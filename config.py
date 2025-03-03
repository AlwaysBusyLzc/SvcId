from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    database_url: str = ""
    max_svc_id: int = 65535

    class Config:
        env_file = ".env"

settings = Settings()