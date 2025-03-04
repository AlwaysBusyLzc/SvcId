import logging
from logging.handlers import TimedRotatingFileHandler
import os
from pathlib import Path
from config import settings


def setup_logger():
    # 创建日志目录（如果不存在）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 日志文件路径（按日期分割）
    log_file = log_dir / "app.log"

    # 配置日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 创建 TimedRotatingFileHandler（每天轮转，保留30天）
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",  # 按天切割
        interval=1,  # 每天一个文件
        backupCount=30,  # 保留最近7天的日志
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    handler.suffix = "%Y-%m-%d"  # 日志文件名后缀（如 app.log.2023-10-01）

    # 获取根日志器并配置
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # 设置日志级别（生产环境建议 INFO）
    logger.addHandler(handler)

    if settings.log_to_console:
        # 同时输出到控制台
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


    # 可选：关闭 Uvicorn 默认的控制台日志（避免重复输出）
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.propagate = False

    return logger