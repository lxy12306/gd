"""Publish static files to a GD-compatible Site or self-hosted HTTP server."""

from __future__ import annotations

import argparse
from getpass import getpass
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import sys
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


EXCLUDED = {".git", ".gd", ".openai", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
MAX_FILE_BYTES = 20 * 1024 * 1024


def config_path(option: str | None) -> Path:
    return Path(option or os.environ.get("GD_SITE_CONFIG") or Path.home() / ".gd" / "sites.json").expanduser().resolve()


def read_config(path: Path) -> dict:
    if not path.exists():
        return {"default": None, "sites": {}}
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or not isinstance(result.get("sites"), dict):
        raise ValueError(f"站点配置格式无效：{path}")
    return result


def save_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".sites-", delete=False) as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
        temporary = Path(file.name)
    try:
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def site_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"https", "http"} or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("站点地址必须是无凭证、查询参数和片段的完整 http(s) URL")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("非本机站点必须使用 HTTPS，以保护写入密钥")
    if parts.path not in {"", "/"}:
        raise ValueError("站点地址目前只支持域名根地址")
    path = parts.path.rstrip("/") + "/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def safe_name(name: str) -> str:
    if "\\" in name or "\x00" in name:
        raise ValueError("站点路径不能包含反斜杠或空字符")
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("站点路径必须是安全的相对路径")
    if parts[0] == "__gd" or any(part.startswith(".") for part in parts):
        raise ValueError("站点路径不能使用保留路径或隐藏文件")
    return "/".join(parts)


def select_site(data: dict, name: str | None) -> tuple[str, dict]:
    selected = name or data.get("default")
    if not selected or selected not in data["sites"]:
        raise ValueError("未配置目标站点；先运行 gd site add")
    return selected, data["sites"][selected]


def publish_files(source: Path, route: str | None) -> list[tuple[str, Path]]:
    source = source.expanduser()
    if source.is_symlink():
        raise ValueError("拒绝发布符号链接")
    source = source.resolve()
    if source.is_file():
        return [(safe_name(route or source.name), source)]
    if not source.is_dir() or route:
        raise ValueError("发布目录不存在，或 --as 只能用于单文件")
    result = []
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if any(part in EXCLUDED or part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"拒绝发布符号链接：{path}")
        if path.is_file():
            result.append((safe_name(relative.as_posix()), path))
    if not result:
        raise ValueError("发布目录中没有可发布文件")
    return sorted(result)


def target_url(base: str, path: str, *, write: bool = False) -> str:
    prefix = "__gd/publish/" if write else ""
    return base + prefix + "/".join(quote(part, safe="") for part in safe_name(path).split("/"))


def request(url: str, method: str, *, token: str | None = None, payload: bytes | None = None,
            content_type: str | None = None):
    headers = {"User-Agent": "gd-site/2.0 (+https://github.com/lxy12306/gd)"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        headers["Content-Type"] = content_type or "application/octet-stream"
        headers["X-GD-SHA256"] = sha256(payload).hexdigest()
    try:
        return urlopen(Request(url, data=payload, headers=headers, method=method), timeout=30)
    except HTTPError as error:
        detail = error.read(240).decode("utf-8", errors="replace").replace("\n", " ")
        raise RuntimeError(f"{method} {url}：HTTP {error.code}；{detail}") from error


def publish(profile: dict, files: list[tuple[str, Path]]) -> list[str]:
    token = profile.get("token")
    if not token:
        raise ValueError("目标站点尚未配置写入密钥；运行 gd site login")
    base = site_url(profile["url"])
    urls = []
    for route, source in files:
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"文件超过 20 MB 上限：{source}")
        payload = source.read_bytes()
        digest = sha256(payload).hexdigest()
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        with request(target_url(base, route, write=True), "PUT", token=token, payload=payload, content_type=mime) as response:
            if response.status not in {200, 201, 204}:
                raise RuntimeError(f"发布失败：HTTP {response.status}，{route}")
        public = target_url(base, route)
        with request(public, "HEAD") as response:
            if response.status != 200 or response.headers.get("X-GD-SHA256") != digest:
                raise RuntimeError(f"发布后回读校验失败：{public}")
        urls.append(public)
    return urls


