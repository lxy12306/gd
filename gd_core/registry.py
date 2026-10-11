"""Per-user script metadata, with locked, atomic updates."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile

from .errors import GDError
from .modules import MANAGEMENT_NAMES, valid_name


@dataclass(frozen=True)
class Script:
    path: str
    runner: str
    interpreter: str | None = None
    description: str = ""
    cwd: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> "Script":
        if not isinstance(value, dict):
            raise ValueError("脚本记录必须是对象")
        script = cls(**value)
        if not isinstance(script.path, str) or not Path(script.path).is_absolute():
            raise ValueError("脚本路径必须是绝对路径")
        if script.runner not in {"python", "powershell", "bash", "exec"}:
            raise ValueError("脚本类型无效")
        if not isinstance(script.description, str):
            raise ValueError("脚本说明必须是字符串")
        for path in (script.interpreter, script.cwd):
            if path is not None and (not isinstance(path, str) or not Path(path).is_absolute()):
                raise ValueError("解释器和工作目录必须是绝对路径")
        if script.runner != "exec" and script.interpreter is None:
            raise ValueError("缺少脚本解释器")
        return script


class Registry:
    def __init__(self, home: str | Path | None = None):
        selected = home if home is not None else os.environ.get("GD_HOME")
        self.home = Path(selected).expanduser().resolve() if selected else Path.home() / ".gd"
        self.path = self.home / "scripts.json"

    def load(self) -> dict[str, Script]:
        try:
            payload = self.path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return {}
        try:
            value = json.loads(payload)
            if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("scripts"), dict):
                raise ValueError("不支持的注册文件格式")
            scripts = {}
            for name, record in value["scripts"].items():
                if not valid_name(name) or name in MANAGEMENT_NAMES:
                    raise ValueError(f"无效的脚本名称：{name}")
                scripts[name] = Script.from_dict(record)
            return scripts
        except (ValueError, TypeError) as exc:
            raise GDError(f"注册文件无效：{self.path}（{exc}）。请修复该文件后重试。") from exc

    @contextmanager
    def _locked(self):
        self.home.mkdir(parents=True, exist_ok=True)
        with (self.home / "scripts.lock").open("a+b") as lock:
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _save(self, scripts: dict[str, Script]) -> None:
        data = {"version": 1, "scripts": {name: asdict(script) for name, script in sorted(scripts.items())}}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.home,
                                             prefix="scripts-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def add(self, name: str, script: Script, *, reserved: set[str], replace: bool = False) -> None:
        if not valid_name(name):
            raise GDError("名称必须以小写字母开头，仅包含小写字母、数字、下划线或连字符。")
        if name in MANAGEMENT_NAMES or name in reserved:
            raise GDError(f"名称已被管理命令或模块占用：{name}")
        with self._locked():
            scripts = self.load()
            if name in scripts and not replace:
                raise GDError(f"脚本 {name} 已注册；更新时添加 --replace。")
            scripts[name] = script
            self._save(scripts)

    def remove(self, name: str) -> Script:
        with self._locked():
            scripts = self.load()
            if name not in scripts:
                raise GDError(f"未注册脚本：{name}")
            removed = scripts.pop(name)
            self._save(scripts)
            return removed
