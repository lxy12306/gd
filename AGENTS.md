# gd 项目协作说明

本文件供开发代理使用，适用于整个仓库。修改子目录前，检查该目录是否有更具体的 `AGENTS.md`。用户在当前任务中的指令优先于本文件。

## 项目目标与结构

`gd` 是通用脚本工具箱，OSS 和静态站点发布是其中两个功能模块。Python 最低版本为 3.10。

- `gd_core/`：命令分发、模块发现、脚本注册与运行，只依赖 Python 标准库。
- `gd_core/oss.py`：OSS 适配器，实际调用时才导入 OSS 模块。
- `oss_toolkit/`：OSS 命令、配置和基于官方 SDK 的服务封装。
- `gd_core/site.py`：基于标准库的静态站点发布与本地 HTTP 服务；站点地址和写入密钥放在用户本地 `~/.gd/sites.json`。
- `examples/`：可注册的普通脚本示例。
- `tests/`：核心测试，以及官方 SDK 访问本地 HTTP 服务的 OSS 测试。
- `pyproject.toml`：打包、命令入口、可选依赖与测试配置。
- `windows/`：Windows 平台入口；脚本定位父目录作为仓库根目录，环境位于根目录 `.venv`。
- `windows/install-gd.ps1`：Windows 全局启动器的安装、更新和移除。
- `windows/setup.ps1`：Windows 下创建或复用项目虚拟环境、安装依赖并准备命令入口。
- `windows/run.ps1`：Windows 下统一使用本仓库 `.venv` 执行 Python 命令。
- `linux/`：Linux 下创建/复用 `.venv`、运行项目 Python，以及安装、迁移和移除 `~/.local/bin/gd` 入口。

阅读文档：[README.md](README.md) 是入口，[GD.md](GD.md) 是使用指南，[OSS.md](OSS.md) 介绍 OSS 配置和 Python API，[SITE.md](SITE.md) 介绍站点发布，[MODULES.md](MODULES.md) 介绍模块扩展。本文件列开发约束；具体命令和配置行为在使用文档说明。

## 开发环境与源码验证（Windows）

本节及后面的 PowerShell 命令适用于 Windows，解释器路径为 `.venv\Scripts\python.exe`。Linux 用 `bash linux/setup.sh --dev --no-launcher` 和 `bash linux/run.sh -m pytest`；解释器位于 `.venv/bin/python`。

开发和验证从本仓库根目录执行，Python 命令默认使用本仓库的 `.venv`：通过 `windows/run.ps1` 或明确的 `.\.venv\Scripts\python.exe` 执行，不使用未激活环境的裸 `python`/`pip`。`gd` 启动器也绑定本仓库环境；先核对导入路径，避免验证其他源码副本。

创建开发环境：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\setup.ps1 -Dev
```

仅准备核心环境时使用 `windows/setup.ps1 -CoreOnly`，不安装 OSS 可选依赖；不更新全局入口时加 `-NoLauncher`。完整测试使用 `-Dev`。已有虚拟环境复用，损坏环境不自动删除；其他项目拥有的全局入口仅在显式 `-MigrateFrom` 匹配时迁移，不能绕过归属检查。

确认导入的是当前源码；在仓库根目录运行，断言应通过，输出所指向的模块文件应位于本仓库：

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import gd_core; assert Path(gd_core.__file__).resolve().parent.parent == Path.cwd().resolve(); print(gd_core.__file__)"
```

比较解释器或目录是否相同时，先解析实际路径，以正确处理 Windows 目录链接。

## 开发约定

- 保持核心独立。不要在核心入口、帮助、模块列举或脚本注册过程中导入 OSS SDK 等模块专属依赖。
- 站点模块通过 HTTP PUT 上传并以公开地址的 `X-GD-SHA256` 回读核对。写入密钥只在本机配置和服务端 secret，不进入仓库、测试输出或站点页面。
- 新的多级命令模块通过 `gd.modules` entry point 扩展，入口为 `main(argv) -> int | None`，模块自己解析参数和管理依赖。
- 保持 `gd oss ...`、`oss-tool`、`oss_cli.py`、`python -m oss_toolkit` 和现有 Python API 的兼容性。
- OSS 通用选项仍支持放在 `gd` 后、`oss` 后或具体操作后。同一选项重复指定时，最后一次指定的值生效；保留现有命令别名。基线见 `tests/test_gd.py::test_global_flags_preserved_at_all_three_levels` 和 [GD.md](GD.md)。
- 使用小范围改动解决任务，避免无关重构；不覆盖已有用户改动。
- 项目未配置的格式化和静态检查，不列为必跑检查步骤。新增依赖时更新对应配置文件，核心依赖与模块可选依赖保持分离。

## 脚本管理行为

