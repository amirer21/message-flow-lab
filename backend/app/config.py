import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    rabbit_host: str = os.getenv("RABBIT_HOST", "localhost")
    rabbit_port: int = int(os.getenv("RABBIT_PORT", "5672"))
    rabbit_user: str = os.getenv("RABBIT_USER", "lab")
    rabbit_password: str = os.getenv("RABBIT_PASSWORD", "")
    rabbit_vhost: str = os.getenv("RABBIT_VHOST", "lab")
    management_url: str = os.getenv("RABBIT_MANAGEMENT_URL", "http://localhost:15672")
    lab_token: str = os.getenv("LAB_TOKEN", "")
    allowed_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
    )
    event_log: str = os.getenv("EVENT_LOG", "data/events.jsonl")
    queue: str = "hello"


settings = Settings()
