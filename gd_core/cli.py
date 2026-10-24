"""General-purpose gd dispatch and script management; standard library only."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys

from . import __version__
from .errors import GDError
from .modules import MANAGEMENT_NAMES, Module, discover_modules, module_arguments
from .registry import Registry
from .scripts import prepare_script, run_script


def configure_console() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def display(value: object) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", lambda match: f"\\x{ord(match[0]):02x}", str(value))


def output(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser(modules: dict[str, Module]) -> argparse.ArgumentParser:
    module_help = "\n".join(f"  gd {name:<12} {module.description}" for name, module in sorted(modules.items()))
    parser = argparse.ArgumentParser(
        prog="gd", description="gd 通用脚本工具箱：管理本地脚本，按需加载功能模块",
        epilog=f"功能模块：\n{module_help}\n\n直接运行：gd <脚本名称> [参数...]\n示例：gd add hello ./hello.py\n      gd hello --name 世界\n      gd oss put image.png images/\n      gd oss ls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--home", help="注册目录（默认 ~/.gd，也可设置 GD_HOME；放在命令前）")
    parser.add_argument("--version", action="version", version=f"gd {__version__}")
    commands = parser.add_subparsers(dest="command", title="脚本管理")
    listing = commands.add_parser("list", aliases=["ls"], help="列出模块与已注册脚本")
    listing.add_argument("--json", action="store_true")
    add = commands.add_parser("add", aliases=["register"], help="注册脚本；只记录路径，不执行脚本")
    add.add_argument("name")
    add.add_argument("path")
    add.add_argument("--description", "-d", default="", help="脚本用途说明")
    add.add_argument("--runner", choices=["auto", "python", "powershell", "bash", "exec"], default="auto")
    add.add_argument("--interpreter", help="解释器名称或完整路径，例如另一个虚拟环境的 Python")
    add.add_argument("--cwd", help="固定运行目录；省略则沿用调用 gd 时的目录")
    add.add_argument("--replace", action="store_true", help="更新同名脚本注册")
    add.add_argument("--json", action="store_true")
    run = commands.add_parser("run", help="运行脚本或模块，其余参数原样转发")
    run.add_argument("name")
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    remove = commands.add_parser("remove", aliases=["rm"], help="移除注册，保留脚本文件")
    remove.add_argument("name")
    remove.add_argument("--json", action="store_true")
    info = commands.add_parser("info", help="查看模块或脚本详情")
    info.add_argument("name")
    info.add_argument("--json", action="store_true")
    return parser


def global_arguments(argv: list[str], parser: argparse.ArgumentParser) -> tuple[str | None, list[str]]:
    home = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token.startswith("--home="):
            home = token.partition("=")[2]
            index += 1
        elif token == "--home":
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                parser.error("--home 需要指定目录。")
            home = argv[index + 1]
            index += 2
        else:
            break
        if not home:
            parser.error("--home 不能为空。")
    return home, argv[index:]


def script_record(name, script):
    return {"name": name, "type": "script", **asdict(script),
            "status": "ready" if Path(script.path).is_file() else "missing"}


def module_record(module):
    return {"name": module.name, "type": "module", "description": module.description, "target": module.target}


def invoke(name: str, argv: list[str], modules: dict[str, Module], registry: Registry) -> int:
    if name in modules:
        return modules[name].invoke(argv[1:] if argv[:1] == ["--"] else argv)
    scripts = registry.load()
    if name not in scripts:
        raise GDError(f"找不到脚本或模块：{name}。使用 gd list 查看，或 gd add 注册脚本。")
    return run_script(scripts[name], argv)


def main(argv: list[str] | None = None) -> int:
    configure_console()
    try:
        modules = discover_modules()
        parser = build_parser(modules)
        home, arguments = global_arguments(list(sys.argv[1:] if argv is None else argv), parser)
        if not arguments:
            parser.print_help()
            return 0
        module_call = module_arguments(arguments, modules)
        if module_call:
            module, forwarded = module_call
            return module.invoke(forwarded)
        registry = Registry(home)
        if arguments[0] not in MANAGEMENT_NAMES and not arguments[0].startswith("-"):
            return invoke(arguments[0], arguments[1:], modules, registry)
        args = parser.parse_args(arguments)
        if args.command in {"run"}:
            return invoke(args.name, args.arguments, modules, registry)
        if args.command in {"add", "register"}:
            script = prepare_script(args.path, runner=args.runner, interpreter=args.interpreter,
                                    description=args.description, cwd=args.cwd)
            registry.add(args.name, script, reserved=set(modules), replace=args.replace)
            if args.json:
                output(script_record(args.name, script))
            else:
                print(f"已注册：{args.name} → {display(script.path)}\n运行：gd {args.name} [参数...]")
        elif args.command in {"remove", "rm"}:
            script = registry.remove(args.name)
            if args.json:
                output({"removed": args.name, "path": script.path})
            else:
                print(f"已移除注册：{args.name}；脚本文件保留在 {display(script.path)}")
        elif args.command in {"list", "ls"}:
            scripts = registry.load()
            values = {"modules": [module_record(modules[name]) for name in sorted(modules)],
                      "scripts": [script_record(name, scripts[name]) for name in sorted(scripts)],
                      "registry": str(registry.path)}
            if args.json:
                output(values)
            else:
                for value in values["modules"]:
                    print(f"[模块] {value['name']:<16} {display(value['description'])}")
                for value in values["scripts"]:
                    status = "（文件不存在）" if value["status"] == "missing" else ""
                    print(f"[脚本] {value['name']:<16} {display(value['description'] or value['path'])}{status}")
                if not scripts:
                    print("尚未注册本地脚本。使用 gd add <名称> <文件路径> 添加。")
        elif args.command == "info":
            if args.name in modules:
                value = module_record(modules[args.name])
            else:
                scripts = registry.load()
                if args.name not in scripts:
                    raise GDError(f"未注册脚本：{args.name}")
                value = script_record(args.name, scripts[args.name])
            if args.json:
                output(value)
            else:
                for key, item in value.items():
                    if item is not None:
                        print(f"{key}: {display(item)}")
        return 0
    except (GDError, OSError, ValueError) as exc:
        print(f"gd: {display(exc)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ngd: 已中断。", file=sys.stderr)
        return 130
