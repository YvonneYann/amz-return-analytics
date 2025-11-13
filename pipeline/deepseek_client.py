from __future__ import annotations

import json
from typing import Dict, List, Optional

import requests

from .config import DeepSeekConfig
from .models import CandidateReview, LLMPayload, TagFragment


DEFAULT_SYSTEM_PROMPT = (
    "You are an Amazon US marketplace return analyst. "
    "Always respond with valid JSON that matches the specified schema."
)

DEFAULT_INSTRUCTIONS = (
    "阅读 review_en（英文原文）与下面的标签库（tag_library），"
    "按 README 规范输出 JSON：review_id, review_source, review_en, review_cn, "
    "sentiment (-1/0/1), tags[{tag_code, tag_name_cn, evidence}]。"
)


class DeepSeekClient:
    """Minimal wrapper for invoking DeepSeek chat completions."""

    def __init__(self, config: DeepSeekConfig):
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._model = config.model

    def annotate(
        self,
        review: CandidateReview,
        tag_library: Dict[str, Dict[str, str]],
        prompt_text: Optional[str] = None,
    ) -> LLMPayload:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        instructions = prompt_text.strip() if prompt_text else DEFAULT_INSTRUCTIONS
        user_payload = {
            "instructions": instructions,
            "review": {
                "review_id": review.review_id,
                "review_source": review.review_source,
                "review_en": review.review_en,
            },
            "tag_library": _format_tag_library(tag_library),
        }
        body: Dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
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


def _format_tag_library(tag_library: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for code, meta in tag_library.items():
        result.append(
            {
                "tag_code": code,
                "tag_name_cn": meta.get("tag_name_cn", ""),
                "category_name_cn": meta.get("category_name_cn", ""),
                "definition": meta.get("definition", ""),
                "boundary_note": meta.get("boundary_note", ""),
            }
        )
    return result
