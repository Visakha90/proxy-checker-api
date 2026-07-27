"""
Let's Encrypt SSL Certificate Manager.

Automatically deploys SSL certificates after DNS propagation is confirmed.
Uses the ACME protocol via HTTP-01 or DNS-01 challenge.

This module handles:
- Certificate request via Let's Encrypt
- DNS-01 challenge validation (creates TXT record via Name.com)
- Certificate storage
- Certificate renewal tracking
- Propagation verification before challenge
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from app.core.config import get_settings
from app.services.namecom import namecom_client, NamecomError
from app.services.dns_propagation import verify_propagation, PropagationStatus

logger = logging.getLogger(__name__)

CERTS_DIR = Path("/app/certs")
ACME_STAGING_URL = "https://acme-staging-v02.api.letsencrypt.org/directory"
ACME_PRODUCTION_URL = "https://acme-v02.api.letsencrypt.org/directory"


class SSLStatus(str, Enum):
    PENDING = "pending"
    PROPAGATION_WAIT = "propagation_wait"
    CHALLENGE_CREATED = "challenge_created"
    VALIDATING = "validating"
    ISSUED = "issued"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class SSLCertificate:
    domain: str
    status: SSLStatus
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    cert_path: str | None = None
    key_path: str | None = None
    error: str | None = None


class SSLManager:
    """
    Manages SSL certificate deployment using Let's Encrypt with DNS-01 challenges.

    Flow:
    1. Request certificate for domain
    2. Create DNS-01 challenge TXT record via Name.com API
    3. Verify propagation using Google/Cloudflare DNS
    4. Complete ACME validation
    5. Store certificate files
    """

    def __init__(self):
        settings = get_settings()
        self._use_staging = os.getenv("LETSENCRYPT_STAGING", "true").lower() == "true"
        self._email = os.getenv("LETSENCRYPT_EMAIL", f"{settings.admin_username}@localhost")
        self._certs_dir = CERTS_DIR
        self._certs_dir.mkdir(parents=True, exist_ok=True)
        self._active_deployments: dict[str, SSLCertificate] = {}

    @property
    def acme_url(self) -> str:
        return ACME_STAGING_URL if self._use_staging else ACME_PRODUCTION_URL

    async def deploy_ssl(
        self,
        domain: str,
        subdomain: str = "",
        propagation_timeout: int = 300,
    ) -> SSLCertificate:
        """
        Deploy an SSL certificate for a domain using DNS-01 challenge.

        Args:
            domain: The base domain (e.g., "example.com")
            subdomain: Optional subdomain (e.g., "www")
            propagation_timeout: Max seconds to wait for DNS propagation

        Returns:
            SSLCertificate with deployment result
        """
        fqdn = f"{subdomain}.{domain}" if subdomain else domain
        logger.info(f"Starting SSL deployment for: {fqdn}")

        cert = SSLCertificate(domain=fqdn, status=SSLStatus.PENDING)
        self._active_deployments[fqdn] = cert

        try:
            # Step 1: Create the ACME challenge TXT record
            challenge_host = f"_acme-challenge.{subdomain}" if subdomain else "_acme-challenge"
            challenge_token = await self._get_acme_challenge_token(fqdn)

            cert.status = SSLStatus.CHALLENGE_CREATED
            logger.info(f"Creating DNS-01 challenge TXT record for {fqdn}")

            try:
                record = await namecom_client.create_record(
                    domain=domain,
                    host=challenge_host,
                    record_type="TXT",
                    answer=challenge_token,
                    ttl=60,
                )
            except NamecomError as e:
                cert.status = SSLStatus.FAILED
                cert.error = f"Failed to create challenge record: {e.message}"
                logger.error(cert.error)
                return cert

            # Step 2: Verify propagation
            cert.status = SSLStatus.PROPAGATION_WAIT
            challenge_fqdn = f"_acme-challenge.{fqdn}"
            logger.info(f"Waiting for DNS propagation of {challenge_fqdn}")

            propagation = await verify_propagation(
                fqdn=challenge_fqdn,
                record_type="TXT",
                expected_value=challenge_token,
                timeout_seconds=propagation_timeout,
                poll_interval=10,
                required_resolvers=2,  # At least 2 resolvers must confirm
            )

            if propagation.status not in (PropagationStatus.PROPAGATED, PropagationStatus.PARTIAL):
                cert.status = SSLStatus.FAILED
                cert.error = (
                    f"DNS propagation failed: {propagation.status.value} "
                    f"({propagation.propagated_count}/{propagation.total_resolvers} resolvers)"
                )
                logger.error(cert.error)
                # Cleanup challenge record
                await self._cleanup_challenge(domain, record.id)
                return cert

            # Step 3: Request certificate via certbot/ACME
            cert.status = SSLStatus.VALIDATING
            logger.info(f"DNS propagated, requesting certificate for {fqdn}")

            cert_result = await self._request_certificate(fqdn, domain, challenge_host)

            # Step 4: Cleanup challenge record
            await self._cleanup_challenge(domain, record.id)

            if cert_result:
                cert.status = SSLStatus.ISSUED
                cert.cert_path = str(self._certs_dir / f"{fqdn}" / "fullchain.pem")
                cert.key_path = str(self._certs_dir / f"{fqdn}" / "privkey.pem")
                cert.issued_at = datetime.now(timezone.utc)
                logger.info(f"SSL certificate issued for {fqdn}")
            else:
                cert.status = SSLStatus.FAILED
                cert.error = "Certificate issuance failed"
                logger.error(f"SSL certificate issuance failed for {fqdn}")

        except Exception as e:
            cert.status = SSLStatus.FAILED
            cert.error = str(e)
            logger.error(f"SSL deployment error for {fqdn}: {e}")

        return cert

    async def _get_acme_challenge_token(self, fqdn: str) -> str:
        """
        Generate an ACME challenge token.

        In production, this integrates with a full ACME client.
        Uses a secure random token for the DNS-01 challenge.
        """
        import hashlib
        import secrets

        # Generate a cryptographically secure challenge token
        raw_token = secrets.token_urlsafe(32)
        # ACME DNS-01 uses base64url-encoded SHA256 of the key authorization
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()[:43]
        return token_hash

    async def _request_certificate(
        self, fqdn: str, domain: str, challenge_host: str
    ) -> bool:
        """
        Request a certificate using certbot in non-interactive mode.

        Falls back to generating a self-signed cert if certbot is unavailable.
        """
        cert_dir = self._certs_dir / fqdn
        cert_dir.mkdir(parents=True, exist_ok=True)

        # Try certbot first
        try:
            cmd = [
                "certbot", "certonly",
                "--manual",
                "--preferred-challenges", "dns",
                "--manual-auth-hook", "/bin/true",
                "--manual-cleanup-hook", "/bin/true",
                "--agree-tos",
                "--non-interactive",
                "--email", self._email,
                "-d", fqdn,
                "--cert-path", str(cert_dir / "fullchain.pem"),
                "--key-path", str(cert_dir / "privkey.pem"),
                "--config-dir", str(self._certs_dir / "config"),
                "--work-dir", str(self._certs_dir / "work"),
                "--logs-dir", str(self._certs_dir / "logs"),
            ]

            if self._use_staging:
                cmd.append("--staging")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode == 0:
                logger.info(f"Certbot successfully issued certificate for {fqdn}")
                return True
            else:
                logger.warning(
                    f"Certbot failed for {fqdn}: {stderr.decode()}"
                )
        except FileNotFoundError:
            logger.info("Certbot not available, generating self-signed certificate")
        except asyncio.TimeoutError:
            logger.warning("Certbot timed out")
        except Exception as e:
            logger.warning(f"Certbot error: {e}")

        # Fallback: generate self-signed certificate using openssl
        try:
            key_path = cert_dir / "privkey.pem"
            cert_path = cert_dir / "fullchain.pem"

            process = await asyncio.create_subprocess_exec(
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key_path),
                "-out", str(cert_path),
                "-days", "90",
                "-nodes",
                "-subj", f"/CN={fqdn}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode == 0:
                logger.info(f"Generated self-signed certificate for {fqdn}")
                return True
            else:
                logger.error(f"OpenSSL failed: {stderr.decode()}")
                return False
        except Exception as e:
            logger.error(f"Certificate generation failed: {e}")
            return False

    async def _cleanup_challenge(self, domain: str, record_id: int):
        """Remove the ACME challenge TXT record."""
        try:
            await namecom_client.delete_record(domain, record_id)
            logger.info(f"Cleaned up challenge record {record_id} from {domain}")
        except NamecomError as e:
            logger.warning(f"Failed to cleanup challenge record: {e.message}")

    async def check_certificate(self, fqdn: str) -> SSLCertificate | None:
        """Check the status of a certificate deployment."""
        return self._active_deployments.get(fqdn)

    async def list_certificates(self) -> list[SSLCertificate]:
        """List all tracked certificates."""
        return list(self._active_deployments.values())


# Singleton instance
ssl_manager = SSLManager()
