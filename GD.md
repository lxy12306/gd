# gd 命令

`gd` 是通用脚本工具箱。核心负责本地脚本管理，功能模块各自处理自己的命令和配置。

## 管理自己的脚本

```powershell
gd list
gd add hello C:\Users\92416\Documents\woker\gd\examples\hello.py -d "问候示例"
gd hello --name 张三
gd run hello -- --name 张三
gd hello --help
gd info hello
gd remove hello
```

| 命令 | 含义 |
|---|---|
| `gd list` / `gd ls` | 列出功能模块和已注册脚本 |
| `gd add <名称> <脚本路径>` | 注册脚本；只记录路径，不执行脚本 |
| `gd <名称> [参数...]` | 直接运行脚本，原样转发后续参数 |
| `gd run <名称> [--] [参数...]` | 显式运行脚本或模块 |
| `gd info <名称>` | 查看脚本路径、解释器和工作目录，或模块入口 |
| `gd remove <名称>` / `gd rm <名称>` | 移除注册，保留原脚本文件 |
| `gd --version` | 查看版本 |

名称使用小写字母、数字、`_`、`-`，以小写字母开头。`oss` 和管理命令名称已保留。同名注册需要 `--replace` 才会更新。`add` 也可写作 `register`。`list/add/info/remove` 支持 `--json`。

自动识别 `.py`、`.pyw`、`.ps1`、`.sh` 和 Windows `.exe/.com`；Linux/macOS 可直接运行具有执行权限的文件。其他扩展名可通过 `--runner python/powershell/bash/exec` 指定。Windows `.bat/.cmd` 不在支持范围内，可改用 PowerShell 脚本。

Python 默认使用 `gd` 所在虚拟环境，自己的脚本需要其他依赖时可指定解释器：

```powershell
gd add report D:\scripts\report.py --interpreter D:\report-env\Scripts\python.exe
gd add cleanup D:\scripts\cleanup.ps1
gd add backup D:\scripts\backup.py --cwd D:\work -d "项目备份"
gd add report D:\new\report.py --replace
```

注册时保存绝对路径及解释器位置。默认沿用调用 `gd` 时的工作目录，`--cwd` 可固定目录。脚本在独立进程运行，标准输入、输出和错误直接连接终端，退出码返回给调用者；参数通过列表传给进程。Python 默认采用 UTF-8 输出，已有编码环境变量优先。PowerShell 使用独立进程的 `-ExecutionPolicy Bypass`，不修改系统执行策略；Bash 需要机器上存在可用的 `bash`。

注册目录默认 `~/.gd`（本机 `C:\Users\92416\.gd`），与 OSS 的 `.ossenv` 分开。可设置 `GD_HOME`，或将 `--home` 放在命令前；命令行优先：

```powershell
gd --home D:\gd-tools add hello .\hello.py
gd --home D:\gd-tools hello --name 张三
gd --home D:\gd-tools list --json
```

注册文件损坏时会报错并保留原内容；并行注册通过文件锁和原子替换保存。脚本移动或删除后，`gd list` 标记文件不存在，可用 `gd add ... --replace` 修复路径。

带多级子命令的模块通过 Python `gd.modules` 入口扩展，无需修改核心；见 [MODULES.md](MODULES.md)。

## OSS 快速使用

`gd oss put` 上传，`gd oss get` 下载，`gd oss ls` 列举。默认操作你现有的杭州 `smell` Bucket，配置读取当前用户目录下的 `~/.ossenv`。你这台 Windows 电脑对应 `C:\Users\92416\.ossenv`，与执行命令时所在目录无关。

