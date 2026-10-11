# gd 项目协作说明

本文件适用于整个仓库。修改子目录前，检查该目录是否有更具体的 `AGENTS.md`。用户在当前任务中的指令优先于本文件。

## 项目目标与结构

`gd` 是通用脚本工具箱，OSS 是其中一个功能模块。Python 最低版本为 3.10。

- `gd_core/`：命令分发、模块发现、脚本注册与运行，只依赖 Python 标准库。
- `gd_core/oss.py`：OSS 适配器，实际调用时才导入 OSS 模块。
- `oss_toolkit/`：OSS 命令、配置和官方 SDK 服务。
- `examples/`：可注册的普通脚本示例。
- `tests/`：核心测试，以及官方 SDK 访问本地 HTTP 服务的 OSS 测试。
- `pyproject.toml`：打包、命令入口、可选依赖与测试配置。
- `install-gd.ps1`：Windows 全局启动器的安装、更新和移除。

阅读文档：`README.md` 是入口，`GD.md` 是使用指南，`OSS.md` 介绍 OSS 配置和 Python API，`MODULES.md` 介绍模块扩展。

## 本机源码与运行环境

本仓库位于 `C:\Users\92416\Documents\woker\gd`。现有全局 `gd` 启动器仍使用旁边 `code` 目录的安装环境；修改本仓库不会立即改变那个命令的行为。

开发和验证从本仓库根目录执行，使用明确的 Python 路径和 `python gd.py ...`，避免把旧安装环境的运行结果当成本仓库的结果。优先使用仓库自己的 `.venv`。

创建开发环境：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[oss]"
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

仅开发独立核心时可使用 `python -m pip install -e .`，不安装 OSS 可选依赖。完整测试需要 `requirements-dev.txt`。

本机也可复用已有环境，从本仓库根目录运行：

```powershell
..\code\.venv\Scripts\python.exe gd.py --help
..\code\.venv\Scripts\python.exe -m pytest
```

复用环境时确认 `gd_core.__file__` 指向本仓库。比较解释器或目录身份时先解析实际路径，兼容 Windows 目录链接。

## 开发约定

- 保持核心独立。不要在核心入口、帮助、模块列举或脚本注册过程中导入 OSS SDK 等模块专属依赖。
- 新的多级命令模块通过 `gd.modules` entry point 扩展，入口为 `main(argv) -> int | None`，模块自己解析参数和管理依赖。
- 保持 `gd oss ...`、`oss-tool`、`oss_cli.py`、`python -m oss_toolkit` 和现有 Python API 的兼容性。
- OSS 通用选项仍支持放在 `gd` 后、`oss` 后或具体操作后；保留现有命令别名和覆盖顺序。
- 使用小范围改动解决任务，避免无关重构；不覆盖已有用户改动。
- 不添加项目没有配置的格式化或静态检查工具作为必跑步骤。新增依赖时更新对应配置文件，核心依赖与模块可选依赖保持分离。

## 脚本管理行为

- 注册目录默认 `~/.gd`，注册文件为 `scripts.json`；`--home` 优先于 `GD_HOME`。
- 注册只保存脚本及解释器的绝对路径和元数据，不导入或执行脚本；移除注册保留脚本文件。
- 默认使用调用时的工作目录，只有显式配置 `--cwd` 才固定工作目录。
- 参数使用进程参数列表转发，不拼接 shell 命令；保留空格、中文、前导选项和脚本退出码。
- 保留注册文件锁、原子保存、损坏配置报错且不覆盖原内容的行为。
- 管理命令与模块名称不能被新注册的脚本占用；同名注册需要 `--replace`。

## OSS 配置与传输行为

- 默认读取 `Path.home() / ".ossenv"`，与当前工作目录无关。指定 `--env-file` 时只读取指定文件。
- 用户配置字段保持无前缀形式：`ACCESS_KEY_ID`、`ACCESS_KEY_SECRET`、`SESSION_TOKEN`、`BUCKET`、`REGION` 等；SDK 内部的 `OSS_*` 映射和旧格式兼容应保留。
- 保留配置优先级：命令行参数 > 环境变量 > 配置文件 > 默认值。
- 不将真实凭证写入源码、文档、测试、输出或 Git。模板仅保留示例值；凭证文件、虚拟环境、缓存和传输临时文件继续由 `.gitignore` 排除。
- 保留默认禁止覆盖、断点续传、分片并发、CRC 校验及下载完成后原子发布的行为。
- 保留下载路径检查，拒绝路径穿越和无法安全映射的文件名；批量上传继续排除 `.ossenv`、`.env` 等配置文件。
- 删除 OSS 文件保留现有 `--yes` 要求。真实云端操作按用户任务范围执行，不作为常规自动化测试的一部分。

## 验证方法

代码变更运行相关测试；涉及核心分发、配置兼容、注册或传输流程时运行完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe gd.py --help
.\.venv\Scripts\python.exe gd.py list
```

测试使用临时注册目录、假凭证和本地 OSS HTTP 服务。手动验证脚本注册时通过 `--home` 指定临时目录，避免修改用户默认注册信息。真实 OSS 上传、删除和覆盖不用于验证代码变更。

重点覆盖参数转发、中文和空格路径、独立核心无需 OSS 依赖、注册持久化、损坏配置保护、目录链接、分页及完整性校验。为实际行为和故障编写测试，避免只重复实现细节。

纯文档修改核对命令、文件链接和格式即可。提交前执行 `git diff --check`，有暂存内容时执行 `git diff --cached --check`；检查 `git status` 和差异，确保只包含本任务内容。

## 文档与提交

命令行为、安装方法、模块接口或配置变化时同步更新相应文档。使用指南放在 `GD.md`，面向开发代理的约定放在本文件。

提交信息说明具体变更。不要将凭证、构建结果或用户机器的临时状态放入提交。提交和远程推送根据用户任务范围执行。

本机终端若找不到 `git`，可以使用已安装的完整路径：

```powershell
& 'C:\Users\92416\AppData\Local\Programs\Git\cmd\git.exe' status
```
