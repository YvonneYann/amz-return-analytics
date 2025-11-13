from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class DorisConfig:
    host: str
    port: int
    database: str
    username: str
    password: str


@dataclass
class DeepSeekConfig:
    base_url: str
    api_key: str
    model: str


@dataclass
class AppConfig:
    doris: DorisConfig
    deepseek: DeepSeekConfig


def load_config(path: Path | str) -> AppConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fp:
        data: Dict[str, Any] = yaml.safe_load(fp)
    return AppConfig(
        doris=DorisConfig(**data["doris"]),
        deepseek=DeepSeekConfig(**data["deepseek"]),
    )
