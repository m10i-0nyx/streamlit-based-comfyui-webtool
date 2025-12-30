from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Load environment variables early so Streamlit reruns pick them up.
load_dotenv()

DEFAULT_API_BASE: Final[str] = "http://localhost:8188"
DEFAULT_WS_URL: Final[str] = "ws://localhost:8188/ws"
DEFAULT_WORKFLOW_PATH: Final[str] = "workflows/example.json"
DEFAULT_WIDTH: Final[int] = 512
DEFAULT_HEIGHT: Final[int] = 512
DEFAULT_MAX_ACTIVE_REQUESTS: Final[int] = 1
DEFAULT_REQUEST_TIMEOUT: Final[float] = 120.0
DEFAULT_DEBUG_MODE: Final[bool] = False
DEFAULT_HISTORY_TTL: Final[int] = 600  # 10 minutes
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
DEFAULT_GLOBAL_MAX_ACTIVE_REQUESTS: Final[int] = 0  # 0 means no global limit


@dataclass(frozen=True)
class Configs:
    api_base: str
    ws_url: str
    workflow_path: Path
    width: int
    height: int
    max_active_requests: int
    request_timeout: float
    debug: bool
    history_ttl: int
    log_level: str
    global_max_active_requests: int


def load_config() -> Configs:
    """Read settings from environment with sensible defaults."""

    api_base = os.getenv("COMFYUI_BASE_URL", DEFAULT_API_BASE).rstrip("/")
    ws_url = os.getenv("COMFYUI_WS_URL", DEFAULT_WS_URL).rstrip("/")
    workflow_path = Path(os.getenv("WORKFLOW_JSON_PATH", DEFAULT_WORKFLOW_PATH))
    width = int(os.getenv("IMAGE_WIDTH", str(DEFAULT_WIDTH)))
    height = int(os.getenv("IMAGE_HEIGHT", str(DEFAULT_HEIGHT)))
    max_active_requests = int(
        os.getenv("MAX_ACTIVE_REQUESTS", str(DEFAULT_MAX_ACTIVE_REQUESTS))
    )
    request_timeout = float(
        os.getenv("REQUEST_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT))
    )
    debug = _to_bool(os.getenv("DEBUG_MODE", str(False)))
    history_ttl = int(os.getenv("HISTORY_TTL_SECONDS", str(DEFAULT_HISTORY_TTL)))

    raw_log_level = os.getenv("LOG_LEVEL")
    if raw_log_level:
        log_level = raw_log_level.strip().upper()
    elif debug:
        log_level = "DEBUG"
    else:
        log_level = DEFAULT_LOG_LEVEL
    if log_level not in {"INFO", "DEBUG", "TRACE"}:
        log_level = DEFAULT_LOG_LEVEL

    global_max_active_requests = int(
        os.getenv(
            "GLOBAL_MAX_ACTIVE_REQUESTS",
            str(DEFAULT_GLOBAL_MAX_ACTIVE_REQUESTS),
        )
    )

    return Configs(
        api_base=api_base,
        ws_url=ws_url,
        workflow_path=workflow_path,
        width=width,
        height=height,
        max_active_requests=max_active_requests,
        request_timeout=request_timeout,
        debug=debug,
        history_ttl=history_ttl,
        log_level=log_level,
        global_max_active_requests=global_max_active_requests,
    )


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
