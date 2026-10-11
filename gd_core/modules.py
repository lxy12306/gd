"""Discover module entry points without importing their dependencies."""

from dataclasses import dataclass, field
from importlib import import_module, metadata
import re

from .errors import GDError

MANAGEMENT_NAMES = frozenset({"add", "register", "list", "ls", "run", "remove", "rm", "info"})


def valid_name(name: str) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9_-]*", name) is not None


@dataclass(frozen=True)
class Module:
    name: str
    description: str
    target: str
    leading_options: dict[str, int] = field(default_factory=dict)

    def invoke(self, argv: list[str]) -> int:
        package, attribute = self.target.split(":", 1)
        try:
            callback = import_module(package)
            for part in attribute.split("."):
                callback = getattr(callback, part)
            if not callable(callback):
                raise GDError(f"模块 {self.name} 的入口不是可调用函数：{self.target}")
            result = callback(argv)
        except ImportError as exc:
            if self.name == "oss" and getattr(exc, "name", "") in {"alibabacloud_oss_v2", "dotenv"}:
                raise GDError('OSS 依赖未安装。请在 code 目录运行：python -m pip install -e ".[oss]"') from exc
            raise GDError(f"模块 {self.name} 加载失败：{exc}") from exc
        except AttributeError as exc:
            raise GDError(f"模块 {self.name} 的入口无效：{self.target}") from exc
        if result is None:
            return 0
        if not isinstance(result, int):
            raise GDError(f"模块 {self.name} 应返回整数退出码或 None。")
        return result


def discover_modules() -> dict[str, Module]:
    modules = {
        "oss": Module(
            "oss", "阿里云 OSS：上传、下载、检索及文件管理", "gd_core.oss:main",
            {"--env-file": 1, "--bucket": 1, "--region": 1, "--endpoint": 1,
             "--cname": 0, "--no-cname": 0, "--json": 0},
        )
    }
    for entry in metadata.entry_points(group="gd.modules"):
        if not valid_name(entry.name) or entry.name in MANAGEMENT_NAMES or entry.name in modules:
            raise GDError(f"扩展模块名称无效或重复：{entry.name}")
        modules[entry.name] = Module(entry.name, "已安装的扩展模块", entry.value)
    return modules


def module_arguments(argv: list[str], modules: dict[str, Module]) -> tuple[Module, list[str]] | None:
    """Pass arguments untouched; also retain legacy flags before `oss`."""
    if argv and argv[0] in modules:
        return modules[argv[0]], argv[1:]
    for module in modules.values():
        index = 0
        while index < len(argv):
            flag, separator, _ = argv[index].partition("=")
            count = module.leading_options.get(flag)
            if count is None or (separator and count == 0):
                break
            index += 1 if separator else 1 + count
        if index > 0 and index < len(argv) and argv[index] == module.name:
            return module, argv[:index] + argv[index + 1:]
    return None