```powershell
# 上传文件；省略远端路径时使用本地文件名
gd oss put .\image.png

# 上传到 images/，保留文件名
gd oss put .\image.png images/

# 上传并指定远端文件名
gd oss put .\image.png images/new-name.png

# 上传整个目录，保留目录内的相对路径
gd oss put .\photos images/

# 只查看上传计划，不连接 OSS
gd oss put .\photos images/ --dry-run

# 下载单文件；默认写到当前目录下的 downloads/<Object key>
gd oss get images/image.png

# 指定本地文件名，或使用 -o
gd oss get images/image.png .\image.png
gd oss get images/image.png -o .\image.png

# 本地目标是已有目录，或路径以 /、\ 结尾时，自动保留远端文件名
gd oss get images/image.png .\downloads\

# 下载整个远端目录，自动识别末尾的 /
gd oss get images/ .\photos

# 前缀不带 / 时，可以显式指定递归
gd oss get images .\photos -r

# 下载整个 Bucket
gd oss get-dir .\backup

# 列举、检索
gd oss ls
gd oss ls images/ --limit 0
gd oss search 文生图
gd oss search --glob "*.png" --min-size 1MB --after 2026-01-01

# 详情、临时链接、复制和删除
gd oss stat images/image.png
gd oss url images/image.png --expires 600
gd oss cp images/image.png backup/image.png
gd oss rm tests/example.txt --yes

# 配置与帮助
gd oss config
gd oss
gd oss put --help
```

本地文件/目录路径从当前工作目录解析。例如 `gd oss put .\photos images/` 会把 `photos/sub/a.png` 上传为 `images/sub/a.png`；`gd oss get images/ .\photos` 对应下载为 `photos/sub/a.png`。

| 命令 | 含义 |
|---|---|
| `gd oss put <本地路径> [远端路径]` | 上传文件或目录，自动识别本地目录 |
| `gd oss get <远端路径> [本地路径]` | 下载文件；末尾为 `/` 或指定 `-r` 时下载目录 |
| `gd oss ls [前缀]` | 分页列举 |
| `gd oss search [关键词]` | 文件名、路径、大小、更新时间筛选 |
| `gd oss stat <key>` | 文件详情 |
| `gd oss url <key>` | 生成临时下载链接 |
| `gd oss cp <源key> <目标key>` | Bucket 内复制 |
| `gd oss rm <key> --yes` | 删除指定单文件 |
| `gd oss put-dir <目录> --prefix <前缀>` | 显式目录上传，兼容原命令 |
| `gd oss get-dir <本地目录> [--prefix <前缀>]` | 显式目录下载，默认整个 Bucket |

各命令支持 `--json`、`--bucket`、`--region`、`--endpoint`、`--env-file`；这些选项可以放在 `gd` 后、`oss` 后或操作命令后。默认避免覆盖；确实需要覆盖时加 `--overwrite`。批量上传默认跳过 `.env*`、`.git`、`.venv` 等，额外排除使用 `--exclude "*.tmp"`。上传/下载继续使用原工具的并发分片、断点续传、CRC 校验和逐文件结果报告。

## 安装及移除

本机现有 `gd.exe` 安装在当前用户 Python 的 `Scripts` 目录，运行环境来自原来的 `code` 目录。本仓库源码位于 `C:\Users\92416\Documents\woker\gd`。先在仓库根目录创建环境并安装依赖：

```powershell
Set-Location C:\Users\92416\Documents\woker\gd
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[oss]"
```

需要将全局命令切换到本仓库时，先用原安装器移除旧启动器，再安装本仓库的入口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\92416\Documents\woker\code\install-gd.ps1 -Uninstall
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\92416\Documents\woker\gd\install-gd.ps1
```

以后更新本仓库的启动器：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\92416\Documents\woker\gd\install-gd.ps1
```

安装器只安装当前项目生成的 `gd` 启动器；检测到其他同名命令时停止，不覆盖它。启动器绑定安装项目的 `.venv`；移动项目后，应先移除旧启动器，再从新位置重新安装。上述 `ExecutionPolicy` 参数只用于安装进程。

移除全局命令（保留代码、配置和下载文件）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\92416\Documents\woker\gd\install-gd.ps1 -Uninstall
```

不安装启动器也可以运行：

```powershell
.\.venv\Scripts\python.exe gd.py oss ls
```

首次真实连接需在本机填写 `~/.ossenv` 中的 OSS AccessKey。`gd oss config` 会显示实际读取的配置路径和凭证是否已配置，不显示密钥。可用 `gd oss --env-file D:\config\my.ossenv ls` 指定其他文件；指定后不会再加载默认文件。配置优先级是命令行参数 > 环境变量 > 配置文件 > 默认值。浏览器登录不会自动提供 SDK 凭证。完整配置、权限及续传说明见 [OSS.md](OSS.md)。
