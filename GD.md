# gd 命令

`gd` 是通用脚本工具箱。核心负责本地脚本管理，功能模块各自处理自己的命令和配置。

## 平台说明

下文的多数终端和路径示例按 **Windows / PowerShell** 编写。Linux 安装和运行命令见 [Linux：准备、运行与移除](#linux准备运行与移除)。

| Windows 脚本 | 用途 |
|---|---|
| `windows/setup.ps1` | 创建或复用 `.venv`、安装依赖和 `gd` 启动器 |
| `windows/run.ps1` | 使用 `.venv\Scripts\python.exe` 执行 Python 命令 |
| `windows/install-gd.ps1` | 更新、迁移或移除 Windows `gd.exe` 启动器 |

下文的 `powershell.exe`、盘符路径和 `.venv\Scripts` 命令适用于 Windows。

Windows 脚本统一放在仓库的 `windows` 目录，按脚本位置定位仓库根目录；虚拟环境仍位于仓库根目录的 `.venv`。相对路径示例从仓库根目录执行。

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

名称使用小写字母、数字、`_`、`-`，以小写字母开头。`oss`、`site` 和管理命令名称已保留。同名注册需要 `--replace` 才会更新。`add` 也可写作 `register`。`list/add/info/remove` 支持 `--json`。

自动识别 `.py`、`.pyw`、`.ps1`、`.sh` 和 Windows `.exe/.com`；Linux/macOS 可直接运行具有执行权限的文件。其他扩展名可通过 `--runner python/powershell/bash/exec` 指定。Windows `.bat/.cmd` 不在支持范围内，可改用 PowerShell 脚本。

新注册或用 `--replace` 更新的 Python 脚本，默认使用 `gd` 所在的本仓库 `.venv`。已有注册保存的解释器路径保持原值；自己的脚本需要其他依赖时可指定解释器：

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

## 站点快速使用

`gd site` 发布 HTML、CSS、JavaScript 和图片等静态文件到已配置的 ChatGPT Site 或自有服务器。站点地址和写入密钥存在当前用户的 `~/.gd/sites.json`，不写入项目源码。本机已配置可用的 `chatgpt` 站点；从仓库根目录可发布 `docs/index.html`：

```powershell
gd site list
gd site publish .\docs --site chatgpt
gd site publish .\index.html --as index.html --site chatgpt
```

新目标使用 `gd site add <名称> --provider chatgpt|self --url <公开地址>` 添加，再运行 `gd site login <名称>` 安全输入该目标的写入密钥。自有服务器还需要 `--root <静态文件目录>`，通过 `gd site serve --site <名称>` 启动本地 HTTP 服务。完整配置、限制与服务端协议见 [SITE.md](SITE.md)。

## OSS 快速使用

`gd oss put` 上传，`gd oss get` 下载，`gd oss ls` 列举。默认操作你现有的杭州 `smell` Bucket，配置读取当前用户目录下的 `~/.ossenv`。你这台 Windows 电脑对应 `C:\Users\92416\.ossenv`，与执行命令时所在目录无关。

本机 APNetwork 路径影响 OSS 连接时，在 `gd oss` 命令加 `--direct-wlan`，只让当前进程的 OSS 请求从 Windows `WLAN` 接口直连。脚本仍使用 OSS 原域名进行 HTTPS 校验，不修改系统路由。例如：

```powershell
gd oss --direct-wlan stat software-ai-news/index.html
gd oss put .\report.html reports/report.html --overwrite --direct-wlan
```

此选项只支持 Windows 和默认 OSS 地域端点；自定义 `ENDPOINT` / `USE_CNAME` 不适用。`config` 与上传 dry-run 不连接 OSS，即使带此选项也不会查询 WLAN。

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

### Linux：准备、运行与移除

需要 Python 3.10+、`venv`、`pip`、Bash。从仓库根目录执行：

```bash
bash linux/setup.sh
.venv/bin/gd --help
.venv/bin/gd list
```

环境位于仓库的 `.venv`；全局入口默认是 `~/.local/bin/gd`，指向 `.venv/bin/gd`。确保 `~/.local/bin` 在 `PATH` 中（必要时在 shell 配置中加入 `export PATH="$HOME/.local/bin:$PATH"`），或直接用 `.venv/bin/gd`。安装器遇到其他项目的 `gd` 会停止；明确迁移时指定原项目路径。

| 选项 | 用途 |
|---|---|
| `--python <命令或路径>` | 创建环境时使用指定的 Python；已有环境仍复用原解释器 |
| `--dev` | 安装完整测试依赖 |
| `--core-only` | 只安装核心，不安装 OSS SDK；不能与 `--dev` 同用 |
| `--no-launcher` | 不更新全局 `gd` 入口 |
| `--install-dir <目录>` | 把全局入口安装在指定目录，默认 `~/.local/bin` |
| `--migrate-from <旧项目路径>` | 显式接管旧项目拥有的入口 |

运行项目 Python，保留参数、工作目录和退出码：

```bash
bash linux/run.sh -m pytest
bash linux/run.sh gd.py list
```

移除全局入口而保留环境、配置与已注册脚本：

```bash
.venv/bin/python linux/install-gd.py --uninstall
```

如果安装时用了 `--install-dir`，移除时也传相同选项。缺失或损坏的 `.venv` 不会被安装脚本自动覆盖；修复或移走后再运行。Linux 上的 `.sh` 用 Bash 执行；无扩展名的可执行文件需要执行权限。PowerShell 脚本需要安装 `pwsh`。

### Windows：准备或更新虚拟环境

需要已安装 Python 3.10+。本机 `gd.exe` 安装在当前用户 Python 的 `Scripts` 目录，启动器绑定本仓库的 `.venv`。源码位于 `C:\Users\92416\Documents\woker\gd`。在 Windows PowerShell 中，从任意目录可运行以下本机准备命令：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\92416\Documents\woker\gd\windows\setup.ps1"
```

脚本自动准备虚拟环境、安装依赖并设置 `gd` 使用环境中的 Python。本机已经准备好，重复执行会复用现有环境。需要同时安装测试依赖时，在命令末尾加 `-Dev`。

以下相对路径示例从仓库根目录执行；准备命令可以简写为 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\setup.ps1`。

`windows/setup.ps1` 可重复执行：已有完整环境会复用，不会删除或重建。创建时优先用 `py -3`，没有启动器时查找 `python`；版本要求 3.10+，也可用 `-Python` 指定创建环境的解释器。已有环境不会因该选项而更换 Python 版本。

| 选项 | 用途 |
|---|---|
| `-Dev` | 安装完整测试依赖 |
| `-CoreOnly` | 仅安装通用核心，不安装 OSS 依赖；不能与 `-Dev` 同用 |
| `-NoLauncher` | 准备环境及本地入口，不更新全局 `gd` |
| `-Python <路径或名称>` | 创建环境时使用指定的 Python |
| `-MigrateFrom <旧项目路径>` | 显式接管该旧项目拥有的全局启动器；不能与 `-NoLauncher` 同用 |

若启动器属于另一项目，默认会停止。明确迁移本机旧 `code` 安装的示例（路径相对当前工作目录解析）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\setup.ps1 -Dev -MigrateFrom ..\code
```

本机迁移已经完成，以后直接运行 `windows/setup.ps1`。旧项目、注册记录和用户 `.ossenv` 保留。环境不完整时脚本会停止并保留目录，修复后重试即可。

只更新已准备好环境的启动器：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\92416\Documents\woker\gd\windows\install-gd.ps1
```

安装器只安装当前项目生成的 `gd` 启动器；无安装清单的同名程序不会被覆盖。`-MigrateFrom` 必须与现有清单中的项目和目标启动器路径匹配，且不能用于卸载其他项目。移动项目后可用该选项显式迁移。上述 `ExecutionPolicy` 参数只用于当前 PowerShell 进程。

## Windows：默认使用项目 Python

`gd ...` 及其默认注册的 Python 脚本使用 `gd/.venv/Scripts/python.exe`，无需激活终端；`--interpreter` 继续优先于默认值。`windows/run.ps1` 将所有参数交给同一解释器，返回 Python 的退出码，不改变调用时的工作目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\run.ps1 -c "import sys; print(sys.executable)"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\run.ps1 -m pytest
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\run.ps1 gd.py oss ls
```

允许执行本地脚本的终端也可简写为 `.\windows\run.ps1 -m pytest`。只准备环境时可直接使用 `.\.venv\Scripts\gd.exe ...`。需要让当前终端的裸 `python` 也选择这个环境时，手动运行 `.\.venv\Scripts\Activate.ps1`；全局系统 Python 的设置不会被准备脚本修改。

## Windows：移除入口

移除全局命令（保留代码、配置和下载文件）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\92416\Documents\woker\gd\windows\install-gd.ps1 -Uninstall
```

不安装全局启动器也可以运行：

```powershell
.\.venv\Scripts\python.exe gd.py oss ls
```

首次真实连接需在本机填写 `~/.ossenv` 中的 OSS AccessKey。`gd oss config` 会显示实际读取的配置路径和凭证是否已配置，不显示密钥。可用 `gd oss --env-file D:\config\my.ossenv ls` 指定其他文件；指定后不会再加载默认文件。配置优先级是命令行参数 > 环境变量 > 配置文件 > 默认值。浏览器登录不会自动提供 SDK 凭证。完整配置、权限及续传说明见 [OSS.md](OSS.md)。
