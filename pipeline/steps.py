from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .deepseek_client import DeepSeekClient
from .doris_client import DorisClient
from .models import CandidateReview, LLMPayload


def step_fetch_candidates(doris: DorisClient, limit: int) -> List[CandidateReview]:
    candidates = doris.fetch_candidates(limit=limit)
    logging.info("Fetched %d candidates from view_return_review_snapshot", len(candidates))
    return candidates


def step_call_llm(
    candidates: Iterable[CandidateReview],
    deepseek: DeepSeekClient,
    doris: DorisClient,
    tag_library: Dict[str, Dict[str, str]],
    prompt_text: Optional[str],
    request_log_path: Optional[Path] = None,
    write_to_db: bool = True,
) -> List[LLMPayload]:
    if not tag_library:
        raise ValueError("tag_library is empty; fetch return_dim_tag before calling LLM.")
    payloads: List[LLMPayload] = []
    log_fp = None
    if request_log_path:
        request_log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = request_log_path.open("a", encoding="utf-8")

        def _logger(body: Dict[str, object]) -> None:
            log_fp.write(json.dumps(body, ensure_ascii=False) + "\n")

    else:
        _logger = None

    for review in candidates:
        payload = deepseek.annotate(review, tag_library, prompt_text, on_request=_logger)
        if write_to_db:
            doris.upsert_return_fact_llm(payload)
        payloads.append(payload)

    if write_to_db:
        logging.info("Stored %d payloads into return_fact_llm", len(payloads))
    if log_fp:
        log_fp.close()
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


def step_write_raw_from_cache(
    doris: DorisClient, payloads: Iterable[LLMPayload]
) -> None:
    count = 0
    for payload in payloads:
        doris.upsert_return_fact_llm(payload)
        count += 1
    logging.info("Upserted %d payloads into return_fact_llm from cache", count)
