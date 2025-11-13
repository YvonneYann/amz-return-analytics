from __future__ import annotations

import logging
from typing import Iterable, List

from .doris_client import DorisClient
from .deepseek_client import DeepSeekClient
from .models import CandidateReview, LLMPayload


def step_fetch_candidates(doris: DorisClient, limit: int) -> List[CandidateReview]:
    candidates = doris.fetch_candidates(limit=limit)
    logging.info("Fetched %d candidates from view_return_review_snapshot", len(candidates))
    return candidates


def step_call_llm(
    candidates: Iterable[CandidateReview],
    deepseek: DeepSeekClient,
    doris: DorisClient,
) -> List[LLMPayload]:
    payloads: List[LLMPayload] = []
    for review in candidates:
        payload = deepseek.annotate(review)
        doris.upsert_return_fact_llm(payload)
        payloads.append(payload)
    logging.info("Stored %d payloads into return_fact_llm", len(payloads))
    return payloads


def step_parse_payloads(
    doris: DorisClient,
    payloads: Iterable[LLMPayload] | None = None,
    limit_from_db: int = 200,
) -> None:
    if payloads is None:
        payloads = doris.fetch_payloads(limit=limit_from_db)
        logging.info("Fetched %d payloads from return_fact_llm", len(payloads))
    count = 0
    for payload in payloads:
        doris.insert_return_fact_details(payload)
        count += 1
    logging.info("Inserted/updated %d rows into return_fact_details", count)
