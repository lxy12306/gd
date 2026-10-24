"""Optional process-scoped WLAN route for the default OSS endpoint on Windows."""

from __future__ import annotations

from contextlib import contextmanager
from ipaddress import IPv4Address
import re
import socket
import subprocess
import sys
from threading import Lock
from typing import Iterator

import alibabacloud_oss_v2 as oss
from alibabacloud_oss_v2.transport import RequestsHttpClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings, require_credentials


_route_lock = Lock()


def _powershell_value(command: str) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, timeout=15, check=True,
    )
    values = result.stdout.strip().splitlines()
    if not values:
        raise RuntimeError("无法取得 WLAN 地址或 OSS 真实地址")
    return str(IPv4Address(values[0].strip()))


@contextmanager
def direct_wlan_client(settings: Settings) -> Iterator[oss.Client]:
    """Bind OSS requests to WLAN without changing the TLS hostname or system routes."""
    if settings.endpoint or settings.use_cname:
        raise ValueError("--direct-wlan 只支持默认 OSS 地域端点")
    if sys.platform != "win32":
        raise ValueError("--direct-wlan 目前只支持 Windows")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", settings.bucket) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", settings.region):
        raise ValueError("--direct-wlan 需要有效的 Bucket 和地域名称")
    require_credentials()
    host = f"{settings.bucket}.oss-{settings.region}.aliyuncs.com"
    local_ip = _powershell_value(
        "Get-NetIPAddress -InterfaceAlias WLAN -AddressFamily IPv4 | "
        "Where-Object { $_.AddressState -eq 'Preferred' } | "
        "Select-Object -First 1 -ExpandProperty IPAddress"
    )
    remote_ip = _powershell_value(
        f"Resolve-DnsName -Name '{host}' -Server 223.5.5.5 -Type A -DnsOnly | "
        "Where-Object { $_.Type -eq 'A' } | "
        "Select-Object -First 1 -ExpandProperty IPAddress"
    )

    class BoundAdapter(HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
            pool_kwargs["source_address"] = (local_ip, 0)
            super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

    config = oss.config.load_default()
    config.region = settings.region
    config.endpoint = settings.endpoint
    config.use_cname = settings.use_cname
    config.credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()
    config.connect_timeout = settings.connect_timeout
    config.readwrite_timeout = settings.read_timeout
    config.retry_max_attempts = settings.max_attempts
    config.user_agent = "smell-oss-toolkit/1.0.0"
    config.http_client = RequestsHttpClient(adapter=BoundAdapter(
        max_retries=Retry(total=False, redirect=False, raise_on_status=False)
    ))

    with _route_lock:
        original = socket.getaddrinfo

        def resolve(name, port, *args, **kwargs):
            if isinstance(name, str) and name.lower() == host:
                name = remote_ip
            return original(name, port, *args, **kwargs)

        socket.getaddrinfo = resolve
        try:
            yield oss.Client(config)
        finally:
            socket.getaddrinfo = original
