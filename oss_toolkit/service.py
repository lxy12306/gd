"""Reusable OSS operations. All object keys are relative to one configured bucket."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterator
import mimetypes
import os
import re

import alibabacloud_oss_v2 as oss

from .config import Settings, require_credentials

Progress = Callable[[int, int, int], None]
DEFAULT_EXCLUDES = (".ossenv*", ".env*", ".git", ".venv", "__pycache__", ".oss-checkpoints", ".pytest_cache")


def utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso_date(value: datetime | None) -> str | None:
    return utc_datetime(value).isoformat() if value else None


def valid_key(key: str) -> str:
    # Do not silently trim whitespace, decode '%' or strip leading '/': they are part of an OSS key.
    if not key or key.endswith("/") or "\x00" in key or len(key.encode("utf-8")) > 1023:
        raise ValueError("请指定非空的文件 Object key，不能以 / 结尾，UTF-8 长度不超过 1023 字节。")
    return key


def directory_prefix(prefix: str) -> str:
    return prefix if not prefix or prefix.endswith("/") else prefix + "/"


def safe_download_path(directory: str | Path, key: str, prefix: str = "") -> Path:
    """Map a remote key to a portable local filename without traversal or normalization collisions."""
    if not key.startswith(prefix):
        raise ValueError(f"文件不属于指定前缀：{key}")
    relative = key[len(prefix):]
    parts = relative.split("/")
    reserved = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)
    for part in parts:
        if (
            part in {"", ".", ".."}
            or part[-1:] in {" ", "."}
            or any(ord(char) < 32 for char in part)
            or any(char in '<>:"\\|?*' for char in part)
            or reserved.match(part)
        ):
            raise ValueError(f"Object key 无法安全映射为本地路径：{key}；请使用单文件下载并显式指定文件名。")
    root = Path(directory).expanduser().resolve()
    candidate = root.joinpath(*parts)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
        raise ValueError(f"下载路径越过目标目录或指向符号链接：{key}")
    return candidate


def upload_plan(directory: str | Path, prefix: str = "", excludes: tuple[str, ...] = ()) -> Iterator[tuple[Path, str]]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"上传目录不存在：{root}")
    prefix = directory_prefix(prefix)
    patterns = DEFAULT_EXCLUDES + tuple(excludes)
    for base, dirs, files in os.walk(root, followlinks=False):
        current = Path(base)
        dirs[:] = sorted(
            name for name in dirs
            if not (current / name).is_symlink()
            and not any(fnmatchcase(name, pattern) or fnmatchcase((current / name).relative_to(root).as_posix(), pattern) for pattern in patterns)
        )
        for name in sorted(files):
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                continue
            if any(fnmatchcase(name, pattern) or fnmatchcase(relative, pattern) for pattern in patterns):
                continue
            yield path, valid_key(prefix + relative)


def service_error(error: Exception) -> oss.exceptions.ServiceError | None:
    current = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, oss.exceptions.ServiceError):
            return current
        unwrap = getattr(current, "unwrap", None)
        current = unwrap() if callable(unwrap) else current.__cause__
    return None


def describe_error(error: Exception) -> str:
    """Do not print SDK exceptions verbatim: they may contain credentials or signed URLs."""
    remote = service_error(error)
    if remote:
        hints = {
            "AccessDenied": "没有访问权限，请检查 RAM 和 Bucket 授权策略。",
            "InvalidAccessKeyId": "AccessKey ID 无效。",
            "SignatureDoesNotMatch": "签名不匹配，请检查密钥、地域和本机时间。",
            "SecurityTokenExpired": "STS 临时凭证已过期，请更新三个凭证环境变量并重新运行。",
            "NoSuchKey": "远端文件不存在。",
            "NoSuchBucket": "Bucket 不存在，请检查 Bucket 名称、地域和 endpoint。",
            "FileAlreadyExists": "远端文件已存在；如需覆盖请显式使用 --overwrite。",
            "ObjectAlreadyExists": "远端文件已存在；如需覆盖请显式使用 --overwrite。",
            "InvalidObjectState": "归档文件尚未解冻，请先在 OSS 控制台恢复后下载。",
            "RequestTimeTooSkewed": "本机时间偏差过大，请同步系统时间。",
        }
        hint = hints.get(remote.code, "OSS 拒绝了请求，请检查权限、endpoint 和服务状态。")
        if remote.code == "AccessDenied" and "cname" in (remote.message or "").lower():
            hint = "该账户需要 CNAME 访问。请配置完整的 ENDPOINT，并设置 USE_CNAME=true。"
        return f"HTTP {remote.status_code} / {remote.code}：{hint} RequestId={remote.request_id or '-'}"
    if isinstance(error, (ValueError, OSError)):
        message = str(error)
        for name in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_SESSION_TOKEN"):
            secret = os.getenv(name, "")
            if secret:
                message = message.replace(secret, "[已隐藏]")
        return message
    return f"OSS 调用失败（{type(error).__name__}），请检查网络、配置和访问凭证。"


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    last_modified: datetime | None
    etag: str | None
    storage_class: str | None

    def to_dict(self) -> dict:
        return dict(key=self.key, size=self.size, last_modified=iso_date(self.last_modified), etag=self.etag, storage_class=self.storage_class)


@dataclass
class BatchReport:
    items: list[dict] = field(default_factory=list)

    @property
    def failures(self) -> int:
        return sum(item["status"] == "failed" for item in self.items)

    def to_dict(self) -> dict:
        return {
            "ok": self.failures == 0,
            "succeeded": sum(item["status"] == "ok" for item in self.items),
            "skipped": sum(item["status"] == "skipped" for item in self.items),
            "planned": sum(item["status"] == "planned" for item in self.items),
            "failed": self.failures,
            "items": self.items,
        }


@contextmanager
def transfer_lock(path: Path):
    """OS releases this advisory lock on process exit, including a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("已有另一个传输进程在操作相同文件，请等待它完成。") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class OSSManager:
    """Read ~/.ossenv via Settings.from_env(), or inject an SDK client for testing."""

    def __init__(self, settings: Settings | None = None, *, client: oss.Client | None = None):
        self.settings = settings or Settings.from_env()
        self.settings.validate()
        if client is None:
            require_credentials()
            cfg = oss.config.load_default()
            cfg.region = self.settings.region
            cfg.endpoint = self.settings.endpoint
            cfg.use_cname = self.settings.use_cname
            cfg.credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()
            cfg.connect_timeout = self.settings.connect_timeout
            cfg.readwrite_timeout = self.settings.read_timeout
            cfg.retry_max_attempts = self.settings.max_attempts
            cfg.user_agent = "smell-oss-toolkit/1.0.0"
            client = oss.Client(cfg)
        self.client = client

    @property
    def bucket(self) -> str:
        return self.settings.bucket

    def list_objects(self, prefix: str = "", limit: int | None = None) -> Iterator[ObjectInfo]:
        """Iterate every page; limit counts returned files, not pages."""
        if limit is not None and limit < 0:
            raise ValueError("limit 不能小于 0。")
        if limit == 0:
            return
        count = 0
        paginator = self.client.list_objects_v2_paginator()
        for page in paginator.iter_page(oss.ListObjectsV2Request(bucket=self.bucket, prefix=prefix, max_keys=1000)):
            for item in page.contents or ():
                yield ObjectInfo(item.key, item.size or 0, item.last_modified, item.etag, item.storage_class)
                count += 1
                if limit is not None and count >= limit:
                    return

    def search(self, keyword: str = "", *, prefix: str = "", pattern: str | None = None,
               min_size: int | None = None, max_size: int | None = None,
               after: datetime | None = None, before: datetime | None = None,
               limit: int | None = None, case_sensitive: bool = False) -> Iterator[ObjectInfo]:
        if min_size is not None and min_size < 0 or max_size is not None and max_size < 0:
            raise ValueError("文件大小不能为负数。")
        if min_size is not None and max_size is not None and min_size > max_size:
            raise ValueError("最小文件大小不能超过最大文件大小。")
        if after and before and utc_datetime(after) > utc_datetime(before):
            raise ValueError("after 不能晚于 before。")
        if limit is not None and limit < 0:
            raise ValueError("limit 不能小于 0。")
        if limit == 0:
            return
        count = 0
        needle = keyword if case_sensitive else keyword.casefold()
        for item in self.list_objects(prefix):
            key = item.key if case_sensitive else item.key.casefold()
            if item.key.endswith("/") or needle not in key:
                continue
            if pattern and not fnmatchcase(key, pattern if case_sensitive else pattern.casefold()):
                continue
            if min_size is not None and item.size < min_size or max_size is not None and item.size > max_size:
                continue
            modified = utc_datetime(item.last_modified) if item.last_modified else None
            if after and (modified is None or modified < utc_datetime(after)):
                continue
            if before and (modified is None or modified > utc_datetime(before)):
                continue
            yield item
            count += 1
            if limit is not None and count >= limit:
                return

    def info(self, key: str) -> dict:
        result = self.client.head_object(oss.HeadObjectRequest(bucket=self.bucket, key=valid_key(key)))
        return dict(bucket=self.bucket, key=key, size=result.content_length,
                    content_type=result.content_type, last_modified=iso_date(result.last_modified),
                    etag=result.etag, storage_class=result.storage_class, metadata=result.metadata or {},
                    crc64=result.hash_crc64, version_id=result.version_id, encryption=result.server_side_encryption)

    def upload(self, local_file: str | Path, key: str | None = None, *, overwrite: bool = False,
               progress: Progress | None = None, metadata: dict[str, str] | None = None) -> dict:
        source = Path(local_file).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"上传文件不存在：{source}")
        key = valid_key(source.name if key is None else key)
        if not overwrite and self.client.is_object_exist(self.bucket, key):
            raise FileExistsError(f"远端文件已存在：{key}；如需覆盖请使用 --overwrite。")
        self.settings.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        identity = sha256(f"{self.settings.endpoint}|{self.bucket}|{key}".encode()).hexdigest()
        with transfer_lock(self.settings.checkpoint_dir / "locks" / f"upload-{identity}.lock"):
            result = self.client.uploader(
                part_size=self.settings.part_size, parallel_num=self.settings.workers,
                enable_checkpoint=True, checkpoint_dir=str(self.settings.checkpoint_dir),
            ).upload_file(oss.PutObjectRequest(
                bucket=self.bucket, key=key, forbid_overwrite=not overwrite,
                content_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                metadata=metadata, progress_fn=progress,
            ), str(source))
        return dict(bucket=self.bucket, key=key, size=source.stat().st_size, etag=result.etag, crc64=result.hash_crc64)

    def download(self, key: str, destination: str | Path | None = None, *, overwrite: bool = False,
                 progress: Progress | None = None) -> Path:
        key = valid_key(key)
        target = Path(destination).expanduser().absolute() if destination is not None else safe_download_path("downloads", key)
        if target.is_symlink():
            raise ValueError(f"拒绝将下载结果写入符号链接：{target}")
        if target.exists() and (not overwrite or not target.is_file()):
            raise FileExistsError(f"本地目标已存在：{target}；如需覆盖请使用 --overwrite。")
        target.parent.mkdir(parents=True, exist_ok=True)
        identity = sha256(str(target.resolve()).encode()).hexdigest()
        with transfer_lock(self.settings.checkpoint_dir / "locks" / f"download-{identity}.lock"):
            if target.exists() and not overwrite:
                raise FileExistsError(f"本地目标已存在：{target}")
            # A stable staging path lets the SDK resume; the user's destination is published only on success.
            object_identity = sha256(f"{self.settings.endpoint}|{self.bucket}|{key}".encode()).hexdigest()[:16]
            staging = target.with_name(f".{target.name}.{object_identity}.oss-part")
            if staging.is_symlink() or Path(str(staging) + ".temp").is_symlink():
                raise ValueError("下载临时文件不能是符号链接。")
            self.client.downloader(
                part_size=self.settings.part_size, parallel_num=self.settings.workers,
                enable_checkpoint=True, checkpoint_dir=str(self.settings.checkpoint_dir),
                use_temp_file=True, verify_data=True,
            ).download_file(oss.GetObjectRequest(bucket=self.bucket, key=key, progress_fn=progress), str(staging))
            if overwrite:
                os.replace(staging, target)
            else:
                # os.rename refuses an existing destination on Windows; a hard link provides atomic no-clobber on Unix.
                if os.name == "nt":
                    os.rename(staging, target)
                else:
                    os.link(staging, target)
                    staging.unlink()
        return target

    def upload_directory(self, directory: str | Path, prefix: str = "", *, overwrite: bool = False,
                         excludes: tuple[str, ...] = (), dry_run: bool = False,
                         on_item: Callable[[dict], None] | None = None) -> BatchReport:
        report = BatchReport()
        for source, key in upload_plan(directory, prefix, excludes):
            item = dict(source=str(source), target=key, status="planned" if dry_run else "ok")
            if not dry_run:
                try:
                    self.upload(source, key, overwrite=overwrite)
                except FileExistsError as exc:
                    item.update(status="skipped", error=describe_error(exc))
                except Exception as exc:
                    remote = service_error(exc)
                    item.update(status="skipped" if remote and remote.code in {"FileAlreadyExists", "ObjectAlreadyExists"} else "failed", error=describe_error(exc))
            report.items.append(item)
            if on_item:
                on_item(item)
        return report

    def download_directory(self, prefix: str, directory: str | Path, *, overwrite: bool = False,
                           dry_run: bool = False, on_item: Callable[[dict], None] | None = None) -> BatchReport:
        prefix = directory_prefix(prefix)
        report = BatchReport()
        seen: set[str] = set()
        for obj in self.list_objects(prefix):
            if obj.key.endswith("/"):
                continue
            item = dict(source=obj.key, target="", status="planned" if dry_run else "ok")
            try:
                target = safe_download_path(directory, obj.key, prefix)
                item["target"] = str(target)
                identity = os.path.normcase(str(target))
                if identity in seen:
                    raise ValueError(f"多个 Object key 映射到相同本地文件：{target}")
                seen.add(identity)
                if not dry_run:
                    self.download(obj.key, target, overwrite=overwrite)
            except FileExistsError as exc:
                item.update(status="skipped", error=describe_error(exc))
            except Exception as exc:
                item.update(status="failed", error=describe_error(exc))
            report.items.append(item)
            if on_item:
                on_item(item)
        return report

    def signed_url(self, key: str, expires: int = 300) -> dict:
        if not 1 <= expires <= 604800:
            raise ValueError("链接有效期范围为 1–604800 秒（最多 7 天）。")
        result = self.client.presign(oss.GetObjectRequest(bucket=self.bucket, key=valid_key(key)), expires=timedelta(seconds=expires))
        return dict(url=result.url, method=result.method, expires_at=iso_date(result.expiration), signed_headers=dict(result.signed_headers or {}))

    def copy(self, source_key: str, target_key: str, *, overwrite: bool = False) -> dict:
        source_key, target_key = valid_key(source_key), valid_key(target_key)
        if source_key == target_key:
            raise ValueError("源文件和目标文件不能相同。")
        result = self.client.copier().copy(oss.CopyObjectRequest(
            bucket=self.bucket, key=target_key, source_bucket=self.bucket, source_key=source_key,
            forbid_overwrite=not overwrite,
        ))
        return dict(bucket=self.bucket, source=source_key, key=target_key, etag=result.etag)

    def delete(self, key: str, *, confirm: bool = False) -> dict:
        if not confirm:
            raise ValueError("删除需显式传入 confirm=True；命令行使用 --yes。只支持单文件删除。")
        self.client.delete_object(oss.DeleteObjectRequest(bucket=self.bucket, key=valid_key(key)))
        return dict(bucket=self.bucket, key=key, deleted=True)
