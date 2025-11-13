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
from pipeline.steps import step_call_llm, step_fetch_candidates, step_parse_payloads


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
    candidate_output: Path | None,
    candidate_input: Path | None,
    payload_output: Path | None,
    payload_input: Path | None,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(config_path)
    doris = DorisClient(cfg.doris)
    deepseek = DeepSeekClient(cfg.deepseek)

    try:
        if step == "candidates":
            candidates = step_fetch_candidates(doris, limit)
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
            if candidate_input:
                candidates = _read_candidates_from_jsonl(candidate_input)
                logging.info("Loaded %d candidates from %s", len(candidates), candidate_input)
            else:
                candidates = step_fetch_candidates(doris, limit)
            payloads = step_call_llm(candidates, deepseek, doris)
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

        elif step == "all":
            candidates = step_fetch_candidates(doris, limit)
            payloads = step_call_llm(candidates, deepseek, doris)
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
        choices=["candidates", "llm", "parse", "all"],
        required=True,
        help="Which step to run.",
    )
    parser.add_argument("--limit", type=int, default=200, help="Max rows to process.")
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_step(
        step=args.step,
        config_path=args.config,
        limit=args.limit,
        candidate_output=args.candidate_output,
        candidate_input=args.candidate_input,
        payload_output=args.payload_output,
        payload_input=args.payload_input,
    )
