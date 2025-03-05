import sys

from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    database_url: str = ""
    max_svc_id: int = 65535
    log_to_console: bool = False
    port: int = 8000

    class Config:
        # 获取当前可执行文件所在目录
        if getattr(sys, 'frozen', False):
            BASE_DIR = os.path.dirname(sys.executable)  # 运行的是打包后的文件
        else:
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 运行的是源码

        env_file = os.path.join(BASE_DIR, ".env")  # 动态获取 .env 文件路径

settings = Settings()