from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import pymysql

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pipeline.config import load_config


def normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single tag record with safe defaults."""
    return {
        "tag_code": item.get("tag_code") or item.get("code"),
        "tag_name_cn": item.get("tag_name_cn") or item.get("name_cn"),
        "category_code": item.get("category_code") or item.get("cat_code"),
        "category_name_cn": item.get("category_name_cn") or item.get("cat_name_cn"),
        "level": item.get("level", 2),
        "definition": item.get("definition") or "",
        "boundary_note": item.get("boundary_note") or "",
        "is_active": int(item.get("is_active", 1)),
        "version": item.get("version", 1),
        "effective_from": item.get("effective_from"),
        "effective_to": item.get("effective_to"),
    }


def load_tags(json_path: Path) -> List[Dict[str, Any]]:
    text = json_path.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, dict):
        if "data" in data:
            data = data["data"]
        elif "return_dim_tag" in data:
            data = data["return_dim_tag"]
    if not isinstance(data, list):
        raise ValueError("Expected a list of tag objects in JSON.")
    records = [normalize_record(item) for item in data]
    records = [r for r in records if r["tag_code"]]
    return records


def upsert_dim_tags(records: List[Dict[str, Any]]) -> None:
    cfg = load_config("config/environment.yaml")
    conn = pymysql.connect(
        host=cfg.doris.host,
        port=cfg.doris.port,
        user=cfg.doris.username,
        password=cfg.doris.password,
        database=cfg.doris.database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    delete_sql = "DELETE FROM return_dim_tag WHERE tag_code = %s"
    insert_sql = """
    INSERT INTO return_dim_tag (
        tag_code,
        tag_name_cn,
        category_code,
        category_name_cn,
        level,
        definition,
        boundary_note,
        is_active,
        version,
        effective_from,
        effective_to
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    try:
        with conn.cursor() as cur:
            for rec in records:
                cur.execute(delete_sql, (rec["tag_code"],))
                cur.execute(
                    insert_sql,
                    (
                        rec["tag_code"],
                        rec["tag_name_cn"],
                        rec["category_code"],
                        rec["category_name_cn"],
                        rec["level"],
                        rec["definition"],
                        rec["boundary_note"],
                        rec["is_active"],
                        rec["version"],
                        rec["effective_from"],
                        rec["effective_to"],
                    ),
                )
        print(f"Upserted {len(records)} records into return_dim_tag")
    finally:
        conn.close()


if __name__ == "__main__":
    json_file = Path("chat/return_dim_tag_v2_20251117.json")
    if not json_file.exists():
        raise SystemExit(f"File not found: {json_file}")
    records = load_tags(json_file)
    upsert_dim_tags(records)
