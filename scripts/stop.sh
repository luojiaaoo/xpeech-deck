#!/usr/bin/env bash

set -euo pipefail

if ! pgrep -f -- '-m xpeech_deck$' >/dev/null; then
    echo "Xpeech Deck 未运行"
    exit 0
fi

pkill -f -- '-m xpeech_deck$'
echo "Xpeech Deck 已停止"
