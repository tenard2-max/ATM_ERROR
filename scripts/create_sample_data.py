"""샘플 매핑 파일 및 README 비율 반영 테스트용 장애리스트 생성."""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
MAPPING_DIR = BASE / "mapping"
SAMPLE_DIR = BASE / "sample_data"

CODES = [
    ("09322", "11330009322", "카드/명세표 미수취"),
    ("10514", "11330010514", "현금입금기 장애"),
    ("33072", "11330033072", "통신회선 접속 오류"),
    ("10518", "11330010518", "지폐 방출 불량"),
    ("20524", "11330020524", "운영장치 도어 센서 이상"),
    ("ATMS1", "113300ATMS1", "카드 리더기 오류"),
]

# README §3.3 (2026년 5월) 비율
MODEL_WEIGHTS = {
    "ATEC-ATM(LM-20T)": 6212,
    "ATEC-ATM(LC-24)": 399,
    "LG-ATM(LC-20T)": 195,
}

BRANCHES = [
    ("0115", "강남역금융센터"),
    ("0210", "서울역지점"),
    ("0311", "부산센터"),
    ("0412", "대구중앙"),
    ("0513", "인천공항"),
]


def create_mapping_file() -> None:
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(CODES, columns=["세부장애", "장애코드2", "설명"])
    df[["세부장애", "장애코드2"]].to_excel(
        MAPPING_DIR / "장애코드.xlsx", index=False, engine="openpyxl"
    )


def _build_devices(device_count: int, rng: random.Random) -> list[tuple[str, str, str]]:
    devices: list[tuple[str, str, str]] = []
    for i in range(device_count):
        branch_code, branch_name = BRANCHES[i % len(BRANCHES)]
        suffix = f"{i // len(BRANCHES) + 1:02d}"
        devices.append((branch_code, branch_name, f"{branch_code}A{suffix}"))
    return devices


def create_sample_incidents(month: str, total_rows: int, rng: random.Random) -> pd.DataFrame:
    year, mon = map(int, month.split("-"))
    start = date(year, mon, 1)
    days_in_month = 28 if mon == 2 else 30 if mon in {4, 6, 9, 11} else 31

    models = list(MODEL_WEIGHTS.keys())
    weights = list(MODEL_WEIGHTS.values())
    device_count = max(120, total_rows // 6)
    devices = _build_devices(device_count, rng)

    records = []
    for i in range(total_rows):
        branch_code, branch_name, device_id = devices[rng.randrange(len(devices))]
        model = rng.choices(models, weights=weights, k=1)[0]
        code, _, desc = CODES[i % len(CODES)]
        day_offset = rng.randrange(days_in_month)
        records.append(
            {
                "점번": branch_code,
                "지점명": branch_name,
                "기번": device_id,
                "기종": model,
                "발생일자": (start + timedelta(days=day_offset)).strftime("%Y-%m-%d"),
                "세부장애": code,
                "장애내용": desc,
            }
        )
    return pd.DataFrame(records)


def main() -> None:
    create_mapping_file()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    plan = {
        "2026-03": 5200,
        "2026-04": 5900,
        "2026-05": 6806,
    }
    for month, rows in plan.items():
        df = create_sample_incidents(month, rows, rng)
        out = SAMPLE_DIR / f"{month.replace('-', '')}_장애리스트.xlsx"
        df.to_excel(out, index=False, engine="openpyxl")
        summary = df["기종"].value_counts()
        print(f"Created {out.name}: {len(df):,} rows")
        for model, count in summary.items():
            print(f"  {model}: {count:,}")

    print(f"Mapping: {MAPPING_DIR / '장애코드.xlsx'}")


if __name__ == "__main__":
    main()
