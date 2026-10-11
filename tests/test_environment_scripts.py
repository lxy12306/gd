"""Verify bootstrap boundaries and the real Windows Python command wrapper."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

PROJECT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(os.name != "nt" or POWERSHELL is None, reason="Windows PowerShell scripts")


def run_ps(script, *arguments):
    return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
                          capture_output=True, encoding="utf-8", errors="replace")


def copy_installer(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    shutil.copy2(PROJECT / "install-gd.ps1", project / "install-gd.ps1")
    python = project / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    # These ownership guards must stop before attempting to execute Python.
    python.write_bytes(b"not an executable")
    target = tmp_path / "global commands"
    target.mkdir()
    launcher = target / "gd.exe"
    launcher.write_bytes(b"original launcher")
    manifest = target / "gd.install.json"
    return project, target, launcher, manifest


@pytest.mark.parametrize("migrate", [False, True])
def test_unrelated_installation_is_not_overwritten(tmp_path, migrate):
    project, target, launcher, manifest = copy_installer(tmp_path)
    original = json.dumps({"project": str(tmp_path / "unrelated"), "launcher": str(launcher)})
    manifest.write_text(original, encoding="utf-8")
    arguments = ["-InstallDir", str(target)]
    if migrate:
        arguments += ["-MigrateFrom", str(tmp_path / "wrong previous project")]
    result = run_ps(project / "install-gd.ps1", *arguments)
    assert result.returncode != 0
    assert "another project" in result.stderr
    assert launcher.read_bytes() == b"original launcher"
    assert manifest.read_text(encoding="utf-8") == original


def test_migration_cannot_uninstall_another_project(tmp_path):
    project, target, launcher, manifest = copy_installer(tmp_path)
    owner = tmp_path / "old project"
    original = json.dumps({"project": str(owner), "launcher": str(launcher)})
    manifest.write_text(original, encoding="utf-8")
    result = run_ps(project / "install-gd.ps1", "-InstallDir", str(target), "-MigrateFrom", str(owner), "-Uninstall")
    assert result.returncode != 0
    assert launcher.read_bytes() == b"original launcher"
    assert manifest.read_text(encoding="utf-8") == original


def test_matching_owner_can_remove_only_the_launcher(tmp_path):
    project, target, launcher, manifest = copy_installer(tmp_path)
    manifest.write_text(json.dumps({"project": str(project), "launcher": str(launcher)}), encoding="utf-8")
    unrelated = target / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    result = run_ps(project / "install-gd.ps1", "-InstallDir", str(target), "-Uninstall")
    assert result.returncode == 0, result.stderr
    assert not launcher.exists()
    assert not manifest.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (project / ".venv" / "Scripts" / "python.exe").exists()


def test_incomplete_virtual_environment_is_preserved(tmp_path):
    project = tmp_path / "bootstrap project"
    project.mkdir()
    shutil.copy2(PROJECT / "setup.ps1", project / "setup.ps1")
    venv = project / ".venv"
    venv.mkdir()
    sentinel = venv / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    result = run_ps(project / "setup.ps1", "-NoLauncher")
    assert result.returncode != 0
    assert "incomplete .venv" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_missing_python_does_not_create_environment(tmp_path):
    shutil.copy2(PROJECT / "setup.ps1", tmp_path / "setup.ps1")
    result = run_ps(tmp_path / "setup.ps1", "-NoLauncher", "-Python", "gd-review-missing-python.exe")
    assert result.returncode != 0
    assert "Cannot find the requested Python" in result.stderr
    assert not (tmp_path / ".venv").exists()


def test_conflicting_modes_stop_before_creating_environment(tmp_path):
    shutil.copy2(PROJECT / "setup.ps1", tmp_path / "setup.ps1")
    result = run_ps(tmp_path / "setup.ps1", "-CoreOnly", "-Dev", "-NoLauncher")
    assert result.returncode != 0
    assert "cannot be combined" in result.stderr
    assert not (tmp_path / ".venv").exists()


def test_run_wrapper_requires_its_own_virtual_environment(tmp_path):
    shutil.copy2(PROJECT / "run.ps1", tmp_path / "run.ps1")
    result = run_ps(tmp_path / "run.ps1", "--version")
    assert result.returncode != 0
    assert "Run setup.ps1 first" in result.stderr


def test_run_wrapper_forwards_arguments_and_exit_code(tmp_path):
    project = tmp_path / "local runner"
    project.mkdir()
    shutil.copy2(PROJECT / "run.ps1", project / "run.ps1")
    # Use a real isolated venv; the wrapper must ignore whichever Python is on PATH.
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(project / ".venv")], check=True)
    script = project / "echo arguments.py"
    script.write_text(
        "import json, sys\nprint(json.dumps({'prefix': sys.prefix, 'args': sys.argv[1:]}))\nsys.exit(7)\n",
        encoding="utf-8",
    )
    result = run_ps(project / "run.ps1", str(script), "space value", "中文参数", "--flag", "a&b")
    assert result.returncode == 7, result.stderr
    value = json.loads(result.stdout)
    assert Path(value["prefix"]).resolve() == (project / ".venv").resolve()
    assert value["args"] == ["space value", "中文参数", "--flag", "a&b"]
