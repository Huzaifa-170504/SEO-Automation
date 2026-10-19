from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


async def validate_public_http_url(url: str, *, allow_private: bool = False) -> None:
    """Reject credentials, unsupported schemes, and SSRF-prone destinations."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("URL must use http:// or https:// and include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")
    if allow_private:
        return
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            resolved = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError("URL hostname could not be resolved.") from exc
        addresses = list(
            {ipaddress.ip_address(item[4][0]) for item in resolved if item[4]}
        )
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("URL must resolve only to public network addresses.")