def serve(profile: dict, *, host: str, port: int) -> None:
    root = Path(profile.get("root") or "").expanduser().resolve()
    if not profile.get("root") or not root.is_dir():
        raise ValueError("自有服务器需要配置已存在的 --root 目录")
    token = profile.get("token")
    if not token:
        raise ValueError("自有服务器需要先运行 gd site login 设置写入密钥")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            print(format % args, file=sys.stderr)

        def route(self):
            raw = unquote(urlsplit(self.path).path)
            writing = raw.startswith("/__gd/publish/")
            if writing:
                raw = raw[len("/__gd/publish/"):]
            else:
                raw = raw.lstrip("/") or "index.html"
            name = safe_name(raw)
            file = (root / Path(*name.split("/"))).resolve()
            if not file.is_relative_to(root):
                raise ValueError("路径超出站点根目录")
            return writing, file

        def respond(self, head=False):
            try:
                writing, file = self.route()
                if writing or not file.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = file.read_bytes() if not head else None
                digest = sha256(file.read_bytes()).hexdigest()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(file.stat().st_size))
                self.send_header("X-GD-SHA256", digest)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if body is not None:
                    self.wfile.write(body)
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)

        def do_GET(self):
            self.respond()

        def do_HEAD(self):
            self.respond(head=True)

        def do_PUT(self):
            from hmac import compare_digest
            try:
                writing, file = self.route()
                if not writing:
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                supplied = self.headers.get("Authorization", "")
                if not compare_digest(supplied, "Bearer " + token):
                    self.send_error(HTTPStatus.UNAUTHORIZED)
                    return
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0 or length > MAX_FILE_BYTES:
                    self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                body = self.rfile.read(length)
                digest = sha256(body).hexdigest()
                if self.headers.get("X-GD-SHA256") != digest:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                file.parent.mkdir(parents=True, exist_ok=True)
                with NamedTemporaryFile("wb", dir=file.parent, delete=False) as output:
                    output.write(body)
                    temporary = Path(output.name)
                temporary.replace(file)
                self.send_response(HTTPStatus.CREATED)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except (ValueError, OSError):
                self.send_error(HTTPStatus.BAD_REQUEST)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"GD 站点服务已启动：{profile['url']}（监听 {host}:{port}）")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gd site", description="发布静态文件到 ChatGPT Site 或自有 HTTP 服务器")
    parser.add_argument("--config", help="本地配置路径，默认 ~/.gd/sites.json")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="在本地配置一个站点")
    add.add_argument("name")
    add.add_argument("--url", required=True, help="站点公开浏览地址")
    add.add_argument("--provider", choices=["chatgpt", "self"], required=True)
    add.add_argument("--root", help="自有服务器的本地文件目录")
    commands.add_parser("list", help="列出本地配置的站点，不显示密钥")
    login = commands.add_parser("login", help="从标准输入保存站点写入密钥")
    login.add_argument("name")
    default = commands.add_parser("default", help="设置默认站点")
    default.add_argument("name")
    publishing = commands.add_parser("publish", help="上传静态文件并回读校验")
    publishing.add_argument("source", help="单个文件或静态文件目录")
    publishing.add_argument("--site", help="站点名称，省略时用默认站点")
    publishing.add_argument("--as", dest="route", help="单文件在站点中的相对路径")
    server = commands.add_parser("serve", help="运行自有静态文件服务器，供反向代理接入")
    server.add_argument("--site", help="站点名称，省略时用默认站点")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        path = config_path(args.config)
        data = read_config(path)
        if args.command == "add":
            if not args.name or not args.name.replace("-", "").replace("_", "").isalnum():
                raise ValueError("站点名称只允许字母、数字、连字符和下划线")
            profile = data["sites"].get(args.name, {})
            url = site_url(args.url)
            if profile.get("url") != url or profile.get("provider") != args.provider:
                profile.pop("token", None)
            profile.update(provider=args.provider, url=url)
            if args.provider == "self":
                if not args.root:
                    raise ValueError("自有服务器须提供 --root")
                profile["root"] = str(Path(args.root).expanduser().resolve())
            else:
                profile.pop("root", None)
            data["sites"][args.name] = profile
            data["default"] = data.get("default") or args.name
            save_config(path, data)
            print(f"已配置站点 {args.name}：{profile['url']}")
        elif args.command == "list":
            for name, profile in sorted(data["sites"].items()):
                print(f"{name}{' *' if name == data.get('default') else ''}\t{profile['provider']}\t{profile['url']}\t{'可写' if profile.get('token') else '缺少写入密钥'}")
        elif args.command == "login":
            _, profile = select_site(data, args.name)
            token = (getpass("站点写入密钥：") if sys.stdin.isatty() else sys.stdin.readline()).strip()
            if len(token) < 24:
                raise ValueError("写入密钥过短或标准输入为空")
            profile["token"] = token
            save_config(path, data)
            print(f"已保存 {args.name} 的本地写入密钥")
        elif args.command == "default":
            select_site(data, args.name)
            data["default"] = args.name
            save_config(path, data)
            print(f"默认站点：{args.name}")
        elif args.command == "publish":
            name, profile = select_site(data, args.site)
            files = publish_files(Path(args.source), args.route)
            urls = publish(profile, files)
            print(f"已发布到 {name}：{len(urls)} 个文件")
            for url in urls:
                print(url)
        elif args.command == "serve":
            _, profile = select_site(data, args.site)
            if profile["provider"] != "self":
                raise ValueError("gd site serve 仅用于自有服务器")
            serve(profile, host=args.host, port=args.port)
        return 0
    except (ValueError, OSError, HTTPError, URLError, RuntimeError) as error:
        print(f"gd site: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
