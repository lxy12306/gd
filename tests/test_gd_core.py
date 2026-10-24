"""Exercise the independent core, persistence and actual subprocess dispatch."""

from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from gd_core.cli import main
from gd_core.registry import Registry
from gd_core.scripts import prepare_script

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("GD_HOME", str(tmp_path / "registry"))
    monkeypatch.setattr(metadata, "entry_points", lambda **kwargs: [])


def make_script(tmp_path, name="中文 脚本.py", exit_code=0):
    source = tmp_path / name
    source.write_text(
        "import json, os, sys\n"
        "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(), 'python': sys.executable}))\n"
        f"sys.exit({exit_code})\n", encoding="utf-8",
    )
    return source


def test_register_and_run_preserves_arguments_and_exit_status(tmp_path, capfd):
    source = make_script(tmp_path, exit_code=7)
    assert main(["add", "demo", str(source), "-d", "示例脚本"]) == 0
    capfd.readouterr()
    arguments = ["--flag", "中文 空格", 'a"b', "a&b", "$(echo injected)", "%PATH%", "--home", "script-only"]
    assert main(["demo", *arguments]) == 7
    assert json.loads(capfd.readouterr().out)["args"] == arguments
    assert main(["run", "demo", "--", *arguments]) == 7
    assert json.loads(capfd.readouterr().out)["args"] == arguments
    assert main(["demo", "--", "--", "literal"]) == 7
    assert json.loads(capfd.readouterr().out)["args"] == ["--", "literal"]


def test_registration_does_not_execute_script_and_duplicate_requires_replace(tmp_path, capsys):
    marker = tmp_path / "executed.txt"
    source = tmp_path / "script.py"
    source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')", encoding="utf-8")
    assert main(["add", "demo", str(source)]) == 0
    assert not marker.exists()
    original = Registry().path.read_bytes()
    assert main(["add", "demo", str(source)]) == 1
    assert "--replace" in capsys.readouterr().err
    assert Registry().path.read_bytes() == original
    assert main(["add", "demo", str(source), "--replace", "-d", "更新说明"]) == 0
    assert Registry().load()["demo"].description == "更新说明"
    assert not marker.exists()


