#!/usr/bin/env bash
set -euo pipefail

project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
python="$project/.venv/bin/python"
if [[ ! -f "$python" ]]; then
    echo 'The project virtual environment is not ready. Run linux/setup.sh first.' >&2
    exit 1
fi
exec "$python" "$@"
