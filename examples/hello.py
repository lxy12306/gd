"""Register with: gd add hello ./examples/hello.py"""

import argparse

parser = argparse.ArgumentParser(description="gd 示例脚本")
parser.add_argument("--name", default="世界")
args = parser.parse_args()
print(f"你好，{args.name}！")
