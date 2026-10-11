"""Fallback without installation: python gd.py list / add / oss ls."""

from gd_core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
