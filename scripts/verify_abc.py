"""결과 A/B/C 기능 자동 점검 스크립트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import analyzer
import db
import drilldown


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def main() -> int:
    db.init_db()
    df = db.load_all_incidents()
    all_ok = True

    print("=" * 50)
    print("장애관리ATM A/B/C/D 기능 점검")
    print("=" * 50)

    all_ok &= check("DB 데이터 존재", not df.empty, f"{len(df):,}건")

    if df.empty:
        return 1

    months = sorted(df["연월"].unique())
    latest = months[-1]
    all_ok &= check("연월 2개 이상", len(months) >= 2, f"{len(months)}개월")

    # --- Result A ---
    agg = analyzer.aggregate_monthly(df)
    top10 = analyzer.top_n_by_month(agg["기번"], "기번")
    may_top = top10[top10["연월"] == latest]
    all_ok &= check("A: 기종 집계", len(agg["기종"]) >= 3, f"{agg['기종']['장애건수'].max():,}건 max")
    all_ok &= check("A: 지점 TOP10", len(may_top) <= 10 and len(may_top) > 0, f"{len(may_top)}건")
    all_ok &= check("A: 기번 TOP10", may_top["장애건수"].max() > 0, f"max {may_top['장애건수'].max()}")

    # --- Result B ---
    device_counts = analyzer.monthly_counts(df, "기번")
    full_coverage = device_counts.groupby("기번")["연월"].nunique()
    candidates = full_coverage[full_coverage >= 3].index.tolist()
    sample_device = candidates[0] if candidates else may_top.iloc[0]["기번"]

    trend = analyzer.get_trend_chart_data(df, "기번", sample_device)
    all_ok &= check("B: 추이 데이터", len(trend) >= 1, f"{len(trend)}개월")
    all_ok &= check("B: 전월 증감률 컬럼", "전월대비증감률" in trend.columns)
    anomalies, msg = analyzer.get_entity_anomalies(df, "기번", sample_device)
    if len(months) >= 3:
        all_ok &= check("B: 이상치 탐지 실행", msg is None, msg or "OK")
    else:
        all_ok &= check("B: 이상치 3개월 미만 안내", msg is not None)

    # --- Result C ---
    grouped = drilldown.attach_grouping(df, confirmed_only=False)
    all_ok &= check("C: 그룹핑 병합", "confirmed_type" in grouped.columns)
    ai_types = drilldown.list_ai_types(grouped[grouped["연월"] == latest])
    all_ok &= check("C: AI 유형 목록", len(ai_types) > 0, str(ai_types[:3]))
    if ai_types:
        scope = drilldown.filter_scope(grouped, 연월=latest, ai_type=ai_types[0])
        faults = drilldown.distribution(scope, "세부장애")
        all_ok &= check("C: 세부장애 분포", not faults.empty, f"{len(faults)}종")
        if not faults.empty:
            code = faults.iloc[0]["세부장애"]
            scope2 = drilldown.filter_scope(scope, 세부장애=code)
            daily = drilldown.daily_trend(scope2.head(200))
            all_ok &= check("C: 일별 추이", not daily.empty or scope2.empty)

    # --- Result D ---
    ranked = analyzer.compute_priority_ranking(df, top_n=10)
    all_ok &= check("D: 우선순위 TOP10", len(ranked) == 10, f"1위 {ranked.iloc[0]['기번']}")

    print("=" * 50)
    print("종합:", "정상" if all_ok else "일부 실패")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
