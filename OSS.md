# Python OSS 工具

OSS 是 `gd` 工具箱的一个独立模块：`gd oss put` 上传、`gd oss get` 下载、`gd oss ls` 列举。具体示例与安装方法见 [GD.md](GD.md)。原有 `oss_cli.py` 入口和 Python API 继续可用。

可从命令行使用，也能作为 Python 模块集成到其他程序。默认连接你现有的 `smell` Bucket，地域为杭州 `cn-hangzhou`。实现基于阿里云官方 Python SDK V2，Python 最低版本为 3.10。

## 首次使用

先按照 [README.md](README.md) 在仓库根目录创建 `.venv` 并安装 OSS 依赖。在 PowerShell 中运行：

```powershell
Set-Location C:\Users\92416\Documents\woker\gd
.\.venv\Scripts\python.exe oss_cli.py --help
```

默认读取当前用户目录下的 `~/.ossenv`（本机为 `C:\Users\92416\.ossenv`）。首次配置凭证时，将模板复制到该位置，再在本机编辑：

```powershell
$taskOssEnv = Join-Path $env:USERPROFILE '.ossenv'
if (!(Test-Path -LiteralPath $taskOssEnv)) { Copy-Item -LiteralPath .ossenv.example -Destination $taskOssEnv }
notepad $taskOssEnv
```

至少填写下面两个字段。使用已有 RAM 用户（例如已授权的 `smell-oss`）的 AccessKey，而不是浏览器登录密码：

```dotenv
ACCESS_KEY_ID=你的AccessKeyID
ACCESS_KEY_SECRET=你的AccessKeySecret
BUCKET=smell
REGION=cn-hangzhou
```

STS 临时凭证还需填写 `SESSION_TOKEN`。凭证不写入源码，项目也忽略同名凭证文件。也可以在 PowerShell 的当前会话中设置同名环境变量。配置优先级是：**命令行参数 > 环境变量 > 配置文件 > 默认值**。默认配置文件始终是用户目录下的 `.ossenv`，与启动时所在目录无关；指定 `--env-file` 时只读取指定文件，支持 `~` 路径。

```powershell
# 只检查配置，不访问云端，不打印密钥
.\.venv\Scripts\python.exe oss_cli.py config

# 第一次真实连接：只读取文件列表
.\.venv\Scripts\python.exe oss_cli.py list
```

浏览器登录阿里云成功，不代表 Python SDK 已经有访问凭证。凭证由本机用户目录的 `.ossenv` 提供，配置检查只显示是否已配置。

在其他电脑上安装：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 常用操作

每条命令都可以追加 `--json` 输出机器可读结果。以下命令在仓库根目录执行；也可以使用 `python -m oss_toolkit` 替代 `python oss_cli.py`。

### 列举与检索

```powershell
# 默认最多显示 100 项；--limit 0 遍历全部分页
.\.venv\Scripts\python.exe oss_cli.py list --limit 0
.\.venv\Scripts\python.exe oss_cli.py list --prefix "images/" --json

# 关键词匹配完整 Object key（包括路径），默认不区分大小写
.\.venv\Scripts\python.exe oss_cli.py search "文生图"
.\.venv\Scripts\python.exe oss_cli.py search --glob "*.png" --min-size 1MB
.\.venv\Scripts\python.exe oss_cli.py search --prefix "images/" --glob "*.jpg" --after "2026-01-01" --max-size 10MB --limit 0

# 文件详情：大小、MIME、ETag、CRC64、元数据等
.\.venv\Scripts\python.exe oss_cli.py info "文生图_noovle__0001.png"
```

检索是**文件名、路径和属性筛选，不是图片语义搜索或文件全文搜索**。前缀过滤在 OSS 服务端执行，其他条件由程序跨分页筛选；只有命中的结果才计入 `--limit`。对于很大的 Bucket，尽量指定前缀以减少列举请求。`--glob` 匹配完整 Object key，`*.png` 也能匹配子目录中的 PNG。大小的 KB/MB/GB 按 1024 进制；无时区的时间按 UTC，传入 `+08:00` 可以按北京时间筛选。时间上下限均包含边界。

### 上传

```powershell
# 单文件：默认以本地文件名作为 Object key
.\.venv\Scripts\python.exe oss_cli.py upload .\image.png
.\.venv\Scripts\python.exe oss_cli.py upload .\image.png --key "images/image.png"

# 显式允许覆盖同名远端文件
.\.venv\Scripts\python.exe oss_cli.py upload .\image.png --key "images/image.png" --overwrite

# 先查看目录上传计划；dry-run 不需要凭证，也不连接 OSS
.\.venv\Scripts\python.exe oss_cli.py upload-dir .\images --prefix "images/" --dry-run

# 递归上传，保留本地目录的相对路径
.\.venv\Scripts\python.exe oss_cli.py upload-dir .\images --prefix "images/" --exclude "*.tmp"
```

