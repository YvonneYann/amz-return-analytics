from __future__ import annotations

import json
from typing import Any, Dict, List

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
    def fetch_candidates(
        self, limit: int = 200, country: str | None = None, fasin: str | None = None
    ) -> List[CandidateReview]:
        sql = """
        SELECT review_id, review_source, review_en
        FROM view_return_review_snapshot
        """
        conditions = []
        params = []
        if country:
            conditions.append("country = %s")
            params.append(country)
        if fasin:
            conditions.append("fasin = %s")
            params.append(fasin)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY review_date DESC LIMIT %s"
        params.append(limit)

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
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
        delete_sql = "DELETE FROM return_fact_llm WHERE review_id = %s"
        insert_sql = """
        INSERT INTO return_fact_llm (review_id, payload)
        VALUES (%s, %s)
        """
        json_payload = payload.to_json()
        with self._conn.cursor() as cur:
            cur.execute(delete_sql, (payload.review_id,))
            cur.execute(insert_sql, (payload.review_id, json_payload))

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
        """
        rows = []
        if payload.tags:
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
        else:
            # 无标签时也保留一行记录，tag_code 置为占位符，便于追踪空结果。
            rows.append(
                (
                    payload.review_id,
                    "NO_TAG",
                    payload.review_source,
                    payload.review_en,
                    payload.review_cn,
                    payload.sentiment,
                    "",
                    "",
                )
            )
        with self._conn.cursor() as cur:
            # Remove existing tags for this review_id to simulate upsert behavior.
            cur.execute("DELETE FROM return_fact_details WHERE review_id = %s", (payload.review_id,))
            cur.executemany(sql, rows)

    # ------------------------------------------------------------------
    # Dimension helpers
    # ------------------------------------------------------------------
    def fetch_dim_tag_map(
        self, filters: List[Dict[str, Any]] | None = None
    ) -> Dict[str, Dict[str, str]]:
        with self._conn.cursor() as cur:
            sql = """
            SELECT
                tag_code,
                tag_name_cn,
                category_name_cn,
                definition,
                boundary_note
            FROM return_dim_tag
            WHERE is_active = 1
            """
            params = []
            if filters:
                for f in filters:
                    field = f.get("field")
                    operator = f.get("operator", "eq").lower()
                    value = f.get("value")
                    if operator != "eq":
                        raise ValueError(f"Unsupported operator: {operator}")
                    sql += f" AND {field} = %s"
                    params.append(value)
            cur.execute(sql, params)
            rows = cur.fetchall()
        return {row["tag_code"]: row for row in rows}

    def close(self) -> None:
        self._conn.close()
