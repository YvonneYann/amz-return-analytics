from __future__ import annotations

import json
from typing import Dict, List

import requests

from .config import DeepSeekConfig
from .models import CandidateReview, LLMPayload, TagFragment


class DeepSeekClient:
    """Minimal wrapper for invoking DeepSeek chat completions."""

    def __init__(self, config: DeepSeekConfig):
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._model = config.model

    def annotate(self, review: CandidateReview) -> LLMPayload:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        system_prompt = (
            "You are an Amazon US marketplace return analyst. "
            "Return JSON with fields review_id, review_source, review_en, "
            "review_cn, sentiment (-1/0/1), "
            "tags[{tag_code, tag_name_cn, evidence}]. No prose."
        )
        body: Dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": review.review_en},
            ],
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        payload_dict = json.loads(content)
        tags = [
            TagFragment(
                tag_code=item["tag_code"],
                tag_name_cn=item["tag_name_cn"],
                evidence=item["evidence"],
            )
            for item in payload_dict.get("tags", [])
        ]
        return LLMPayload(
            review_id=payload_dict.get("review_id", review.review_id),
            review_source=payload_dict.get("review_source", review.review_source),
            review_en=payload_dict.get("review_en", review.review_en),
            review_cn=payload_dict.get("review_cn", ""),
            sentiment=payload_dict.get("sentiment", 0),
            tags=tags,
        )