上传目录 `images/sub/a.png` 到前缀 `pictures/`，远端 key 为 `pictures/sub/a.png`，不会额外重复最外层目录名。目录上传默认排除 `.ossenv*`、`.env*`、`.git`、`.venv`、`__pycache__`、`.oss-checkpoints` 和 `.pytest_cache`，并跳过符号链接。空目录不会上传。`--exclude` 可重复指定。

### 下载

```powershell
# 下载你现有的图片；不指定目标时写入 downloads/<Object key>
.\.venv\Scripts\python.exe oss_cli.py download "文生图_noovle__0001.png"
.\.venv\Scripts\python.exe oss_cli.py download "文生图_noovle__0001.png" .\downloads\example.png

# 指定本地文件名并允许覆盖
.\.venv\Scripts\python.exe oss_cli.py download "images/image.png" .\downloads\image.png --overwrite

# 下载一个远端目录，images/sub/a.png 对应 downloads/images/sub/a.png
.\.venv\Scripts\python.exe oss_cli.py download-dir .\downloads\images --prefix "images/"

# 下载整个 Bucket
.\.venv\Scripts\python.exe oss_cli.py download-dir .\downloads

# 只查看下载计划：会查询远端列表，但不下载文件
.\.venv\Scripts\python.exe oss_cli.py download-dir .\downloads --dry-run --json
```

默认避免覆盖已有本地文件。下载先写临时文件，通过 SDK 完整性校验后再发布到最终路径；中断不会用半个文件替换你的原文件。批量下载会拒绝 `../`、绝对路径、Windows 保留文件名等无法安全映射的 key。若 OSS 中确实有这类名称，可使用单文件 `download` 并显式指定合法的本地文件名。

### 临时链接、复制与删除

```powershell
# 私有文件的临时下载链接，默认有效期 300 秒
.\.venv\Scripts\python.exe oss_cli.py url "文生图_noovle__0001.png" --expires 600

# 在当前 Bucket 内复制文件
.\.venv\Scripts\python.exe oss_cli.py copy "images/a.png" "backup/a.png"

# 只删除指定 key，必须显式传入 --yes
.\.venv\Scripts\python.exe oss_cli.py delete "tests/example.txt" --yes
```

链接生成是本地签名操作，不会验证文件是否存在，也不会改变文件权限。有效期最长 7 天；使用 STS 时还受临时凭证自身有效期限制。私有文件通过签名链接访问，默认 OSS 域名通常表现为下载。未开启版本控制时，删除文件通常无法恢复；本工具不提供批量删除或删除 Bucket 功能。

## 在 Python 中调用

在仓库根目录执行你的 Python 文件，或者先运行 `python -m pip install -e ".[oss]"` 安装含 OSS 依赖的工具箱，即可导入：

```python
from datetime import datetime, timezone
from oss_toolkit import OSSManager, Settings

# 自动读取 ~/.ossenv；也可传 Settings.from_env("D:/config/oss.env")
manager = OSSManager()

for item in manager.list_objects(prefix="images/", limit=100):
    print(item.to_dict())

for item in manager.search(
    "文生图", pattern="*.png", min_size=1024,
    after=datetime(2026, 1, 1, tzinfo=timezone.utc),
):
    print(item.key, item.size)

manager.upload("./image.png", "images/image.png")
manager.download("images/image.png", "./downloads/image.png")
print(manager.info("images/image.png"))
print(manager.signed_url("images/image.png", expires=600)["url"])

upload_result = manager.upload_directory("./images", "images/", dry_run=True)
print(upload_result.to_dict())
download_result = manager.download_directory("images/", "./downloads/images")
print(download_result.to_dict())

# 单文件调用失败会抛异常；批量调用将各文件状态和错误放在报告中
if download_result.failures:
    print("部分文件失败，请检查报告后重试。")
```

`example_usage.py` 是一个默认只列举和检索的调用示例。`ObjectInfo` 使用字节表示大小；`last_modified` 为 datetime，`to_dict()` 转换为带时区的 ISO 字符串。`manager.upload(..., metadata={"source": "my-app"})` 可以附加文件元数据。传输进度回调形式为 `(本次字节数, 已传字节数, 总字节数)`。

## 续传、批量结果和配置

