"""GitHub Pages용 정적 JSON 데이터 생성."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cloud_bootstrap
import db
from config import MAPPING_FILE, SAMPLE_DIR

OUT_DIR = ROOT / "static" / "data"


def export_incidents() -> int:
    cloud_bootstrap.ensure_runtime_data()
    df = db.load_all_incidents()
    cols = [
        "연월",
        "점번",
        "지점명",
        "기번",
        "기종",
        "발생일자",
        "세부장애",
        "장애내용",
        "장애코드2",
    ]
    records = df[cols].astype(str).to_dict("records")
    path = OUT_DIR / "incidents.json"
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return len(records)


def export_mapping() -> int:
    if not MAPPING_FILE.exists():
        from scripts.create_sample_data import create_mapping_file

        create_mapping_file()
    df = pd.read_excel(MAPPING_FILE, engine="openpyxl")
    records = df.astype(str).to_dict("records")
    path = OUT_DIR / "mapping.json"
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return len(records)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_inc = export_incidents()
    n_map = export_mapping()
    print(f"Exported {n_inc:,} incidents -> {OUT_DIR / 'incidents.json'}")
    print(f"Exported {n_map:,} mapping rows -> {OUT_DIR / 'mapping.json'}")
    if not any(SAMPLE_DIR.glob("*.xlsx")):
        print("(sample_data missing — used DB/bootstrap source)")


if __name__ == "__main__":
    main()
