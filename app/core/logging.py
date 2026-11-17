"""统一日志配置。

实践点：为不同模块配置独立 logger，避免 print 调试，结构化输出便于排查。
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
