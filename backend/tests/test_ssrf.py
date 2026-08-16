"""SSRF guard tests."""

from __future__ import annotations

import pytest
from app.core.errors import ValidationError
from app.security.egress import validate_url


def test_blocks_metadata_host() -> None:
    with pytest.raises(ValidationError, match="Metadata"):
        validate_url("http://169.254.169.254/latest/meta-data/", allow_http=True)


def test_blocks_localhost() -> None:
    with pytest.raises(ValidationError, match="blocked"):
        validate_url("http://localhost/", allow_http=True)


def test_blocks_private_ip_literal() -> None:
    with pytest.raises(ValidationError, match="blocked"):
        validate_url("http://127.0.0.1/", allow_http=True)


def test_allows_public_https() -> None:
    url = validate_url("https://example.com/jobs", allow_http=False)
    assert url == "https://example.com/jobs"


def test_rejects_ftp_scheme() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        validate_url("ftp://example.com/file", allow_http=True)
