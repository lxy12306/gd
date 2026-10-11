"""Compatibility import for gd's former OSS-specific entry point."""

from gd_core.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