- 注册目录默认 `~/.gd`，注册文件为 `scripts.json`；`--home` 优先于 `GD_HOME`。
- 注册只保存脚本及解释器的绝对路径和元数据，不导入或执行脚本；移除注册保留脚本文件。
- 默认继承运行脚本时所在的工作目录，只有显式配置 `--cwd` 才固定工作目录。
- 参数使用进程参数列表转发，不拼接 shell 命令；保留空格、中文及以 `-` 或 `--` 开头的参数。脚本退出码返回给调用者。
- 更新注册文件时须加锁并原子保存；损坏配置报错，保留原内容。
- 管理命令与模块名称不能被新注册的脚本占用；同名注册需要 `--replace`。

## OSS 配置与传输行为

- 默认读取 `Path.home() / ".ossenv"`，与当前工作目录无关。指定 `--env-file` 时只读取指定文件。
- 用户配置字段保持无前缀形式：`ACCESS_KEY_ID`、`ACCESS_KEY_SECRET`、`SESSION_TOKEN`、`BUCKET`、`REGION` 等；SDK 内部的 `OSS_*` 映射和旧格式兼容应保留。
- 单次 CLI 进程的配置优先级：命令行参数 > 环境变量 > 配置文件 > 默认值。
- 当前 `Settings.from_env` 会把文件值写入 `os.environ`；同一 Python 进程再次加载时，已有 `OSS_*` 值优先。涉及多份配置的 API 变更须覆盖环境污染和重复调用，不能把重复加载文件当作已实现的隔离切换。
- 不将真实凭证写入源码、文档、测试、输出或 Git。模板仅保留示例值。
- `.gitignore` 排除 `.ossenv`、`.ossenv.*`、`.env`、`.env.*`（示例模板除外）、虚拟环境、缓存及 `*.oss-part`、`*.oss-part.temp`。自定义凭证文件名需另加忽略规则，提交前核对暂存内容。
- 默认禁止覆盖。保留断点续传、分片并发、CRC 校验及下载完成后原子发布的行为。
- 保留下载路径检查，拒绝路径穿越和无法安全映射的文件名；批量上传继续排除 `.ossenv`、`.env` 等配置文件。
- 删除 OSS 文件保留现有 `--yes` 要求。真实云端操作按用户任务范围执行，不作为常规自动化测试的一部分。

## 验证方法

代码变更运行相关测试；涉及核心分发、配置兼容、注册或传输流程时运行完整测试：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\run.ps1 -m pytest
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\run.ps1 gd.py --help
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\run.ps1 gd.py list
```

测试使用临时注册目录、假凭证和本地 OSS HTTP 服务。手动验证脚本注册时通过 `--home` 指定临时目录，避免修改用户默认注册信息。常规代码验证不操作真实 OSS；用户任务明确包含真实云端验证时，按任务范围执行。

重点覆盖参数转发、中文和空格路径、独立核心无需 OSS 依赖、注册持久化、损坏配置保护、目录链接、分页及完整性校验。为实际行为和故障编写测试，避免只重复实现细节。

纯文档修改核对命令、文件链接和格式即可。提交前执行 `git diff --check`，有暂存内容时执行 `git diff --cached --check`；检查 `git status` 和差异，确保只包含本任务内容。

## 本机环境备注（2026-10-11 核实）

本机仓库位于 `C:\Users\92416\Documents\woker\gd`。执行准备脚本后，全局 `gd` 已迁移至本仓库，使用 `C:\Users\92416\Documents\woker\gd\.venv\Scripts\python.exe`。安装或迁移后重新核实，不能把该记录当作其他机器或未来安装的固定状态。

已安装全局命令时，查看实际启动器及同目录清单；以输出中的 `project`、`python` 为准：

```powershell
$taskGdExe = (Get-Command gd -CommandType Application -ErrorAction Stop).Source
$taskGdManifest = Join-Path (Split-Path -Parent $taskGdExe) 'gd.install.json'
Get-Content -LiteralPath $taskGdManifest -Raw -Encoding UTF8 | ConvertFrom-Json | Select-Object project, python
```

开发默认使用本仓库环境；保留的旧 `code` 环境用于兼容回退，不用于默认验证。准备和迁移步骤见 [GD.md 的安装及移除](GD.md#安装及移除)。已有脚本注册保存的解释器路径不会自动改写；新注册或 `--replace` 更新的 Python 脚本默认用当前 `gd` 环境，显式 `--interpreter` 按指定值执行。

本机终端若找不到 `git`，可以使用已安装的完整路径：

```powershell
& 'C:\Users\92416\AppData\Local\Programs\Git\cmd\git.exe' status
```

## 文档与提交

命令行为、安装方法、模块接口或配置变化时同步更新实现、测试及相应文档。使用指南放在 `GD.md`，面向开发代理的约定放在本文件。

提交信息说明具体变更。不要将凭证、构建结果或临时运行文件放入提交。提交和远程推送根据用户任务范围执行。
