"""
Shared test fixtures and configuration.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Set test environment variables before importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["NAMECOM_USERNAME"] = "test_user"
os.environ["NAMECOM_API_TOKEN"] = "test_token_12345"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_namecom_response():
    """Factory for mock Name.com API responses."""

    def _make_response(status_code=200, json_data=None, text=""):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        response.json.return_value = json_data or {}
        response.headers = {}
        return response

    return _make_response


@pytest.fixture
def sample_dns_record():
    """Sample DNS record data from Name.com API."""
    return {
        "id": 12345,
        "domainName": "example.com",
        "host": "www",
        "fqdn": "www.example.com.",
        "type": "A",
        "answer": "1.2.3.4",
        "ttl": 300,
        "priority": None,
    }


@pytest.fixture
def sample_records_list(sample_dns_record):
    """Sample list of DNS records."""
    return {
        "records": [
            sample_dns_record,
            {
                "id": 12346,
                "domainName": "example.com",
                "host": "mail",
                "fqdn": "mail.example.com.",
                "type": "MX",
                "answer": "mail.example.com.",
                "ttl": 300,
                "priority": 10,
            },
            {
                "id": 12347,
                "domainName": "example.com",
                "host": "",
                "fqdn": "example.com.",
                "type": "TXT",
                "answer": "v=spf1 include:_spf.google.com ~all",
                "ttl": 3600,
                "priority": None,
            },
        ]
    }
