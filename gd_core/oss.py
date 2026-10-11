"""Lazy adapter: importing gd's core does not load the OSS SDK."""

import argparse


def main(argv: list[str] | None = None) -> int:
    from oss_toolkit import cli

    parser = argparse.ArgumentParser(
        prog="gd oss",
        description="gd oss · put 上传 / get 下载 / ls 列举 / search 检索",
        epilog="上传目录：gd oss put ./images images/\n下载目录：gd oss get images/ ./downloads\n只检查配置：gd oss config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cli.build_parser(parser, required_commands=False, friendly=True)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return cli.run(args)
