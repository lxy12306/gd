"""Configuration without embedding credentials in source code."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import os

from dotenv import dotenv_values

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_NAMES = (
    "ACCESS_KEY_ID", "ACCESS_KEY_SECRET", "SESSION_TOKEN", "BUCKET", "REGION",
    "ENDPOINT", "USE_CNAME", "WORKERS", "PART_SIZE_MB", "CONNECT_TIMEOUT",
    "READ_TIMEOUT", "MAX_ATTEMPTS", "CHECKPOINT_DIR",
)


def default_env_file() -> Path:
    return Path.home() / ".ossenv"


def _load_env(path: Path) -> None:
    """Expose bare file keys to the SDK's native OSS_* environment names internally."""
    fields = {name.upper(): value for name, value in dotenv_values(path, encoding="utf-8-sig").items()}
    for name in CONFIG_NAMES:
        sdk_name = "OSS_" + name
        if sdk_name in os.environ:
            continue
        value = os.environ.get(name) if name in os.environ else fields.get(name, fields.get(sdk_name))
        if value is not None:
            os.environ[sdk_name] = value


def _positive_int(name: str, default: int, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name.removeprefix('OSS_')} 必须是整数。") from exc
    if value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{name.removeprefix('OSS_')} 必须大于 0" + (f" 且不超过 {maximum}。" if maximum else "。"))
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"{name.removeprefix('OSS_')} 请填写 true 或 false。")
    return raw in {"true", "1", "yes"}


@dataclass(frozen=True)
class Settings:
    bucket: str = "smell"
    region: str = "cn-hangzhou"
    endpoint: str | None = None
    use_cname: bool = False
    workers: int = 4
    part_size: int = 8 * 1024 * 1024
    connect_timeout: int = 10
    read_timeout: int = 60
    max_attempts: int = 3
    checkpoint_dir: Path = PROJECT_DIR / ".oss-checkpoints"

    @classmethod
    def from_env(cls, env_file: str | Path | None = None, **overrides) -> "Settings":
        path = Path(env_file).expanduser() if env_file else default_env_file()
        if env_file and not path.is_file():
            raise ValueError(f"配置文件不存在：{path}")
        _load_env(path)
        checkpoint = Path(os.getenv("OSS_CHECKPOINT_DIR", ".oss-checkpoints"))
        if not checkpoint.is_absolute():
            checkpoint = PROJECT_DIR / checkpoint
        values = dict(
            bucket=os.getenv("OSS_BUCKET", "smell").strip(),
            region=os.getenv("OSS_REGION", "cn-hangzhou").strip(),
            endpoint=os.getenv("OSS_ENDPOINT", "").strip() or None,
            use_cname=_boolean("OSS_USE_CNAME"),
            workers=_positive_int("OSS_WORKERS", 4, 32),
            part_size=_positive_int("OSS_PART_SIZE_MB", 8, 512) * 1024 * 1024,
            connect_timeout=_positive_int("OSS_CONNECT_TIMEOUT", 10),
            read_timeout=_positive_int("OSS_READ_TIMEOUT", 60),
            max_attempts=_positive_int("OSS_MAX_ATTEMPTS", 3, 10),
            checkpoint_dir=checkpoint,
        )
        values.update({key: value for key, value in overrides.items() if value is not None})
        result = cls(**values)
        result.validate()
        return result

    def validate(self) -> None:
        if not self.bucket or not self.region:
            raise ValueError("BUCKET 和 REGION 不能为空。")
        if self.use_cname and not self.endpoint:
            raise ValueError("启用 USE_CNAME 时必须设置 ENDPOINT。")
        if self.endpoint:
            endpoint = urlsplit(self.endpoint)
            if endpoint.scheme not in {"https", "http"} or not endpoint.hostname:
                raise ValueError("ENDPOINT 必须是完整的 http(s) URL。")
            if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in {"", "/"}:
                raise ValueError("ENDPOINT 只填写域名和可选端口，不能包含凭证、路径或查询参数。")
        if not 1 <= self.workers <= 32 or not 1 <= self.max_attempts <= 10:
            raise ValueError("并发数范围为 1–32，重试次数范围为 1–10。")
        if self.part_size < 1024 * 1024 or self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("分片大小至少为 1 MB，超时必须大于 0。")


def require_credentials() -> None:
    names = ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET")
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise ValueError(
            "尚未配置 " + "、".join(name.removeprefix("OSS_") for name in missing)
            + f"。请在默认配置文件 {default_env_file()} 或 --env-file 指定的文件中填写已有 RAM 用户的 AccessKey；"
            "也可以使用环境变量。浏览器登录状态不能代替 SDK 凭证。"
        )
