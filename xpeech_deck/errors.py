"""领域异常：服务层错误统一映射为 HTTP 状态码。"""

from __future__ import annotations


class DeckError(Exception):
    """所有业务异常的基类。"""

    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DeckError):
    """请求参数错误（400）：TOML 错误、端口错误、非法实例名。"""

    status_code = 400


class NotFoundError(DeckError):
    """资源不存在（404）。"""

    status_code = 404


class ConflictError(DeckError):
    """资源冲突（409）：实例已存在、正在执行命令。"""

    status_code = 409


class FileOperationError(DeckError):
    """文件或 Git 操作失败（500）。"""

    status_code = 500


class CommandTimeoutError(DeckError):
    """Compose 命令超时（504）。"""

    status_code = 504
