"""The direct WLAN option must preserve the OSS TLS name and restore DNS afterward."""

import socket

import pytest

from oss_toolkit.config import Settings
from oss_toolkit import network


def test_direct_wlan_scopes_dns_and_uses_a_bound_adapter(monkeypatch):
    monkeypatch.setattr(network.sys, "platform", "win32")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "fake-id")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "fake-secret")
    values = iter(("192.0.2.5", "198.51.100.8"))
    monkeypatch.setattr(network, "_powershell_value", lambda command: next(values))
    calls = []

    def original(host, port, *args, **kwargs):
        calls.append((host, port))
        return []

    monkeypatch.setattr(socket, "getaddrinfo", original)
    captured = {}
    monkeypatch.setattr(network.oss, "Client", lambda config: captured.setdefault("config", config))
    settings = Settings(bucket="example-bucket", region="cn-hangzhou")

    with network.direct_wlan_client(settings):
        assert socket.getaddrinfo("example-bucket.oss-cn-hangzhou.aliyuncs.com", 443) == []
        assert calls[-1] == ("198.51.100.8", 443)
        assert captured["config"].http_client is not None

    assert socket.getaddrinfo is original


def test_direct_wlan_rejects_custom_endpoint_before_network_calls():
    with pytest.raises(ValueError, match="默认 OSS 地域端点"):
        with network.direct_wlan_client(Settings(endpoint="https://example.com")):
            pass
