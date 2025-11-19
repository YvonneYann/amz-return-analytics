from __future__ import annotations

import json
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pipeline.config import load_config

cfg = load_config("config/environment.yaml", "config/tag_filters.yaml")

url = cfg.deepseek.base_url.rstrip("/") + "/chat/completions"
headers = {
    "Authorization": f"Bearer {cfg.deepseek.api_key}",
    "Content-Type": "application/json",
}
body = {
    "model": cfg.deepseek.model,
    "messages": [
        {"role": "system", "content": "You are a JSON echo bot."},
        {"role": "user", "content": json.dumps({"ping": "hello"})},
    ],
    "response_format": {"type": "json_object"},
}

resp = requests.post(url, headers=headers, json=body, timeout=cfg.deepseek.timeout)
resp.raise_for_status()
print(resp.json())
