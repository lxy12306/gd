# 为 gd 添加功能模块

单个脚本直接用 `gd add <名称> <路径>` 注册。需要 `gd git status` 这样多级命令的模块，可用 Python 包的 `gd.modules` entry point。核心发现入口时读取包元数据，实际调用该模块时才导入入口函数；模块自己解析参数并管理依赖和配置。

例如创建一个 `gd_demo` 包：

```text
gd-demo/
  pyproject.toml
  gd_demo/
    __init__.py
    cli.py
```

`pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "gd-demo-module"
version = "0.1.0"
requires-python = ">=3.10"

[project.entry-points."gd.modules"]
demo = "gd_demo.cli:main"
```

`gd_demo/cli.py`：

```python
import argparse

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gd demo")
    commands = parser.add_subparsers(dest="command", required=True)
    hello = commands.add_parser("hello")
    hello.add_argument("name")
    args = parser.parse_args(argv)
    print(f"你好，{args.name}！")
    return 0
```

安装到运行 `gd` 的同一个虚拟环境：

```powershell
C:\Users\92416\Documents\woker\gd\.venv\Scripts\python.exe -m pip install -e D:\code\gd-demo
gd list
gd demo hello 张三
gd demo --help
```

模块名称遵循小写字母开头及字母、数字、`_`、`-` 的规则，不能与内置模块或管理命令重名。为避免占用已有脚本名称，安装前使用 `gd list` 检查；模块名称优先于同名脚本，卸载模块后脚本注册仍然保留。卸载扩展包即可从 `gd` 移除该模块。

入口接收移除模块名称之后的原始参数列表，返回整数退出码或 `None`（成功）。将该模块的第三方依赖放在自己的包中，勿在 `gd_core` 根入口提前导入它们。模块参数位于模块名称后，例如 `gd demo --help`；内置 OSS 另外保留历史上放在 `gd` 后的 OSS 选项。
