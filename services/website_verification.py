"""Safe, explainable checks for a supplied company website."""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


MAX_RESPONSE_BYTES = 512_000
MAX_REDIRECTS = 4
DEFAULT_TIMEOUT_SECONDS = 6
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}


class WebsiteVerificationError(ValueError):
    """Raised when a website cannot be checked safely."""


def _normalise_url(raw_url: str) -> str:
    value = (raw_url or "").strip()

    if not value:
        raise WebsiteVerificationError("No company website was supplied.")

    if "://" not in value:
        value = f"https://{value}"

    parsed = urlsplit(value)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise WebsiteVerificationError(
            "Only HTTP and HTTPS company websites are supported."
        )

    if not parsed.hostname:
        raise WebsiteVerificationError("The company website is invalid.")

    if parsed.username or parsed.password:
        raise WebsiteVerificationError(
            "Website URLs containing login credentials are not allowed."
        )

    try:
        port = parsed.port
    except ValueError as error:
        raise WebsiteVerificationError(
            "The company website contains an invalid port."
        ) from error

    if port is not None and port not in ALLOWED_PORTS:
        raise WebsiteVerificationError(
            "Only standard web ports 80 and 443 are allowed."
        )

    return value


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(ip.is_global)


def _resolve_public_addresses(hostname: str) -> list[str]:
    try:
        records = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise WebsiteVerificationError(
            "The company website domain could not be resolved."
        ) from error

    addresses = sorted({record[4][0] for record in records})

    if not addresses:
        raise WebsiteVerificationError(
            "The company website domain has no network address."
        )

    if any(not _is_public_ip(address) for address in addresses):
        raise WebsiteVerificationError(
            "Local, private and reserved network addresses are not allowed."
        )

    return addresses


def _validate_public_url(raw_url: str) -> str:
    url = _normalise_url(raw_url)
    hostname = urlsplit(url).hostname
    assert hostname is not None
    _resolve_public_addresses(hostname)
    return url


class _NoAutomaticRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        request,
        file_pointer,
        code,
        message,
        headers,
        new_url,
    ):
        return None


def _extract_title(content: bytes, content_type: str) -> str | None:
    if "html" not in (content_type or "").lower():
        return None

    text = content.decode("utf-8", errors="replace")
    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return None

    title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
    return title[:200] or None


def _request_once(url: str, timeout: int) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "InternShield-AI/1.0 "
                "(student internship website verification)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    opener = build_opener(_NoAutomaticRedirects())

    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            return {
                "status_code": response.status,
                "headers": response.headers,
                "body": body[:MAX_RESPONSE_BYTES],
            }
    except HTTPError as error:
        # Redirects and normal HTTP error responses both arrive here because
        # automatic redirects are intentionally disabled.
        body = error.read(MAX_RESPONSE_BYTES + 1)
        return {
            "status_code": error.code,
            "headers": error.headers,
            "body": body[:MAX_RESPONSE_BYTES],
        }
    except (URLError, TimeoutError, socket.timeout, ssl.SSLError) as error:
        raise WebsiteVerificationError(
            "The company website could not be reached securely."
        ) from error


def verify_company_website(
    website: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """
    Check basic technical signals without treating them as proof of legitimacy.

    The function validates every redirect target and refuses localhost,
    private, link-local, multicast and reserved network destinations.
    """
    current_url = _validate_public_url(website)
    submitted_url = current_url
    redirects: list[str] = []

    for _ in range(MAX_REDIRECTS + 1):
        result = _request_once(current_url, timeout)
        status_code = int(result["status_code"])

        if status_code in {301, 302, 303, 307, 308}:
            location = result["headers"].get("Location")

            if not location:
                raise WebsiteVerificationError(
                    "The website returned an invalid redirect."
                )

            next_url = urljoin(current_url, location)
            current_url = _validate_public_url(next_url)
            redirects.append(current_url)
            continue

        final_parts = urlsplit(current_url)
        content_type = result["headers"].get("Content-Type", "")
        title = _extract_title(result["body"], content_type)
        reachable = 200 <= status_code < 500
        uses_https = final_parts.scheme.lower() == "https"

        checks = [
            {
                "type": "evidence" if reachable else "warning",
                "label": (
                    "Website responded"
                    if reachable
                    else "Website did not return a usable response"
                ),
                "detail": f"HTTP status {status_code}",
            },
            {
                "type": "evidence" if uses_https else "warning",
                "label": (
                    "HTTPS is enabled"
                    if uses_https
                    else "Website does not use HTTPS"
                ),
                "detail": current_url,
            },
        ]

        return {
            "submitted_url": submitted_url,
            "final_url": current_url,
            "final_domain": final_parts.hostname,
            "status_code": status_code,
            "reachable": reachable,
            "uses_https": uses_https,
            "redirect_count": len(redirects),
            "redirects": redirects,
            "page_title": title,
            "checks": checks,
            "disclaimer": (
                "Website reachability and HTTPS are technical signals only. "
                "They do not prove that a company or internship is legitimate."
            ),
        }

    raise WebsiteVerificationError(
        f"The company website exceeded {MAX_REDIRECTS} redirects."
    )

