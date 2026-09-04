#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_ROOT}/deck.log"

cd "${PROJECT_ROOT}"

if pgrep -f 'python -m xpeech_deck$' >/dev/null; then
    echo "Xpeech Deck 已在运行"
    exit 0
fi

nohup uv run --frozen python -m xpeech_deck >>"${LOG_FILE}" 2>&1 &

sleep 1
if pgrep -f 'python -m xpeech_deck$' >/dev/null; then
    echo "Xpeech Deck 启动成功"
    echo "日志：${LOG_FILE}"
else
    echo "启动失败，请查看日志：${LOG_FILE}" >&2
    exit 1
fi