def test_list_info_remove_and_missing_file(tmp_path, capsys):
    source = make_script(tmp_path)
    assert main(["add", "demo", str(source)]) == 0
    capsys.readouterr()
    assert main(["ls", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert [module["name"] for module in result["modules"]] == ["oss", "site"]
    assert result["scripts"][0]["name"] == "demo"
    assert result["scripts"][0]["status"] == "ready"
    assert main(["info", "demo", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(source)
    assert main(["info", "oss", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "module"
    assert main(["rm", "demo"]) == 0
    assert source.exists()
    assert not Registry().load()
    assert main(["remove", "demo"]) == 1
    assert main(["add", "demo", str(source)]) == 0
    source.unlink()
    capsys.readouterr()
    assert main(["list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["scripts"][0]["status"] == "missing"
    assert main(["demo"]) == 1
    assert "已移动或删除" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["oss", "run", "rm", "list", "../demo", "Demo", "a b", "--flag"])
def test_invalid_or_reserved_names_cannot_overwrite_registry(name, tmp_path):
    source = make_script(tmp_path)
    assert main(["add", "safe", str(source)]) == 0
    original = Registry().path.read_bytes()
    # Names starting with -- need the argparse separator, followed by the path.
    arguments = ["add", "--", name, str(source)] if name.startswith("--") else ["add", name, str(source)]
    assert main(arguments) == 1
    assert Registry().path.read_bytes() == original


@pytest.mark.parametrize("payload", ["{broken", '{"version": 2, "scripts": {}}',
                                     '{"version": 1, "scripts": {"demo": {"path": "relative.py", "runner": "python"}}}'])
def test_corrupt_registry_is_preserved_during_mutation(payload, tmp_path, capsys):
    registry = Registry()
    registry.home.mkdir()
    registry.path.write_text(payload, encoding="utf-8")
    source = make_script(tmp_path)
    assert main(["add", "demo", str(source)]) == 1
    assert "注册文件无效" in capsys.readouterr().err
    assert registry.path.read_text(encoding="utf-8") == payload
    assert main(["remove", "demo"]) == 1
    assert registry.path.read_text(encoding="utf-8") == payload


def test_read_only_commands_do_not_create_registry_directory(capsys):
    assert main([]) == 0
    assert "gd oss put" in capsys.readouterr().out
    assert main(["list"]) == 0
    assert not Registry().home.exists()


def test_relative_registration_survives_cwd_change_and_fixed_cwd(tmp_path, monkeypatch, capfd):
    source = make_script(tmp_path)
    run_directory = tmp_path / "run directory"
    run_directory.mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["add", "demo", source.name]) == 0
    assert main(["add", "fixed", source.name, "--cwd", str(tmp_path), "--interpreter", sys.executable]) == 0
    capfd.readouterr()
    monkeypatch.chdir(run_directory)
    assert main(["demo"]) == 0
    result = json.loads(capfd.readouterr().out)
    assert Path(result["cwd"]) == run_directory
    assert Path(result["python"]).resolve() == Path(sys.executable).resolve()
    assert main(["fixed"]) == 0
    assert Path(json.loads(capfd.readouterr().out)["cwd"]) == tmp_path


def test_explicit_home_is_separate_from_environment_home(tmp_path, capsys):
    source = make_script(tmp_path)
    custom = tmp_path / "custom"
    assert main(["--home", str(custom), "add", "demo", str(source)]) == 0
    assert "demo" in Registry(custom).load()
    assert not Registry().load()
    capsys.readouterr()
    assert main([f"--home={custom}", "list", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["scripts"]) == 1


def test_default_registry_is_in_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("GD_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert Registry().path == tmp_path / ".gd" / "scripts.json"


def test_plugin_discovery_is_lazy_and_forwards_argv(tmp_path, monkeypatch, capsys):
    marker = tmp_path / "module-loaded"
    plugin = tmp_path / "gd_test_plugin.py"
    plugin.write_text(
        "import json\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('loaded')\n"
        "def main(argv):\n    print(json.dumps(argv))\n    return 9\n", encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(metadata, "entry_points", lambda **kwargs: [SimpleNamespace(name="demo", value="gd_test_plugin:main")])
    assert main(["list", "--json"]) == 0
    assert not marker.exists()
    capsys.readouterr()
    assert main(["demo", "--help", "space value"]) == 9
    assert json.loads(capsys.readouterr().out) == ["--help", "space value"]
    assert marker.exists()


def test_duplicate_plugin_names_fail_clearly(monkeypatch, capsys):
    monkeypatch.setattr(metadata, "entry_points", lambda **kwargs: [SimpleNamespace(name="oss", value="anything:main")])
    assert main(["list"]) == 1
    assert "重复" in capsys.readouterr().err


def test_core_and_scripts_work_when_oss_imports_are_blocked(tmp_path):
    source = make_script(tmp_path)
    launcher = """
import importlib.abc, sys
class NoOSS(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('oss_toolkit', 'alibabacloud', 'dotenv')):
            raise AssertionError('Core tried to import OSS: ' + fullname)
sys.meta_path.insert(0, NoOSS())
sys.path.insert(0, sys.argv.pop(1))
from gd_core.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    env = {**os.environ, "GD_HOME": str(tmp_path / "independent registry"), "PYTHONUTF8": "1"}
    for arguments in (["--help"], ["list"], ["add", "demo", str(source)], ["demo", "--flag", "中文 空格"], ["remove", "demo"]):
        result = subprocess.run([sys.executable, "-I", "-c", launcher, str(PROJECT), *arguments],
                                cwd=tmp_path, env=env, capture_output=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr
    assert source.exists()


def test_missing_oss_dependency_has_actionable_message(tmp_path):
    launcher = """
import importlib.abc, sys
class MissingSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'alibabacloud_oss_v2':
            raise ModuleNotFoundError('SDK unavailable', name=fullname)
sys.meta_path.insert(0, MissingSDK())
sys.path.insert(0, sys.argv.pop(1))
from gd_core.cli import main
raise SystemExit(main(['oss', 'ls']))
"""
    result = subprocess.run([sys.executable, "-I", "-c", launcher, str(PROJECT)],
                            cwd=tmp_path, capture_output=True, encoding="utf-8")
    assert result.returncode == 1
    assert ".[oss]" in result.stderr
    assert "Traceback" not in result.stderr


def test_concurrent_registration_keeps_every_script(tmp_path):
    source = make_script(tmp_path)
    # Separate processes exercise the cross-process lock rather than a Python thread lock.
    env = {**os.environ, "GD_HOME": str(tmp_path / "concurrent registry"), "PYTHONUTF8": "1"}
    def register(index):
        return subprocess.run([sys.executable, str(PROJECT / "gd.py"), "add", f"demo-{index}", str(source)],
                              env=env, capture_output=True, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(register, range(8)))
    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    assert len(Registry(env["GD_HOME"]).load()) == 8


@pytest.mark.skipif(os.name != "nt", reason="PowerShell runtime on this Windows installation")
def test_powershell_script_runs_with_arguments(tmp_path, capfd):
    source = tmp_path / "script with spaces.ps1"
    source.write_text("param([string]$Value)\nWrite-Output $Value\nexit 6\n", encoding="utf-8-sig")
    assert main(["add", "ps-demo", str(source)]) == 0
    capfd.readouterr()
    assert main(["ps-demo", "-Value", "space value & literal"]) == 6
    assert capfd.readouterr().out.strip() == "space value & literal"


@pytest.mark.skipif(os.name == "nt", reason="Unix executable bit")
def test_linux_executable_and_bash_scripts(tmp_path, capfd):
    executable = tmp_path / "no extension"
    executable.write_text("#!/bin/sh\nprintf '%s\\n' \"$1\"\nexit 8\n", encoding="utf-8")
    executable.chmod(0o755)
    shell = tmp_path / "shell script.sh"
    shell.write_text("printf '%s\\n' \"$1\"\nexit 9\n", encoding="utf-8")
    assert main(["add", "executable", str(executable)]) == 0
    assert main(["add", "shell", str(shell)]) == 0
    capfd.readouterr()
    assert main(["executable", "space value"]) == 8
    assert capfd.readouterr().out.strip() == "space value"
    assert main(["shell", "中文 参数"]) == 9
    assert capfd.readouterr().out.strip() == "中文 参数"
