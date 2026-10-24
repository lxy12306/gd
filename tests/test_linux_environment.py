"""Exercise Linux wrappers and installation without touching the user's home."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux shell and venv paths")
SOURCE = Path(__file__).resolve().parents[1] / "linux"


def project_copy(tmp_path, *names):
    project = tmp_path / "project with spaces"
    project.mkdir()
    scripts = project / "linux"
    scripts.mkdir()
    for name in names:
        shutil.copy2(SOURCE / name, scripts / name)
    return project


def run_bash(script, *args, cwd=None):
    return subprocess.run(["bash", str(script), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True)


def test_setup_preserves_incomplete_environment_and_rejects_conflicts(tmp_path):
    project = project_copy(tmp_path, "setup.sh")
    script = project / "linux" / "setup.sh"
    conflict = run_bash(script, "--core-only", "--dev")
    assert conflict.returncode != 0
    assert not (project / ".venv").exists()
    (project / ".venv").mkdir()
    sentinel = project / ".venv" / "keep.txt"
    sentinel.write_text("keep")
    result = run_bash(script, "--no-launcher")
    assert result.returncode != 0
    assert "incomplete .venv" in result.stderr
    assert sentinel.read_text() == "keep"


def test_run_wrapper_preserves_arguments_cwd_and_exit_code(tmp_path):
    project = project_copy(tmp_path, "run.sh")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(project / ".venv")], check=True)
    script = project / "echo arguments.py"
    script.write_text(
        "import json, os, sys\nprint(json.dumps({'prefix': sys.prefix, 'args': sys.argv[1:], 'cwd': os.getcwd()}))\nsys.exit(7)\n",
        encoding="utf-8",
    )
    caller = tmp_path / "caller directory"
    caller.mkdir()
    result = run_bash(project / "linux" / "run.sh", script, "space value", "中文参数", "--flag", "a&b", cwd=caller)
    assert result.returncode == 7, result.stderr
    value = json.loads(result.stdout)
    assert Path(value["prefix"]).resolve() == (project / ".venv").resolve()
    assert Path(value["cwd"]).resolve() == caller.resolve()
    assert value["args"] == ["space value", "中文参数", "--flag", "a&b"]


def test_installer_refuses_unrelated_command_then_installs_and_uninstalls(tmp_path):
    project = project_copy(tmp_path, "install-gd.py")
    launcher = project / ".venv" / "bin" / "gd"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o755)
    target_dir = tmp_path / "global commands"
    target_dir.mkdir()
    target = target_dir / "gd"
    manifest = target_dir / "gd.install.json"
    target.write_text("unrelated")
    command = [sys.executable, str(project / "linux" / "install-gd.py"), "--install-dir", str(target_dir)]
    env = {"PATH": str(target_dir)}
    refused = subprocess.run(command, capture_output=True, text=True, env=env)
    assert refused.returncode != 0
    assert target.read_text() == "unrelated"
    target.unlink()
    installed = subprocess.run(command, capture_output=True, text=True, env=env)
    assert installed.returncode == 0, installed.stderr
    assert target.is_symlink() and target.resolve() == launcher.resolve()
    assert json.loads(manifest.read_text())["project"] == str(project)
    unrelated = target_dir / "keep.txt"
    unrelated.write_text("keep")
    removed = subprocess.run([*command, "--uninstall"], capture_output=True, text=True, env=env)
    assert removed.returncode == 0, removed.stderr
    assert not target.exists() and not manifest.exists()
    assert unrelated.read_text() == "keep"
    assert launcher.exists()


def test_installer_requires_exact_migration_owner(tmp_path):
    project = project_copy(tmp_path, "install-gd.py")
    launcher = project / ".venv" / "bin" / "gd"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o755)
    previous = tmp_path / "previous project"
    previous_launcher = previous / ".venv" / "bin" / "gd"
    previous_launcher.parent.mkdir(parents=True)
    previous_launcher.write_text("#!/bin/sh\nexit 0\n")
    previous_launcher.chmod(0o755)
    target_dir = tmp_path / "commands"
    target_dir.mkdir()
    target = target_dir / "gd"
    target.symlink_to(previous_launcher)
    manifest = target_dir / "gd.install.json"
    manifest.write_text(json.dumps({"project": str(previous), "launcher": str(target)}))
    command = [sys.executable, str(project / "linux" / "install-gd.py"), "--install-dir", str(target_dir)]
    env = {"PATH": str(target_dir)}
    denied = subprocess.run(command, capture_output=True, text=True, env=env)
    assert denied.returncode != 0
    assert target.resolve() == previous_launcher.resolve()
    denied_remove = subprocess.run([*command, "--uninstall", "--migrate-from", str(previous)], capture_output=True, text=True, env=env)
    assert denied_remove.returncode != 0
    migrated = subprocess.run([*command, "--migrate-from", str(previous)], capture_output=True, text=True, env=env)
    assert migrated.returncode == 0, migrated.stderr
    assert target.resolve() == launcher.resolve()
    assert json.loads(manifest.read_text())["project"] == str(project)
