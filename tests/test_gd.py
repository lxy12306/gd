"""Exercise friendly commands through the actual SDK and the local OSS test server."""

import json

import pytest

from oss_toolkit import cli
from oss_toolkit.gd import main


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    import os
    import oss_toolkit.config as config
    monkeypatch.setattr(config, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(config, "default_env_file", lambda: tmp_path / ".ossenv")
    for name in list(os.environ):
        if name.startswith("OSS_") or name in config.CONFIG_NAMES:
            monkeypatch.delenv(name)


def use_local_manager(local_oss, monkeypatch):
    store, factory = local_oss
    manager = factory()
    monkeypatch.setattr(cli, "OSSManager", lambda settings: manager)
    return store


def test_put_file_remote_directory_and_get_output_directory(local_oss, tmp_path, monkeypatch, capsys):
    store = use_local_manager(local_oss, monkeypatch)
    source = tmp_path / "中文 文件.png"
    source.write_bytes(b"sample image")
    assert main(["oss", "put", str(source), "images/", "--json"]) == 0
    assert store.objects["images/中文 文件.png"] == b"sample image"
    assert json.loads(capsys.readouterr().out)["key"] == "images/中文 文件.png"
    destination = tmp_path / "output"
    destination.mkdir()
    assert main(["oss", "get", "images/中文 文件.png", "-o", str(destination), "--json"]) == 0
    assert (destination / "中文 文件.png").read_bytes() == b"sample image"


def test_put_directory_and_get_directory_automatic(local_oss, tmp_path, monkeypatch, capsys):
    store = use_local_manager(local_oss, monkeypatch)
    source = tmp_path / "input"
    (source / "sub").mkdir(parents=True)
    (source / "sub" / "file.txt").write_bytes(b"nested")
    (source / ".env").write_text("excluded")
    (source / ".ossenv").write_text("excluded user credentials")
    assert main(["oss", "put", str(source), "docs", "--json"]) == 0
    assert set(store.objects) == {"docs/sub/file.txt"}
    capsys.readouterr()
    output = tmp_path / "output"
    assert main(["oss", "get", "docs/", str(output), "--json"]) == 0
    assert (output / "sub" / "file.txt").read_bytes() == b"nested"
    assert json.loads(capsys.readouterr().out)["succeeded"] == 1


def test_put_and_get_explicit_filenames(local_oss, tmp_path, monkeypatch):
    store = use_local_manager(local_oss, monkeypatch)
    source = tmp_path / "source.txt"
    source.write_bytes(b"renamed")
    assert main(["oss", "put", str(source), "docs/remote.txt"]) == 0
    assert store.objects["docs/remote.txt"] == b"renamed"
    output = tmp_path / "local.txt"
    assert main(["oss", "get", "docs/remote.txt", str(output)]) == 0
    assert output.read_bytes() == b"renamed"


def test_ls_positional_prefix_and_search(local_oss, monkeypatch, capsys):
    store = use_local_manager(local_oss, monkeypatch)
    store.objects.update({"images/文生图.png": b"png", "other.txt": b"other"})
    assert main(["oss", "ls", "images/", "--json"]) == 0
    assert [item["key"] for item in json.loads(capsys.readouterr().out)["objects"]] == ["images/文生图.png"]
    assert main(["oss", "search", "文生图", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["returned"] == 1


def test_put_dry_run_needs_no_credentials_and_never_calls_oss(tmp_path, capsys, monkeypatch):
    source = tmp_path / "image.png"
    source.write_bytes(b"image")
    monkeypatch.setattr(cli, "OSSManager", lambda *args: pytest.fail("dry-run must not connect"))
    assert main(["oss", "put", str(source), "images/", "-n", "--json"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["target"] == "images/image.png"
    assert value["status"] == "planned"


def test_global_flags_preserved_at_all_three_levels(capsys):
    assert main(["--bucket", "root-bucket", "oss", "config"]) == 0
    assert json.loads(capsys.readouterr().out)["bucket"] == "root-bucket"
    assert main(["oss", "--bucket", "service-bucket", "config"]) == 0
    assert json.loads(capsys.readouterr().out)["bucket"] == "service-bucket"
    assert main(["--bucket", "root-bucket", "oss", "--bucket", "service-bucket", "config", "--bucket", "action-bucket"]) == 0
    assert json.loads(capsys.readouterr().out)["bucket"] == "action-bucket"


def test_help_without_subcommand(capsys):
    assert main([]) == 0
    assert "gd oss put" in capsys.readouterr().out
    assert main(["oss"]) == 0
    assert "put (upload)" in capsys.readouterr().out


def test_duplicate_destinations_fail_before_any_transfer(tmp_path, capsys, monkeypatch):
    source = tmp_path / "a.txt"
    source.write_text("a")
    monkeypatch.setattr(cli, "OSSManager", lambda *args: pytest.fail("must not connect"))
    assert main(["oss", "put", str(source), "a.txt", "--key", "b.txt", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert main(["oss", "get", "a.txt", "a.txt", "--output", "b.txt", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
