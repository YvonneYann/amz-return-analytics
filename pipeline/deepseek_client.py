from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

import requests

from .config import DeepSeekConfig
from .models import CandidateReview, LLMPayload, TagFragment

DEFAULT_INSTRUCTIONS = (
    "你是一名亚马逊美国站的退货分析专家，请严格按照 schema 输出 JSON，字段为："
    "review_id, review_source, review_en, review_cn, sentiment(-1/0/1), "
    "tags[{tag_code, tag_name_cn, evidence}]。仅可使用 tag_library 中的标签。"
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
        on_request: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> LLMPayload:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        instructions = prompt_text.strip() if prompt_text else DEFAULT_INSTRUCTIONS
        system_payload = {
            "role": "return_analyst",
            "instructions": instructions,
            "tag_library": _format_tag_library(tag_library),
        }
        user_payload = {
            "review_id": review.review_id,
            "review_source": review.review_source,
            "review_en": review.review_en,
        }
        body: Dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": json.dumps(system_payload, ensure_ascii=False)},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        if on_request:
            on_request(body)
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
