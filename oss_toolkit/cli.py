"""Chinese CLI for OSSManager."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import json
import re
import sys
import threading
import time

from .config import Settings
from . import config as config_module
from .service import BatchReport, OSSManager, describe_error, iso_date, safe_download_path, upload_plan, valid_key

COMMAND_ALIASES = {
    "list": ["ls"], "upload": ["put"], "download": ["get"],
    "info": ["stat"], "copy": ["cp"], "delete": ["rm"],
    "upload-dir": ["put-dir"], "download-dir": ["get-dir"],
}


def parse_size(value: str) -> int:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|KIB|MIB|GIB|TIB)?", value.strip(), re.IGNORECASE)
    if not match:
        raise argparse.ArgumentTypeError("大小格式示例：1024、500KB、2MB、1GB。")
    unit = (match[2] or "B").upper().replace("IB", "B")
    return int(float(match[1]) * 1024 ** {"B": 0, "KB": 1, "MB": 2, "GB": 3, "TB": 4}[unit])


def parse_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("时间格式示例：2026-01-01 或 2026-01-01T12:00:00+08:00；无时区按 UTC。") from exc


def nonnegative(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是非负整数。") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("不能小于 0。")
    return result


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return str(size)


def terminal_text(value: object) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", lambda match: f"\\x{ord(match[0]):02x}", str(value))


class ConsoleProgress:
    def __init__(self, label: str, enabled: bool):
        self.label = terminal_text(label)
        self.enabled = enabled and sys.stderr.isatty()
        self.last = 0.0
        self.lock = threading.Lock()

    def __call__(self, increment: int, transferred: int, total: int):
        if not self.enabled:
            return
        with self.lock:
            now = time.monotonic()
            if now - self.last < 0.2 and transferred != total:
                return
            self.last = now
            percent = 100 * transferred / total if total > 0 else 100
            print(f"\r{self.label} {percent:6.1f}%  {human_size(transferred)} / {human_size(total)}", end="", file=sys.stderr, flush=True)
            if transferred >= total:
                print(file=sys.stderr)


def add_common(parser: argparse.ArgumentParser, *, child: bool = False) -> None:
    default = argparse.SUPPRESS if child else None
    parser.add_argument("--env-file", default=default, help="指定配置文件（默认当前用户目录下的 ~/.ossenv）")
    parser.add_argument("--bucket", default=default, help="覆盖 Bucket 名称")
    parser.add_argument("--region", default=default, help="覆盖地域，例如 cn-hangzhou")
    parser.add_argument("--endpoint", default=default, help="覆盖完整的 http(s) endpoint")
    parser.add_argument("--cname", action=argparse.BooleanOptionalAction, default=default, help="使用已绑定的自定义 Bucket 域名")
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS if child else False, help="输出 JSON，便于脚本调用")


def build_parser(parser: argparse.ArgumentParser | None = None, *, child: bool = False, required_commands: bool = True, friendly: bool = False) -> argparse.ArgumentParser:
    parser = parser or argparse.ArgumentParser(description="阿里云 OSS 工具：上传、下载、检索和文件管理", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    add_common(parser, child=child)
    commands = parser.add_subparsers(dest="command", required=required_commands, title="命令")

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        aliases = COMMAND_ALIASES.get(name, [])
        primary = aliases[0] if friendly and aliases else name
        names = [name] + aliases
        result = commands.add_parser(primary, aliases=[item for item in names if item != primary], help=help_text, description=help_text, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        add_common(result, child=True)
        return result

    listing = command("list", "分页列举文件")
    listing.add_argument("path_prefix", nargs="?", help="Object key 前缀，也可使用 --prefix")
    listing.add_argument("--prefix", default="", help="服务端 Object key 前缀")
    listing.add_argument("--limit", type=nonnegative, default=100, help="最多显示多少文件；0 表示全部")

    search = command("search", "按文件名、路径、大小和更新时间检索；不搜索文件内容")
    search.add_argument("keyword", nargs="?", default="", help="Object key 包含的关键词")
    search.add_argument("--prefix", default="", help="先按服务端前缀缩小检索范围")
    search.add_argument("--glob", dest="pattern", help="完整 Object key 通配符，例如 '*.png' 或 'images/*'")
    search.add_argument("--min-size", type=parse_size)
    search.add_argument("--max-size", type=parse_size)
    search.add_argument("--after", type=parse_date, help="更新时间下限，含边界")
    search.add_argument("--before", type=parse_date, help="更新时间上限，含边界")
    search.add_argument("--case-sensitive", action="store_true", help="区分大小写")
    search.add_argument("--limit", type=nonnegative, default=100, help="匹配结果数量上限；0 表示全部")

    info = command("info", "查看文件大小、MIME、元数据和 CRC64")
    info.add_argument("key")
    upload = command("upload", "上传文件或目录；默认禁止覆盖远端文件")
    upload.add_argument("file", help="本地文件路径")
    upload.add_argument("remote", nargs="?", help="远端 key 或目录前缀；以 / 结尾时保留本地文件名")
    upload.add_argument("--key", help="Object key；默认使用本地文件名")
    upload.add_argument("--overwrite", action="store_true")
    upload.add_argument("--exclude", action="append", default=[], help="上传目录时额外排除的通配符，可重复使用")
    upload.add_argument("-n", "--dry-run", action="store_true", help="只列出上传计划，不连接 OSS")
    download = command("download", "下载文件或目录，自动断点续传；默认禁止覆盖本地文件")
    download.add_argument("key")
    download.add_argument("destination", nargs="?", help="完整的本地文件路径；默认 downloads/<key>")
    download.add_argument("-o", "--output", help="本地输出文件或目录，也可使用第二个位置参数")
    download.add_argument("-r", "--recursive", action="store_true", help="下载该前缀下的整个目录；key 以 / 结尾时自动启用")
    download.add_argument("-n", "--dry-run", action="store_true", help="目录下载只查询列表并显示计划")
    download.add_argument("--overwrite", action="store_true")

    upload_dir = command("upload-dir", "递归上传目录，保留相对路径；默认跳过 .ossenv、.env、.git、.venv 等")
    upload_dir.add_argument("directory")
    upload_dir.add_argument("--prefix", default="", help="远端目录前缀")
    upload_dir.add_argument("--exclude", action="append", default=[], help="额外排除通配符，可重复使用")
    upload_dir.add_argument("--overwrite", action="store_true")
    upload_dir.add_argument("--dry-run", action="store_true", help="只列出本地上传计划，不连接 OSS")
    download_dir = command("download-dir", "递归下载远端目录；空前缀表示整个 Bucket")
    download_dir.add_argument("directory", help="本地输出目录")
    download_dir.add_argument("--prefix", default="", help="例如 images/；省略则下载整个 Bucket")
    download_dir.add_argument("--overwrite", action="store_true")
    download_dir.add_argument("--dry-run", action="store_true", help="查询远端文件并列出下载计划，不下载")

    url = command("url", "生成私有文件临时下载链接（默认 5 分钟）")
    url.add_argument("key")
    url.add_argument("--expires", type=nonnegative, default=300, help="有效期，单位秒，1–604800")
    copy = command("copy", "在当前 Bucket 内复制文件，不经过本机下载")
    copy.add_argument("source_key")
    copy.add_argument("target_key")
    copy.add_argument("--overwrite", action="store_true")
    delete = command("delete", "删除指定单文件；需 --yes，未开启版本控制时通常无法恢复")
    delete.add_argument("key")
    delete.add_argument("--yes", action="store_true", required=True, help="确认删除指定文件")
    command("config", "检查配置和凭证是否存在，不连接 OSS，不显示密钥")
    return parser


def output(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def configure_console() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def normalize_args(args: argparse.Namespace) -> None:
    args.command = next((name for name, aliases in COMMAND_ALIASES.items() if args.command in aliases), args.command)
    if args.command == "list" and args.path_prefix is not None:
        if args.prefix:
            raise ValueError("前缀只能在位置参数和 --prefix 中选择一种。")
        args.prefix = args.path_prefix
    if args.command == "upload":
        if args.remote is not None and args.key is not None:
            raise ValueError("远端路径只能在位置参数和 --key 中选择一种。")
        source = Path(args.file).expanduser()
        key = args.remote if args.remote is not None else args.key
        if source.is_dir():
            args.command = "upload-dir"
            args.directory = str(source)
            args.prefix = key or ""
        else:
            args.key = (key + source.name) if key and key.endswith("/") else key
    if args.command == "download":
        if args.output is not None and args.destination is not None:
            raise ValueError("输出路径只能在第二个位置参数和 --output 中选择一种。")
        destination = args.output if args.output is not None else args.destination
        if args.recursive or args.key.endswith("/"):
            args.command = "download-dir"
            args.prefix = args.key
            args.directory = destination or "downloads"
        else:
            if args.dry_run:
                raise ValueError("单文件下载不支持 --dry-run；目录下载可使用 -r --dry-run。")
            if destination and (Path(destination).expanduser().is_dir() or destination.endswith(("/", "\\"))):
                name = args.key.rsplit("/", 1)[-1]
                destination = str(safe_download_path(destination, name))
            args.destination = destination


def run(args: argparse.Namespace) -> int:
    try:
        normalize_args(args)
        settings = Settings.from_env(args.env_file, bucket=args.bucket, region=args.region, endpoint=args.endpoint, use_cname=args.cname)
        if args.command == "config":
            import os
            from dataclasses import asdict
            value = asdict(settings)
            value["checkpoint_dir"] = str(value["checkpoint_dir"])
            env_path = Path(args.env_file).expanduser() if args.env_file else config_module.default_env_file()
            value["env_file"] = str(env_path.resolve())
            value["env_file_exists"] = env_path.is_file()
            value["credentials_configured"] = all(os.getenv(name, "").strip() for name in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"))
            value["session_token_configured"] = bool(os.getenv("OSS_SESSION_TOKEN", "").strip())
            output(value)
            return 0
        if args.command == "upload" and args.dry_run:
            source = Path(args.file).expanduser().resolve()
            if not source.is_file():
                raise ValueError(f"上传文件不存在：{source}")
            key = valid_key(args.key if args.key is not None else source.name)
            output(dict(source=str(source), target=key, bucket=settings.bucket, size=source.stat().st_size, status="planned"))
            return 0
        if args.command == "upload-dir" and args.dry_run:
            report = BatchReport([dict(source=str(path), target=key, status="planned") for path, key in upload_plan(args.directory, args.prefix, tuple(args.exclude))])
            output(report.to_dict())
            return 0

        manager = OSSManager(settings)
        if args.command in {"list", "search"}:
            limit = args.limit or None
            if args.command == "list":
                results = manager.list_objects(args.prefix, limit)
            else:
                results = manager.search(args.keyword, prefix=args.prefix, pattern=args.pattern, min_size=args.min_size, max_size=args.max_size,
                                         after=args.after, before=args.before, limit=limit, case_sensitive=args.case_sensitive)
            if args.json:
                objects = [item.to_dict() for item in results]
                output(dict(bucket=manager.bucket, returned=len(objects), limit=limit, objects=objects))
                count = len(objects)
            else:
                print("大小\t更新时间（UTC）\t存储类型\tObject key")
                count = 0
                for item in results:
                    print(f"{human_size(item.size)}\t{iso_date(item.last_modified) or '-'}\t{terminal_text(item.storage_class or '-')}\t{terminal_text(item.key)}")
                    count += 1
                print(f"共显示 {count} 个文件。", file=sys.stderr)
            if limit is not None and count >= limit:
                print("已达到显示上限；使用 --limit 0 遍历全部结果。", file=sys.stderr)
            return 0
        if args.command == "info":
            output(manager.info(args.key))
        elif args.command == "upload":
            output(manager.upload(args.file, args.key, overwrite=args.overwrite, progress=ConsoleProgress("上传", not args.json)))
        elif args.command == "download":
            path = manager.download(args.key, args.destination, overwrite=args.overwrite, progress=ConsoleProgress("下载", not args.json))
            output(dict(key=args.key, file=str(path), size=path.stat().st_size))
        elif args.command in {"upload-dir", "download-dir"}:
            def on_item(item: dict):
                if not args.json:
                    print(f"[{item['status']}] {terminal_text(item['source'])} -> {terminal_text(item['target'])}", file=sys.stderr)
            if args.command == "upload-dir":
                report = manager.upload_directory(args.directory, args.prefix, overwrite=args.overwrite, excludes=tuple(args.exclude), on_item=on_item)
            else:
                report = manager.download_directory(args.prefix, args.directory, overwrite=args.overwrite, dry_run=args.dry_run, on_item=on_item)
            output(report.to_dict())
            return 1 if report.failures else 0
        elif args.command == "url":
            value = manager.signed_url(args.key, args.expires)
            if args.json:
                output(value)
            else:
                print(value["url"])
                print(f"有效期截止：{value['expires_at']}；STS 链接还受临时凭证有效期限制。", file=sys.stderr)
        elif args.command == "copy":
            output(manager.copy(args.source_key, args.target_key, overwrite=args.overwrite))
        elif args.command == "delete":
            output(manager.delete(args.key, confirm=args.yes))
        return 0
    except KeyboardInterrupt:
        print("\n传输已中断。上传/下载可重新运行相同命令续传。", file=sys.stderr)
        return 130
    except Exception as exc:
        error = describe_error(exc)
        if args.json:
            output(dict(ok=False, error=error))
        else:
            print("错误：" + terminal_text(error), file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    configure_console()
    return run(build_parser().parse_args(argv))
