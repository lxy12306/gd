#!/usr/bin/env bash
set -euo pipefail

project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
venv="$project/.venv"
python="$venv/bin/python"
bootstrap=python3
core_only=0
dev=0
no_launcher=0
installer_args=()

usage() {
    echo 'Usage: linux/setup.sh [--python COMMAND] [--core-only | --dev] [--no-launcher] [--install-dir DIR] [--migrate-from PROJECT]'
}
while (($#)); do
    case "$1" in
        --python|--install-dir|--migrate-from)
            if (($# < 2)) || [[ -z "$2" ]]; then echo "Missing value for $1" >&2; exit 2; fi
            case "$1" in
                --python) bootstrap="$2" ;;
                *) installer_args+=("$1" "$2") ;;
            esac
            shift 2 ;;
        --core-only) core_only=1; shift ;;
        --dev) dev=1; shift ;;
        --no-launcher) no_launcher=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done
if ((core_only && dev)); then echo '--core-only and --dev cannot be combined.' >&2; exit 2; fi
if ((no_launcher && ${#installer_args[@]})); then
    echo '--install-dir/--migrate-from require launcher installation.' >&2; exit 2
fi

if [[ ! -f "$python" ]]; then
    if [[ -e "$venv" || -L "$venv" ]]; then
        echo "An incomplete .venv exists at $venv. It has been preserved; repair or move it before retrying." >&2
        exit 1
    fi
    if ! command -v -- "$bootstrap" >/dev/null 2>&1; then
        echo "Cannot find the requested Python interpreter: $bootstrap" >&2; exit 1
    fi
    "$bootstrap" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ is required"'
    echo "Creating virtual environment: $venv"
    "$bootstrap" -m venv "$venv"
else
    echo "Reusing virtual environment: $venv"
fi

"$python" - "$venv" <<'PY'
from pathlib import Path
import sys
expected = Path(sys.argv[1]).resolve()
if sys.version_info < (3, 10) or sys.prefix == sys.base_prefix or Path(sys.prefix).resolve() != expected:
    raise SystemExit('The .venv interpreter must be Python 3.10+ and belong to this virtual environment.')
PY
"$python" -m pip --version
package="$project"
if ((!core_only)); then package="$project[oss]"; fi
install_args=(-m pip install --disable-pip-version-check -e "$package")
if ((dev)); then install_args+=(-r "$project/requirements-dev.txt"); fi
"$python" "${install_args[@]}"
"$python" -m pip check
"$venv/bin/gd" --help >/dev/null
if ((!no_launcher)); then
    "$python" "$project/linux/install-gd.py" "${installer_args[@]}"
fi
echo "Ready. Default Python: $python"
echo 'Run Python commands: bash linux/run.sh <python arguments>'
if ((no_launcher)); then
    echo 'Run gd locally: .venv/bin/gd <arguments>'
else
    echo 'Run from any directory: gd <arguments> (ensure ~/.local/bin is on PATH)'
fi