- 大文件按分片并发上传/下载，默认每片 8 MB、并发 4。小文件无需分片；小文件失败后会重新传输。
- 断点信息保存在 `code/.oss-checkpoints`。失败会保留已上传分片和下载临时文件；保持文件路径、Object key、源文件内容和 checkpoint 配置不变，重新执行相同命令即可续传。完成后 SDK 自动清理对应断点记录。
- 目录内的文件逐个处理，每个大文件的分片并发传输。批量上传/下载中，同名文件默认标记为 `skipped`，其他文件继续处理；真正失败的文件标记为 `failed`，整条命令返回非零退出码。目录迭代或远端列举失败会直接返回错误，已完成的文件保留。
- 可用 `--overwrite` 显式允许覆盖。远端上传/复制使用 OSS 服务端禁止覆盖参数，避免仅靠本地查询判断同名文件。
- `--json` 时标准输出只包含 JSON，进度和提示写入标准错误。退出码 `0` 表示成功（可包含跳过项）、`1` 表示配置/调用或批量失败、`2` 表示命令行参数错误、`130` 表示用户中断。

| 环境变量 | 默认值 | 作用 |
|---|---|---|
| `BUCKET` | `smell` | 存储空间名称 |
| `REGION` | `cn-hangzhou` | 地域，签名也使用此值 |
| `ENDPOINT` | 留空 | 自动选择地域 HTTPS 节点；可填写自定义完整 URL |
| `USE_CNAME` | `false` | endpoint 是否是已绑定的 Bucket 自定义域名 |
| `WORKERS` | `4` | 单个文件的并发分片数，最大 32 |
| `PART_SIZE_MB` | `8` | 分片大小，1–512 MB |
| `CONNECT_TIMEOUT` | `10` | 连接超时，秒 |
| `READ_TIMEOUT` | `60` | 网络读写超时，秒 |
| `MAX_ATTEMPTS` | `3` | 每次 SDK 请求最多尝试次数，包含第一次请求 |
| `CHECKPOINT_DIR` | `.oss-checkpoints` | 相对路径按本程序目录解析 |

跨地域使用时可以在任何命令前或后传 `--bucket`、`--region` 和 `--endpoint`。同地域 ECS 可按需设置内网 endpoint。自定义域名示例：

```dotenv
ENDPOINT=https://files.example.com
USE_CNAME=true
```

这里填写的是已绑定到 Bucket 的完整域名。部分中国大陆账户的数据访问有 CNAME 要求；若返回相关 AccessDenied，请根据控制台提供的访问域名配置 endpoint，不要关闭 HTTPS 校验或把私有 Bucket 改成公共读。

## 权限、费用与常见问题

列举/检索需要 `oss:ListObjects`；下载和详情需要读取对象权限；上传需要写入权限，大文件续传还涉及分片上传与列举分片权限；复制同时需要源读取和目标写入权限。你目前的 `smell-oss` 已在 Bucket Policy 中获准完全控制 `smell/*`，但真实调用仍应以服务端返回为准。

- `AccessDenied`：核对 RAM 权限、Bucket Policy 和 endpoint；如果只能操作对象但不能列举，单文件访问可能成功而 `list` 失败。
- `InvalidAccessKeyId` / `SignatureDoesNotMatch`：检查凭证、地域和系统时间。
- STS 过期：更新凭证环境变量或 `~/.ossenv`，重启调用程序。
- 归档文件无法直接下载：在控制台恢复文件后再下载。
- 默认同名文件不覆盖：单文件命令报错，目录命令跳过；需要覆盖时使用 `--overwrite`。

真实调用会产生 OSS 对应的请求和存储用量；公网下载可能产生外网流出流量。已有资源包是否抵扣，应以适用地域、存储类型、计费项目及费用中心明细为准。本程序没有调整你的资源包、账户权限或 Bucket 配置。

官方参考：[Python SDK V2](https://github.com/aliyun/alibabacloud-oss-python-sdk-v2)、[预签名链接](https://help.aliyun.com/zh/oss/user-guide/how-to-obtain-the-url-of-a-single-object-or-the-urls-of-multiple-objects)、[流量计费](https://help.aliyun.com/zh/oss/traffic-fees)。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

测试使用本地 HTTP OSS 模拟服务和虚构凭证，运行真实官方 SDK；不会访问你的云账号。覆盖中文文件名、空文件、大小文件传输、分页与条件检索、上传/下载中断后的实际续传、CRC 校验失败、网络重试、同名覆盖保护、目录路径映射、复制、删除确认和配置优先级。
