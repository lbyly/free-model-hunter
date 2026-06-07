"""
DNS-over-HTTPS (DoH) 解析器
用于绕过 DNS 污染，确保正确解析被劫持的域名
"""
import asyncio
import json
import socket
import logging
from contextlib import contextmanager
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Cloudflare DoH 端点
DOH_ENDPOINTS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/dns-query",
]

# 已知被污染的域名及其真实 Cloudflare IP 缓存
# 如果 DoH 也失败，可以使用此缓存
KNOWN_HOST_CACHE: dict[str, str] = {}


async def resolve_via_doh(
    hostname: str,
    dns_type: str = "A",
    timeout: int = 10,
) -> Optional[str]:
    """通过 DNS-over-HTTPS 解析域名，返回 IP 地址"""
    for endpoint in DOH_ENDPOINTS:
        try:
            params = {"name": hostname, "type": dns_type}
            headers = {"Accept": "application/dns-json"}

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(endpoint, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            # 解析 DNS JSON 响应
            for answer in data.get("Answer", []):
                if answer.get("type") == 1:  # A 记录 (IPv4)
                    ip = answer.get("data", "")
                    if ip:
                        logger.info(f"DoH 解析 {hostname} -> {ip} (via {endpoint})")
                        KNOWN_HOST_CACHE[hostname] = ip
                        return ip

        except Exception as e:
            logger.warning(f"DoH {endpoint} 解析 {hostname} 失败: {e}")
            continue

    # DoH 失败时尝试从缓存取
    if hostname in KNOWN_HOST_CACHE:
        cached_ip = KNOWN_HOST_CACHE[hostname]
        logger.info(f"使用缓存 {hostname} -> {cached_ip}")
        return cached_ip

    logger.error(f"所有 DoH 端点解析 {hostname} 均失败")
    return None


async def resolve_batch_via_doh(
    hostnames: list[str],
    dns_type: str = "A",
    timeout: int = 15,
) -> dict[str, str]:
    """批量解析多个域名"""
    results = {}
    tasks = [resolve_via_doh(h, dns_type, timeout) for h in hostnames]
    ips = await asyncio.gather(*tasks, return_exceptions=True)
    for hostname, result in zip(hostnames, ips):
        if isinstance(result, str) and result:
            results[hostname] = result
        elif isinstance(result, Exception):
            logger.warning(f"批量解析 {hostname} 失败: {result}")
    return results


@contextmanager
def dns_patch(host_to_ip: dict[str, str]):
    """
    临时覆盖 socket.getaddrinfo，将指定域名解析到期望的 IP。
    用于绕过系统 DNS 污染，配合 httpx 使用。

    用法:
        with dns_patch({"api.x.ai": "104.18.x.x"}):
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api.x.ai/v1/models")
    """
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
        if host in host_to_ip:
            real_ip = host_to_ip[host]
            logger.debug(f"[DNS Patch] {host} -> {real_ip}")
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    (real_ip, port),
                )
            ]
        return original_getaddrinfo(host, port, family, socktype, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


async def resolve_and_patch(hostname: str) -> Optional[str]:
    """
    一站式：解析域名 + 返回 IP（已缓存到 KNOWN_HOST_CACHE）
    之后调用 dns_patch 即可使用 KNOWN_HOST_CACHE 中的结果
    """
    ip = await resolve_via_doh(hostname)
    if ip:
        KNOWN_HOST_CACHE[hostname] = ip
    return ip
