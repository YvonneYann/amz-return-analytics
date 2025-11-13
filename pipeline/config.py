from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

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
class TagFilter:
    field: str
    operator: str
    value: Any


@dataclass
class AppConfig:
    doris: DorisConfig
    deepseek: DeepSeekConfig
    tag_filters: List[TagFilter]


def load_config(path: Path | str, tag_filter_path: Path | str | None = None) -> AppConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fp:
        data: Dict[str, Any] = yaml.safe_load(fp)
    tag_filters_data: List[Dict[str, Any]] = []
    filter_file = Path(tag_filter_path) if tag_filter_path else None
    if filter_file and filter_file.exists():
        tag_filters_data = yaml.safe_load(filter_file.read_text(encoding="utf-8")).get("tag_filters", [])
    filters = [
        TagFilter(**item)
        for item in (data.get("tag_filters", []) + tag_filters_data)
    ]
    return AppConfig(
        doris=DorisConfig(**data["doris"]),
        deepseek=DeepSeekConfig(**data["deepseek"]),
        tag_filters=filters,
    )
