#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

was_running=false
if pgrep -f -- '-m xpeech_deck$' >/dev/null; then
    was_running=true
fi

echo "更新代码..."
git fetch origin
git reset --hard origin/main

echo "同步后端依赖..."
uv sync --frozen

if [[ "${was_running}" == true ]]; then
    "${SCRIPT_DIR}/stop.sh"
    "${SCRIPT_DIR}/start.sh"
fi

echo "升级完成"
