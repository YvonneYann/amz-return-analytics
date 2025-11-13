from __future__ import annotations

import json
from typing import Dict, List

import pymysql

from .config import DorisConfig
from .models import CandidateReview, LLMPayload, TagFragment


class DorisClient:
    """Thin MySQL-protocol wrapper for Doris operations used in the pipeline."""

    def __init__(self, config: DorisConfig):
        self._conn = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.username,
            password=config.password,
            database=config.database,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    # ------------------------------------------------------------------
    # Candidate stage
    # ------------------------------------------------------------------
    def fetch_candidates(self, limit: int = 200) -> List[CandidateReview]:
        sql = """
        SELECT review_id, review_source, review_en
        FROM view_return_review_snapshot
        ORDER BY review_date DESC
        LIMIT %s
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
        return [
            CandidateReview(
                review_id=row["review_id"],
                review_source=row["review_source"],
                review_en=row["review_en"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Raw payload stage
    # ------------------------------------------------------------------
    def upsert_return_fact_llm(self, payload: LLMPayload) -> None:
        sql = """
        INSERT INTO return_fact_llm (review_id, payload)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE payload = VALUES(payload),
                                created_at = NOW()
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (payload.review_id, payload.to_json()))

    def fetch_payloads(self, limit: int = 200) -> List[LLMPayload]:
        sql = """
        SELECT payload
        FROM return_fact_llm
        ORDER BY created_at DESC
        LIMIT %s
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
        payloads: List[LLMPayload] = []
        for row in rows:
            payload_dict = json.loads(row["payload"])
            tags = [
                TagFragment(
                    tag_code=item["tag_code"],
                    tag_name_cn=item["tag_name_cn"],
                    evidence=item["evidence"],
                )
                for item in payload_dict.get("tags", [])
            ]
            payloads.append(
                LLMPayload(
                    review_id=payload_dict["review_id"],
                    review_source=payload_dict["review_source"],
                    review_en=payload_dict["review_en"],
                    review_cn=payload_dict.get("review_cn", ""),
                    sentiment=payload_dict.get("sentiment", 0),
                    tags=tags,
                )
            )
        return payloads

    # ------------------------------------------------------------------
    # Fact details stage
    # ------------------------------------------------------------------
    def insert_return_fact_details(self, payload: LLMPayload) -> None:
        if not payload.tags:
            return
        sql = """
        INSERT INTO return_fact_details (
            review_id,
            tag_code,
            review_source,
            review_en,
            review_cn,
            sentiment,
            tag_name_cn,
            evidence
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            review_source = VALUES(review_source),
            review_en = VALUES(review_en),
            review_cn = VALUES(review_cn),
            sentiment = VALUES(sentiment),
            tag_name_cn = VALUES(tag_name_cn),
            evidence = VALUES(evidence),
            updated_at = NOW()
        """
        rows = [
            (
                payload.review_id,
                tag.tag_code,
                payload.review_source,
                payload.review_en,
                payload.review_cn,
                payload.sentiment,
                tag.tag_name_cn,
                tag.evidence,
            )
            for tag in payload.tags
        ]
        with self._conn.cursor() as cur:
            cur.executemany(sql, rows)

    # ------------------------------------------------------------------
    # Dimension helpers
    # ------------------------------------------------------------------
    def fetch_dim_tag_map(self) -> Dict[str, Dict[str, str]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag_code, tag_name_cn, category_name_cn
                FROM return_dim_tag
                WHERE is_active = 1
                """
            )
            rows = cur.fetchall()
        return {row["tag_code"]: row for row in rows}

    def close(self) -> None:
        self._conn.close()
