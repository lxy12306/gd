"""Exercise the built-in static site publisher against its own local HTTP server."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from gd_core import site


def test_site_config_and_publish_plan_skip_secrets(tmp_path):
    path = tmp_path / "sites.json"
    assert site.main(["--config", str(path), "add", "demo", "--provider", "self", "--url", "http://127.0.0.1:8765", "--root", str(tmp_path)]) == 0
    assert site.read_config(path)["sites"]["demo"]["url"] == "http://127.0.0.1:8765/"
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.html").write_text("<h1>hello</h1>", encoding="utf-8")
    (source / ".env").write_text("SECRET=bad")
    (source / "assets").mkdir()
    (source / "assets" / "main.css").write_text("body{}")
    files = site.publish_files(source, None)
    assert [name for name, _ in files] == ["assets/main.css", "index.html"]
    with pytest.raises(ValueError):
        site.safe_name("../secret")


def test_site_publish_roundtrip_and_write_authentication(tmp_path, monkeypatch):
    root = tmp_path / "served"
    root.mkdir()
    original = site.ThreadingHTTPServer
    holder = {}

    def make_server(address, handler):
        server = original(address, handler)
        holder["server"] = server
        return server

    monkeypatch.setattr(site, "ThreadingHTTPServer", make_server)
    with ThreadPoolExecutor(max_workers=1) as pool:
        profile = {"url": "http://127.0.0.1/", "root": str(root), "token": "x" * 40, "provider": "self"}
        task = pool.submit(site.serve, profile, host="127.0.0.1", port=0)
        for _ in range(100):
            if "server" in holder:
                break
            time.sleep(0.01)
        assert "server" in holder
        port = holder["server"].server_address[1]
        profile["url"] = f"http://127.0.0.1:{port}/"
        source = tmp_path / "index.html"
        source.write_text("<!doctype html><h1>Published</h1>", encoding="utf-8")
        try:
            urls = site.publish(profile, [("index.html", source)])
            assert urls == [f"http://127.0.0.1:{port}/index.html"]
            with urlopen(profile["url"]) as response:
                assert response.read() == source.read_bytes()
                assert response.headers["Content-Type"] == "text/html"
            style = tmp_path / "main.css"
            style.write_text("body{color:teal}", encoding="utf-8")
            assert site.publish(profile, [("assets/main.css", style)]) == [f"http://127.0.0.1:{port}/assets/main.css"]
            assert (root / "assets" / "main.css").read_bytes() == style.read_bytes()
            with pytest.raises(HTTPError) as error:
                urlopen(Request(profile["url"] + "__gd/publish/evil.html", data=b"evil", method="PUT"))
            assert error.value.code == 401
        finally:
            holder["server"].shutdown()
            task.result(timeout=5)
