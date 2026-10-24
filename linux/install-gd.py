#!/usr/bin/env python3
"""Install a project-owned Linux gd symlink in the user's command directory."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", type=Path, default=Path.home() / ".local" / "bin")
    parser.add_argument("--migrate-from", type=Path)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    launcher = project / ".venv" / "bin" / "gd"
    target_dir = args.install_dir.expanduser().resolve()
    target = target_dir / "gd"
    manifest = target_dir / "gd.install.json"
    previous = args.migrate_from.expanduser().resolve() if args.migrate_from else None

    if not args.uninstall and (not launcher.is_file() or not os.access(launcher, os.X_OK)):
        parser.error("Missing project gd entry point. Run linux/setup.sh first.")
    if manifest.exists():
        try:
            owner = json.loads(manifest.read_text(encoding="utf-8"))
            owned_project = Path(owner["project"]).resolve()
            owned_target = Path(owner["launcher"]).absolute()
        except (ValueError, KeyError, TypeError) as exc:
            parser.error(f"Invalid installation manifest: {manifest} ({exc})")
        if owned_target != target or (owned_project != project and (args.uninstall or owned_project != previous)):
            parser.error("The existing gd installation belongs to another project. Pass --migrate-from with its exact project path to migrate it.")
        if target.exists() or target.is_symlink():
            expected = owned_project / ".venv" / "bin" / "gd"
            if not target.is_symlink() or target.readlink().resolve() != expected.resolve():
                parser.error(f"The gd command at {target} no longer matches the installation manifest.")
    elif target.exists() or target.is_symlink():
        parser.error(f"An unrelated gd command already exists at {target}.")

    if args.uninstall:
        if target.exists() or target.is_symlink():
            target.unlink()
        manifest.unlink(missing_ok=True)
        print("gd launcher removed. Project files and configuration have been preserved.")
        return 0

    found = shutil.which("gd")
    if found and Path(found).absolute() not in {target, launcher}:
        parser.error(f"Another command named gd is already on PATH: {found}")

    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".gd-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.unlink()
        temporary.symlink_to(launcher)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    payload = {"project": str(project), "python": sys.executable, "launcher": str(target)}
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target_dir,
                                     prefix=".gd-install-", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    try:
        os.replace(temporary, manifest)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Installed: {target}")
    if target_dir not in (Path(part).expanduser().resolve() for part in os.environ.get("PATH", "").split(os.pathsep) if part):
        print(f"Add {target_dir} to PATH to use gd from any directory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
