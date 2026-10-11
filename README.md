# gd 通用脚本工具箱

`gd` 是统一命令入口，负责管理本地脚本和加载功能模块。OSS 是其中一个模块，继续使用 `gd oss put/get/ls/search`。核心只使用 Python 标准库；查看帮助、管理脚本和运行自定义脚本无需 OSS SDK 或云端凭证。

## 快速使用

```powershell
# 查看模块和自己的脚本
gd list

# 注册 Python 脚本，以后从任何目录调用
gd add hello C:\Users\92416\Documents\woker\gd\examples\hello.py -d "问候示例"
gd hello --name 张三
gd run hello -- --name 张三

# 查看详情、更新注册、移除注册
gd info hello
gd add hello D:\scripts\hello.py --replace
gd remove hello

# OSS 模块
gd oss ls
gd oss put .\image.png images/
gd oss get images/image.png .\image.png
gd oss search 文生图
```

注册信息保存在 `~/.gd/scripts.json`，脚本保留在原位置。移除注册只删除名称与路径的关联。OSS 默认读取 `~/.ossenv`，字段保持 `ACCESS_KEY_ID`、`ACCESS_KEY_SECRET` 等无前缀形式。

## 安装（Windows）

在仓库根目录准备环境并安装全局命令（Windows，Python 3.10+）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本会创建或复用本仓库的 `.venv`，安装项目和 OSS 依赖，检查环境，再安装绑定该环境的 `gd` 启动器。以后从任意目录执行 `gd ...` 都使用 `.venv` 中的 Python，不需要激活环境。本机已从原来的 `code` 安装迁移到本仓库。

`setup.ps1`、`run.ps1` 和 `install-gd.ps1` 是 Windows 脚本，本文的 `powershell.exe` 及 `.venv\Scripts` 示例对应 Windows；其他系统的环境安装需使用其对应的解释器路径和部署方式。

开发环境加 `-Dev`；仅需核心加 `-CoreOnly`；只准备环境、不安装全局命令加 `-NoLauncher`。完整用法、显式迁移和解释器选择见 [GD.md](GD.md#安装及移除)。

Windows 上的 Python 命令通过 `run.ps1` 执行，默认使用本仓库的解释器并保留当前工作目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -c "import sys; print(sys.executable)"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 gd.py list
```

需要在当前终端直接输入 `python` 时，可手动激活 `.\.venv\Scripts\Activate.ps1`。`gd` 和 `run.ps1` 自己选择项目解释器，不依赖终端激活状态。

## 项目结构

```text
gd_core/                 通用核心：命令分发、模块发现、注册文件、脚本运行
  cli.py                 gd 的全局入口
  modules.py             模块目录与 gd.modules 扩展入口
  registry.py            用户脚本注册，文件锁与原子保存
  scripts.py             Python / PowerShell / Bash / 可执行文件
  oss.py                 按需加载 OSS 的适配器
oss_toolkit/             OSS 配置、命令与 SDK 服务
examples/hello.py        可注册的普通脚本示例
tests/                   核心测试与基于真实 SDK 的本地 OSS 测试
```

普通脚本无需修改核心即可添加。带多级子命令的功能模块通过 `gd.modules` Python entry point 扩展，入口约定为 `main(argv) -> int | None`。

使用详解见 [GD.md](GD.md)，OSS 配置和 Python API 见 [OSS.md](OSS.md)，模块开发见 [MODULES.md](MODULES.md)。

开发代理和协作约定见 [AGENTS.md](AGENTS.md)。

## 验证（Windows）

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Dev
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -m pytest
```

测试隔离用户注册目录及 OSS 凭证；OSS 测试由官方 SDK 访问本地 HTTP 测试服务，不修改真实 Bucket。
