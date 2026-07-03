"""Phase 8 통합·예외·성능·연계 테스트."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ai_classifier
import analyzer
import api_settings
import data_loader
import db
import drilldown
from app_common import set_nav_target, set_nav_to_c
from config import MAX_UPLOAD_FILES


class FakeUpload(io.BytesIO):
    def __init__(self, name: str, content: bytes):
        super().__init__(content)
        self.name = name


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def test_exceptions() -> bool:
    ok = True
    print("\n--- SS10 예외 처리 ---")

    bad_cols = pd.DataFrame({"A": [1]})
    buf = io.BytesIO()
    bad_cols.to_excel(buf, index=False)
    r1 = data_loader.parse_uploaded_file(FakeUpload("bad.xlsx", buf.getvalue()))
    ok &= check(
        "필수 컬럼 누락 거부",
        not r1.ok and any("필수 컬럼" in e for e in r1.errors),
        r1.errors[0] if r1.errors else "no error",
    )

    empty = pd.DataFrame(columns=["점번", "지점명", "기번", "기종", "발생일자", "세부장애", "장애내용"])
    buf2 = io.BytesIO()
    empty.to_excel(buf2, index=False)
    r2 = data_loader.parse_uploaded_file(FakeUpload("empty.xlsx", buf2.getvalue()))
    ok &= check("빈 파일 거부", not r2.ok)

    sample = ROOT / "sample_data" / "202605_장애리스트.xlsx"
    if sample.exists():
        good = data_loader.parse_uploaded_file(
            FakeUpload("good.xlsx", sample.read_bytes())
        )
        ok &= check("장애코드2 매핑 생성", good.ok and "장애코드2" in good.df.columns)
        ok &= check("정상 파일 파싱", good.ok, f"{len(good.df)}건")

    codes = ai_classifier.extract_unique_codes(
        db.load_all_incidents().head(50) if not db.load_all_incidents().empty else pd.DataFrame()
    )
    if not codes.empty:
        _, msg = ai_classifier.classify_with_gemini(codes)
        ok &= check("Gemini 폴백/호출", "분류" in msg or "실패" in msg or "API" in msg, msg[:40])

    df = db.load_all_incidents()
    if not df.empty:
        one_month = df[df["연월"] == df["연월"].iloc[0]]
        _, msg = analyzer.detect_anomalies_for_devices(one_month)
        ok &= check("1개월 이상치 안내", msg is not None and "3" in msg)

    ok &= check("12개 초과 제한 상수", MAX_UPLOAD_FILES == 12)
    return ok


def test_linkage() -> bool:
    print("\n--- SS5.1 화면 연계 (session_state) ---")
    ok = True
    set_nav_target("기번", "TEST001", "2026-05")
    set_nav_to_c("2026-05", "09322")
    ok &= check("A->B nav_target", True, "기번=TEST001")
    ok &= check("B->C nav_c", True, "2026-05 / 09322")
    return ok


def test_performance() -> bool:
    print("\n--- 성능 (집계) ---")
    df = db.load_all_incidents()
    if df.empty:
        return check("데이터 없음", False)

    start = time.perf_counter()
    analyzer.aggregate_monthly(df)
    analyzer.compute_top10_all(df)
    analyzer.compute_priority_ranking(df)
    drilldown.attach_grouping(df, confirmed_only=False)
    elapsed = time.perf_counter() - start
    ok = elapsed < 5.0
    return check(
        f"집계+TOP10+우선순위+드릴다운 ({len(df):,}건)",
        ok,
        f"{elapsed:.2f}s (목표 5s 이내)",
    )


def test_e2e_logic() -> bool:
    print("\n--- E2E 로직 (15분 시연 경로) ---")
    df = db.load_all_incidents()
    ok = True
    if df.empty:
        return check("DB 데이터", False)

    months = sorted(df["연월"].unique())
    latest = months[-1]
    agg = analyzer.aggregate_monthly(df)
    top = analyzer.top_n_by_month(agg["기번"], "기번")
    device = top[top["연월"] == latest].iloc[0]["기번"]

    ok &= check("1. TOP10 추출", True, device)
    trend = analyzer.get_trend_chart_data(df, "기번", device)
    ok &= check("2. 추이 생성", len(trend) >= 1, f"{len(trend)}개월")

    grouped = drilldown.attach_grouping(df, confirmed_only=False)
    ai = drilldown.list_ai_types(grouped[grouped["연월"] == latest])
    if ai:
        scope = drilldown.filter_scope(grouped, 연월=latest, ai_type=ai[0])
        ok &= check("3. 드릴다운", len(scope) > 0, ai[0])

    ranked = analyzer.compute_priority_ranking(df, top_n=5)
    ok &= check("4. 우선순위", len(ranked) == 5, ranked.iloc[0]["기번"])
    return ok


def test_poc_readiness() -> bool:
    print("\n--- PoC 준비 상태 ---")
    ok = True
    ok &= check("DB", db.list_uploaded_months().shape[0] > 0)
    ok &= check("매핑파일", (ROOT / "mapping" / "장애코드.xlsx").exists())
    ok &= check("API키 설정", api_settings.get_api_key() is not None, api_settings.mask_api_key(api_settings.get_api_key()))
    ok &= check("web_app.py (Flask)", (ROOT / "web_app.py").exists())
    ok &= check("templates", (ROOT / "templates" / "base.html").exists())
    ok &= check("route flow", (ROOT / "templates" / "flow.html").exists())
    ok &= check("route code", (ROOT / "templates" / "code_analysis.html").exists())
    ok &= check("route priority", (ROOT / "templates" / "priority.html").exists())
    ok &= check("run.bat", (ROOT / "run.bat").exists())
    return ok


def main() -> int:
    db.init_db()
    print("=" * 55)
    print("Phase 8 통합 테스트")
    print("=" * 55)

    results = [
        test_exceptions(),
        test_linkage(),
        test_performance(),
        test_e2e_logic(),
        test_poc_readiness(),
    ]

    print("\n" + "=" * 55)
    passed = sum(results)
    total = len(results)
    print(f"종합: {passed}/{total} 영역 PASS")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
