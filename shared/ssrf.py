"""SSRF (Server-Side Request Forgery) protection utilities.

Validates URLs/hostnames against private and internal network ranges.
Used by agent security tools and webhook callback validation.
"""

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_url(url: str) -> None:
    """Raise ValueError if *url* points to a private/internal network.

    Resolves domain names to IP addresses to prevent DNS rebinding attacks.
    Call this before making any HTTP request or socket connection to a
    user-supplied URL.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname")
    validate_hostname(hostname)


def validate_hostname(hostname: str) -> None:
    """Raise ValueError if *hostname* resolves to a private/internal IP."""

    def _check_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(f"Connection to private network blocked: {addr}")

    try:
        addr = ipaddress.ip_address(hostname)
        _check_ip(addr)
    except ValueError as e:
        if "private network" in str(e) or "Connection to" in str(e):
            raise
        # hostname is a domain name — resolve and validate all addresses
        try:
            addrinfos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            for _family, _type, _proto, _canonname, sockaddr in addrinfos:
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                _check_ip(resolved_ip)
        except socket.gaierror:
            raise ValueError(f"Cannot resolve hostname: {hostname}")  # noqa: B904
