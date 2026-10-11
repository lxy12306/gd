from pathlib import Path
import json

import pytest

from oss_toolkit.cli import main, parse_size
from oss_toolkit.config import Settings
from oss_toolkit import OSSManager
from oss_toolkit.service import describe_error


@pytest.fixture(autouse=True)
def clear_oss_environment(monkeypatch, tmp_path):
    import os
    import oss_toolkit.config as config
    # Never load a user's real ~/.ossenv when this test suite is run after configuration.
    monkeypatch.setattr(config, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(config, "default_env_file", lambda: tmp_path / ".ossenv")
    for name in list(os.environ):
        if name.startswith("OSS_") or name in config.CONFIG_NAMES:
            monkeypatch.delenv(name)


def test_config_defaults_and_secrets_are_not_printed(monkeypatch, capsys):
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "not-a-real-key")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "not-a-real-secret")
    assert main(["config"]) == 0
    output = capsys.readouterr().out
    assert "not-a-real-key" not in output
    assert "not-a-real-secret" not in output
    assert json.loads(output)["bucket"] == "smell"


def test_environment_overrides_dotenv_and_cli_overrides_environment(tmp_path, monkeypatch):
    path = tmp_path / "config.env"
    path.write_text("OSS_BUCKET=file-bucket\nOSS_REGION=cn-shanghai\n", encoding="utf-8")
    monkeypatch.setenv("OSS_BUCKET", "env-bucket")
    assert Settings.from_env(path).bucket == "env-bucket"
    assert Settings.from_env(path, bucket="cli-bucket").bucket == "cli-bucket"


def test_default_user_config_loaded_outside_project_with_bom(tmp_path, monkeypatch, capsys):
    (tmp_path / ".ossenv").write_text(
        "ACCESS_KEY_ID=fake-home-key\nACCESS_KEY_SECRET=fake-home-secret\nBUCKET=home-bucket\n",
        encoding="utf-8-sig",
    )
    (tmp_path / ".env").write_text("OSS_BUCKET=ignored-project-bucket\n", encoding="utf-8")
    working = tmp_path / "unrelated"
    working.mkdir()
    (working / ".ossenv").write_text("OSS_BUCKET=ignored-cwd-bucket\n", encoding="utf-8")
    monkeypatch.chdir(working)
    assert main(["config"]) == 0
    output = capsys.readouterr().out
    value = json.loads(output)
    assert value["bucket"] == "home-bucket"
    assert value["credentials_configured"] is True
    assert value["env_file"] == str(tmp_path / ".ossenv")
    assert value["env_file_exists"] is True
    assert "fake-home-key" not in output and "fake-home-secret" not in output


def test_explicit_env_file_replaces_default_user_file(tmp_path, capsys):
    (tmp_path / ".ossenv").write_text("OSS_BUCKET=home-bucket\nOSS_WORKERS=invalid\n", encoding="utf-8")
    explicit = tmp_path / "explicit.env"
    explicit.write_text("OSS_BUCKET=explicit-bucket\n", encoding="utf-8")
    assert main(["config", "--env-file", str(explicit)]) == 0
    assert json.loads(capsys.readouterr().out)["bucket"] == "explicit-bucket"


def test_bare_config_fields_reach_sdk_and_override_legacy_file_fields(tmp_path):
    from urllib.parse import parse_qs, urlsplit
    path = tmp_path / ".ossenv"
    path.write_text(
        "OSS_ACCESS_KEY_ID=\nACCESS_KEY_ID=fake-bare-id\nACCESS_KEY_SECRET=fake-bare-secret\n"
        "SESSION_TOKEN=fake-bare-token\nBUCKET=bare-bucket\nREGION=cn-hangzhou\n"
        "WORKERS=2\nPART_SIZE_MB=4\nCONNECT_TIMEOUT=7\nREAD_TIMEOUT=30\nMAX_ATTEMPTS=2\n",
        encoding="utf-8",
    )
    settings = Settings.from_env(path)
    assert settings.bucket == "bare-bucket"
    assert settings.workers == 2 and settings.part_size == 4 * 1024 * 1024
    assert settings.connect_timeout == 7 and settings.read_timeout == 30 and settings.max_attempts == 2
    # Presigning is local: prove the real SDK received both the ID and STS token without a cloud request.
    query = parse_qs(urlsplit(OSSManager(settings).signed_url("file.txt")["url"]).query)
    assert query["x-oss-credential"][0].startswith("fake-bare-id/")
    assert query["x-oss-security-token"] == ["fake-bare-token"]


def test_file_keys_are_case_insensitive_and_environment_keeps_priority(tmp_path, monkeypatch):
    path = tmp_path / ".ossenv"
    path.write_text("bucket=file-bucket\nregion=cn-shanghai\n", encoding="utf-8")
    monkeypatch.setenv("BUCKET", "env-bucket")
    settings = Settings.from_env(path)
    assert settings.bucket == "env-bucket"
    assert settings.region == "cn-shanghai"


def test_global_flags_before_and_after_subcommand(capsys):
    assert main(["--bucket", "before-bucket", "config", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["bucket"] == "before-bucket"
    assert main(["config", "--bucket", "after-bucket", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["bucket"] == "after-bucket"


def test_upload_directory_dry_run_works_without_credentials(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("sample")
    (tmp_path / ".env").write_text("do not upload")
    assert main(["upload-dir", str(tmp_path), "--prefix", "docs", "--dry-run", "--json"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["planned"] == 1
    assert value["items"][0]["target"] == "docs/a.txt"


def test_missing_credentials_produce_useful_json(capsys):
    assert main(["list", "--json"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert "ACCESS_KEY_ID" in output["error"]
    assert "OSS_ACCESS_KEY_ID" not in output["error"]


def test_error_output_redacts_secret_values(monkeypatch):
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "sensitive-test-value")
    assert "sensitive-test-value" not in describe_error(ValueError("bad sensitive-test-value"))


@pytest.mark.parametrize("size,expected", [("1024", 1024), ("1.5MB", 1572864), ("2GiB", 2147483648)])
def test_human_size_arguments(size, expected):
    assert parse_size(size) == expected


def test_invalid_cname_configuration_rejected():
    with pytest.raises(ValueError, match="ENDPOINT"):
        Settings(use_cname=True).validate()
