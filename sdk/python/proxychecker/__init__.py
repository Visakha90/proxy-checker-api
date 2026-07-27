"""
ProxyChecker Python SDK.

Usage:
    from proxychecker import ProxyChecker

    client = ProxyChecker(api_key="pc_your_key")
    proxies = client.get_proxies(type="http", country="US", limit=50)
    random_proxy = client.get_random(type="socks5")
    stats = client.get_stats()
"""

import requests
from typing import Optional


class ProxyChecker:
    """Official ProxyChecker Python SDK."""

    def __init__(self, api_key: str = "", base_url: str = "http://localhost:8000/api/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-API-Key"] = api_key

    def _get(self, path: str, params: dict = None) -> dict:
        r = self.session.get(f"{self.base_url}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: dict = None) -> dict:
        r = self.session.post(f"{self.base_url}{path}", json=json)
        r.raise_for_status()
        return r.json()

    def get_proxies(
        self,
        type: Optional[str] = None,
        country: Optional[str] = None,
        anonymity: Optional[str] = None,
        alive: bool = True,
        ssl: Optional[bool] = None,
        latency_lt: Optional[int] = None,
        limit: int = 100,
        page: int = 1,
    ) -> dict:
        """Get proxies with filters."""
        params = {"limit": limit, "page": page, "alive": str(alive).lower()}
        if type: params["type"] = type
        if country: params["country"] = country
        if anonymity: params["anonymity"] = anonymity
        if ssl is not None: params["ssl"] = str(ssl).lower()
        if latency_lt: params["latency_lt"] = latency_lt
        return self._get("/proxies", params)

    def get_random(self, type: Optional[str] = None, country: Optional[str] = None) -> dict:
        """Get a random alive proxy."""
        params = {}
        if type: params["type"] = type
        if country: params["country"] = country
        return self._get("/random", params)

    def get_stats(self) -> dict:
        """Get proxy statistics."""
        return self._get("/stats")

    def get_countries(self) -> dict:
        """Get list of countries with proxy counts."""
        return self._get("/countries")

    def rotate(self, type: Optional[str] = None, country: Optional[str] = None) -> dict:
        """Get next proxy in rotation."""
        params = {}
        if type: params["type"] = type
        if country: params["country"] = country
        return self._get("/rotate", params)

    def download(self, type: str = "http", format: str = "txt") -> str:
        """Download proxy list as text."""
        r = self.session.get(f"{self.base_url}/download/{type}", params={"format": format})
        r.raise_for_status()
        return r.text

    def get_speed_tiers(self) -> dict:
        """Get proxy counts by speed tier."""
        return self._get("/speed-tiers")

    def get_leaderboard(self, category: str = "fastest", limit: int = 50) -> dict:
        """Get proxy leaderboard."""
        return self._get(f"/leaderboard/{category}", {"limit": limit})

    def check_fingerprint(self, ip: str, port: int, type: str = "http") -> dict:
        """Check if a proxy is fingerprinted/blacklisted."""
        return self._post("/fingerprint", {"ip": ip, "port": port, "type": type})

    def gateway_request(self, url: str, method: str = "GET", **kwargs) -> dict:
        """Forward a request through the proxy gateway."""
        return self._post("/gateway", {"url": url, "method": method, **kwargs})
