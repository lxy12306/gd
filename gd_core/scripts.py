"""Resolve script runtimes at registration; forward argv without a shell."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

from .errors import GDError
from .registry import Script


def executable(value: str) -> str:
    found = shutil.which(str(Path(value).expanduser()))
    if not found:
        raise GDError(f"找不到解释器：{value}")
    return str(Path(found).resolve())


def prepare_script(path: str, *, runner: str = "auto", interpreter: str | None = None,
                   description: str = "", cwd: str | None = None) -> Script:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise GDError(f"脚本文件不存在：{source}")
    if runner == "auto":
        runner = {".py": "python", ".pyw": "python", ".ps1": "powershell", ".sh": "bash",
                  ".exe": "exec", ".com": "exec"}.get(source.suffix.lower(), "exec")
    if runner == "exec":
        if interpreter:
            raise GDError("exec 类型直接运行文件，不能指定 --interpreter。")
        if os.name == "nt" and source.suffix.lower() not in {".exe", ".com"}:
            raise GDError("请使用 .py、.ps1、.sh 或 .exe 文件；其他扩展名可用 --runner 指定类型。")
        if os.name != "nt" and not os.access(source, os.X_OK):
            raise GDError("文件不可执行；可用 --runner python/bash 等指定解释器。")
        resolved_interpreter = None
    else:
        default = {"python": sys.executable, "powershell": shutil.which("pwsh") or "powershell",
                   "bash": "bash"}[runner]
        resolved_interpreter = executable(interpreter or default)
    directory = Path(cwd).expanduser().resolve() if cwd is not None else None
    if directory is not None and not directory.is_dir():
        raise GDError(f"工作目录不存在：{directory}")
    return Script(str(source), runner, resolved_interpreter, description, str(directory) if directory else None)


def run_script(script: Script, argv: list[str]) -> int:
    if not Path(script.path).is_file():
        raise GDError(f"脚本文件已移动或删除：{script.path}。请用 gd add ... --replace 更新注册。")
    if script.cwd is not None and not Path(script.cwd).is_dir():
        raise GDError(f"工作目录不存在：{script.cwd}")
    if script.runner == "exec":
        command = [script.path]
    elif script.runner == "powershell":
        command = [script.interpreter, "-NoLogo", "-NoProfile"]
        if os.name == "nt":
            command += ["-ExecutionPolicy", "Bypass"]
        command += ["-File", script.path]
    else:
        command = [script.interpreter, script.path]
    # An optional leading separator belongs to gd, all following tokens belong to the script.
    forwarded = argv[1:] if argv[:1] == ["--"] else argv
    environment = None
    if script.runner == "python":
        environment = os.environ.copy()
        environment.setdefault("PYTHONUTF8", "1")
        environment.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(command + forwarded, cwd=script.cwd, env=environment, shell=False)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode
