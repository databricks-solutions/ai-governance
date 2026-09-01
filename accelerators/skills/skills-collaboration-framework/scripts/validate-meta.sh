#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec python3 "$(dirname "$0")/_validate_meta.py" "$@"
