"""
Modular CLI for running the return analytics pipeline step-by-step.

Steps:
1. candidates - fetch data from view_return_review_snapshot and optionally dump to JSONL.
2. llm        - call DeepSeek on candidates (from DB or JSONL) and upsert into return_fact_llm.
3. parse      - parse payloads (from DB or JSONL) into return_fact_details.
4. all        - run the full chain (fetch -> LLM -> parse) without intermediate files.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Iterable, List

from pipeline.config import load_config
from pipeline.deepseek_client import DeepSeekClient
from pipeline.doris_client import DorisClient
from pipeline.models import CandidateReview, LLMPayload, TagFragment
from pipeline.steps import (
    step_call_llm,
    step_fetch_candidates,
    step_parse_payloads,
    step_write_raw_from_cache,
)


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for record in records:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_candidates_from_jsonl(path: Path) -> List[CandidateReview]:
    with path.open("r", encoding="utf-8") as fp:
        return [
            CandidateReview(
                review_id=obj["review_id"],
                review_source=obj["review_source"],
                review_en=obj["review_en"],
            )
            for obj in map(json.loads, fp)
        ]


def _read_payloads_from_jsonl(path: Path) -> List[LLMPayload]:
    payloads: List[LLMPayload] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            obj = json.loads(line)
            payloads.append(
                LLMPayload(
                    review_id=obj["review_id"],
                    review_source=obj["review_source"],
                    review_en=obj["review_en"],
                    review_cn=obj.get("review_cn", ""),
                    sentiment=obj.get("sentiment", 0),
                    tags=[
                        TagFragment(
                            tag_code=item["tag_code"],
                            tag_name_cn=item["tag_name_cn"],
                            evidence=item["evidence"],
                        )
                        for item in obj.get("tags", [])
                    ],
                )
            )
    return payloads


def run_step(
    step: str,
    config_path: str,
    limit: int,
    country: str | None,
    fasin: str | None,
    candidate_output: Path | None,
    candidate_input: Path | None,
    payload_output: Path | None,
    payload_input: Path | None,
    prompt_text: str | None,
    llm_request_output: Path | None,
    skip_db_write: bool,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(config_path, tag_filter_path="config/tag_filters.yaml")
    doris = DorisClient(cfg.doris)
    deepseek = DeepSeekClient(cfg.deepseek)

    try:
        if step == "candidates":
            candidates = step_fetch_candidates(doris, limit, country=country, fasin=fasin)
            if candidate_output:
                _write_jsonl(
                    candidate_output,
                    (
                        {
                            "review_id": c.review_id,
                            "review_source": c.review_source,
                            "review_en": c.review_en,
                        }
                        for c in candidates
                    ),
                )
                logging.info("Saved candidates to %s", candidate_output)

        elif step == "llm":
            tag_library = doris.fetch_dim_tag_map(filters=[f.__dict__ for f in cfg.tag_filters])
            if candidate_input:
                candidates = _read_candidates_from_jsonl(candidate_input)
                logging.info("Loaded %d candidates from %s", len(candidates), candidate_input)
            else:
                candidates = step_fetch_candidates(doris, limit, country=country, fasin=fasin)
            payloads = step_call_llm(
                candidates,
                deepseek,
                doris,
                tag_library,
                prompt_text,
                request_log_path=llm_request_output,
                write_to_db=not skip_db_write,
            )
            if payload_output:
                _write_jsonl(
                    payload_output,
                    (json.loads(payload.to_json()) for payload in payloads),
                )
                logging.info("Saved payloads to %s", payload_output)

        elif step == "parse":
            if payload_input:
                payloads = _read_payloads_from_jsonl(payload_input)
                logging.info("Loaded %d payloads from %s", len(payloads), payload_input)
                step_parse_payloads(doris, payloads=payloads)
            else:
                step_parse_payloads(doris, payloads=None, limit_from_db=limit)

        elif step == "raw":
            if not payload_input:
                raise ValueError("--payload-input is required for --step raw")
            payloads = _read_payloads_from_jsonl(payload_input)
            logging.info("Loaded %d payloads from %s", len(payloads), payload_input)
            step_write_raw_from_cache(doris, payloads)

        elif step == "all":
            candidates = step_fetch_candidates(doris, limit, country=country, fasin=fasin)
            tag_library = doris.fetch_dim_tag_map(filters=[f.__dict__ for f in cfg.tag_filters])
            payloads = step_call_llm(
                candidates,
                deepseek,
                doris,
                tag_library,
                prompt_text,
                request_log_path=llm_request_output,
            )
            step_parse_payloads(doris, payloads=payloads)

        else:
            raise ValueError(f"Unsupported step: {step}")

    finally:
        doris.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run modular pipeline steps.")
    parser.add_argument(
        "--config",
        default="config/environment.yaml",
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--step",
        choices=["candidates", "llm", "parse", "raw", "all"],
        required=True,
        help="Which step to run.",
    )
    parser.add_argument("--limit", type=int, default=200, help="Max rows to process.")
    parser.add_argument(
        "--country",
        type=str,
        help="Optional country filter (matches view_return_review_snapshot.country).",
    )
    parser.add_argument(
        "--fasin",
        type=str,
        help="Optional parent ASIN filter (matches view_return_review_snapshot.fasin).",
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        help="When running 'candidates' step, optional JSONL destination.",
    )
    parser.add_argument(
        "--candidate-input",
        type=Path,
        help="When running 'llm' step, optional JSONL source of candidates.",
    )
    parser.add_argument(
        "--payload-output",
        type=Path,
        help="When running 'llm' step, optional JSONL destination for payloads.",
    )
    parser.add_argument(
        "--payload-input",
        type=Path,
        help="When running 'parse' step, optional JSONL source of payloads.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=Path("prompt/deepseek_prompt.txt"),
        help="Text file containing custom instructions for DeepSeek (default: prompt/deepseek_prompt.txt).",
    )
    parser.add_argument(
        "--llm-request-output",
        type=Path,
        help="Optional JSONL file to log request bodies sent to DeepSeek.",
    )
    parser.add_argument(
        "--skip-db-write",
        action="store_true",
        help="When running --step llm, avoid writing payloads into Doris (only emit JSONL).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    prompt_text = None
    if args.prompt_file and args.prompt_file.exists():
        prompt_text = args.prompt_file.read_text(encoding="utf-8")
    run_step(
        step=args.step,
        config_path=args.config,
        limit=args.limit,
        country=args.country,
        fasin=args.fasin,
        candidate_output=args.candidate_output,
        candidate_input=args.candidate_input,
        payload_output=args.payload_output,
        payload_input=args.payload_input,
        prompt_text=prompt_text,
        llm_request_output=args.llm_request_output,
        skip_db_write=args.skip_db_write,
    )
