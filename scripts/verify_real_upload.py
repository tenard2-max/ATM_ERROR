"""5월장애_분석.xlsx 파싱·교체 업로드 검증."""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import data_loader
import db


class FakeUpload(io.BytesIO):
    def __init__(self, name: str, content: bytes):
        super().__init__(content)
        self.name = name


def inspect_file(path: Path) -> None:
    print(f"\n=== 파일: {path.name} ===")
    if not path.exists():
        print("  [없음] 파일이 존재하지 않습니다.")
        return

    raw = path.read_bytes()
    print(f"  크기: {len(raw):,} bytes")

    result = data_loader.parse_uploaded_file(FakeUpload(path.name, raw))
    if not result.ok:
        print(f"  [파싱 실패] {result.errors}")
        return

    df = result.df
    print(f"  파싱 성공: {len(df):,}건, 연월={result.연월}")
    print(f"  컬럼: {list(df.columns)}")
    if "지점명" in df.columns:
        incheon = df[df["지점명"].astype(str).str.contains("인천", na=False)]
        print(f"  인천 포함 지점: {len(incheon):,}건")
        if len(incheon):
            print(incheon["지점명"].value_counts().head(5).to_string())
    print(f"  미리보기 행 수: {min(3, len(df))}")


def test_replace_upload(path: Path) -> None:
    print("\n=== DB 교체 업로드 테스트 ===")
    if not path.exists():
        print("  파일 없음 — 스킵")
        return

    db.init_db()
    before_meta = db.list_uploaded_months()
    before_may = db.load_all_incidents()
    before_count = len(before_may[before_may["연월"] == "2026-05"]) if not before_may.empty else 0
    print(f"  교체 전 2026-05: {before_count:,}건")
    if not before_meta.empty and "2026-05" in before_meta["연월"].values:
        row = before_meta[before_meta["연월"] == "2026-05"].iloc[0]
        print(f"  교체 전 source: {row['source_filename']}")

    result = data_loader.parse_uploaded_file(FakeUpload(path.name, path.read_bytes()))
    if not result.ok:
        print(f"  [실패] {result.errors}")
        return

    saved = db.save_month_data(result.df, result.연월, result.filename, mode="replace")
    after_may = db.load_all_incidents()
    after_count = len(after_may[after_may["연월"] == result.연월])
    meta = db.list_uploaded_months()
    row = meta[meta["연월"] == result.연월].iloc[0]

    print(f"  save_month_data 반환: {saved:,}건")
    print(f"  교체 후 DB 2026-05: {after_count:,}건")
    print(f"  교체 후 source: {row['source_filename']}")
    print(f"  교체 후 uploaded_at: {row['uploaded_at']}")

    incheon = after_may[
        (after_may["연월"] == result.연월)
        & after_may["지점명"].astype(str).str.contains("인천", na=False)
    ]
    print(f"  교체 후 인천공항(유사): {len(incheon):,}건")

    ok = after_count == len(result.df) and before_count != after_count or before_count == after_count
    print(f"  DB 건수 = 파싱 건수: {'OK' if after_count == len(result.df) else 'FAIL'}")
    print(f"  샘플(6806) 제거됨: {'OK' if after_count != 6806 or len(result.df) == 6806 else '확인필요'}")


def main() -> None:
    candidates = [
        ROOT / "5월장애_분석.xlsx",
        ROOT / "5월장애_분석.xls",
        ROOT / "sample_data" / "202605_장애리스트.xlsx",
    ]
    for p in candidates:
        inspect_file(p)

    real = ROOT / "5월장애_분석.xlsx"
    if not real.exists():
        real = ROOT / "5월장애_분석.xls"
    test_replace_upload(real)


if __name__ == "__main__":
    main()
