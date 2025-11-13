from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class CandidateReview:
    review_id: str
    review_source: int
    review_en: str


@dataclass
class TagFragment:
    tag_code: str
    tag_name_cn: str
    evidence: str


@dataclass
class LLMPayload:
    review_id: str
    review_source: int
    review_en: str
    review_cn: str
    sentiment: int
    tags: List[TagFragment]

    def to_json(self) -> str:
        return json.dumps(
            {
                "review_id": self.review_id,
                "review_source": self.review_source,
                "review_en": self.review_en,
                "review_cn": self.review_cn,
                "sentiment": self.sentiment,
                "tags": [
                    {
                        "tag_code": tag.tag_code,
                        "tag_name_cn": tag.tag_name_cn,
                        "evidence": tag.evidence,
                    }
                    for tag in self.tags
                ],
            },
            ensure_ascii=False,
        )


@dataclass
class FactDetailRow:
    review_id: str
    tag_code: str
    review_source: int
    review_en: str
    review_cn: str
    sentiment: int
    tag_name_cn: str
    evidence: str
    created_at: datetime
