"""命令行入口：启动 Xpeech Deck。"""

from __future__ import annotations

import uvicorn

from .app import create_app
from .config import docker_available, ensure_root_path, load_settings


def main() -> None:
    settings = load_settings()
    ensure_root_path(settings.root_path)
    if not docker_available():
        print("[警告] 未检测到 docker 命令，Compose 操作将会失败。")
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=7801)


if __name__ == "__main__":
    main()
