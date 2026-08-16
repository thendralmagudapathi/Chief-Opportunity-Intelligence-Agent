"""Outbound HTTP with SSRF controls (docs/SECURITY_MODEL.md §6)."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.security.trust import ExternalContent, sanitize_external_text

logger = get_logger(__name__)

_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.azure.com",
        "metadata.aws.internal",
    }
)


_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.is_private or address.is_loopback or address.is_link_local:
        return True
    if address.is_multicast or address.is_reserved or address.is_unspecified:
        return True
    return isinstance(address, ipaddress.IPv4Address) and address in _CGNAT


def validate_url(url: str, *, allow_http: bool) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        raise ValidationError("URL scheme must be https or http")
    if parsed.scheme == "http" and not allow_http:
        raise ValidationError("HTTP is only allowed in development and test")
    if not parsed.hostname:
        raise ValidationError("URL must include a hostname")
    host = parsed.hostname.lower()
    if host in _METADATA_HOSTS:
        raise ValidationError("Metadata endpoints are blocked")
    if host.endswith(".internal") or host.endswith(".local"):
        raise ValidationError("Internal hostnames are blocked")

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise ValidationError("Unable to resolve hostname") from exc

    for info in infos:
        sockaddr = info[4]
        ip_text = str(sockaddr[0])
        try:
            address = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if _is_blocked_ip(address):
            raise ValidationError("Target resolves to a blocked address range")
    return url


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str | None
    body: str
    retrieved_at: datetime


class SafeHttpClient:
    """Single egress path for tool-layer HTTP fetches."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.allow_http = settings.environment.value in {"development", "test"}
        self.max_bytes = settings.egress.max_response_bytes
        self.timeout_s = settings.egress.timeout_s
        self.user_agent = settings.egress.user_agent

    async def fetch(self, url: str) -> FetchResult:
        safe_url = validate_url(url, allow_http=self.allow_http)
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_s,
            headers=headers,
        ) as client:
            response = await client.get(safe_url)
            if response.url.host:
                validate_url(str(response.url), allow_http=self.allow_http)
            raw = response.content[: self.max_bytes]
            encoding = response.encoding or "utf-8"
            text = sanitize_external_text(raw.decode(encoding, errors="replace"))
            logger.info(
                "egress_fetch",
                url=safe_url,
                status=response.status_code,
                bytes=len(raw),
            )
            return FetchResult(
                url=str(response.url),
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                body=text,
                retrieved_at=datetime.now(UTC),
            )

    def as_external(self, result: FetchResult) -> ExternalContent:
        return ExternalContent(
            text=result.body,
            source_url=result.url,
            retrieved_at=result.retrieved_at,
        )
