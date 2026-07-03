"""집계·TOP10·이상치 분석 엔진."""
from __future__ import annotations

import calendar

import pandas as pd

from config import ANOMALY_SIGMA, ANOMALY_WINDOW, PRIORITY_TOP_N, PRIORITY_WEIGHTS, TOP_N


def ensure_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    if "연월" not in out.columns and "발생일자" in out.columns:
        out["연월"] = pd.to_datetime(out["발생일자"]).dt.to_period("M").astype(str)
    return out


def monthly_counts(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    data = ensure_dataframe(df)
    if data.empty:
        return pd.DataFrame(columns=["연월", group_col, "장애건수"])
    grouped = (
        data.groupby(["연월", group_col], dropna=False)
        .size()
        .reset_index(name="장애건수")
        .sort_values(["연월", "장애건수"], ascending=[True, False])
    )
    return grouped


def aggregate_monthly(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "기종": monthly_counts(df, "기종"),
        "지점": monthly_counts(df, "지점명"),
        "기번": monthly_counts(df, "기번"),
    }


def top_n_by_month(counts: pd.DataFrame, group_col: str, n: int = TOP_N) -> pd.DataFrame:
    if counts.empty:
        return counts
    return (
        counts.sort_values(["연월", "장애건수"], ascending=[True, False])
        .groupby("연월", as_index=False)
        .head(n)
    )


def attach_branch_name(
    df: pd.DataFrame,
    top_df: pd.DataFrame,
    selected_month: str | None = None,
    device_col: str = "기번",
    branch_col: str = "지점명",
    label: str = "지점이름",
) -> pd.DataFrame:
    """기번 TOP 표에 지점명 컬럼 추가 (기번 옆)."""
    if top_df.empty or device_col not in top_df.columns:
        return top_df

    data = ensure_dataframe(df)
    if selected_month:
        data = data[data["연월"] == selected_month]
    if data.empty:
        out = top_df.copy()
        out[label] = ""
        return out

    def _pick_branch(series: pd.Series) -> str:
        modes = series.mode()
        return str(modes.iloc[0]) if not modes.empty else str(series.iloc[0])

    branch_map = data.groupby(device_col)[branch_col].agg(_pick_branch)
    out = top_df.copy()
    out[label] = out[device_col].map(branch_map).fillna("")

    cols = [c for c in out.columns if c != label]
    insert_at = cols.index(device_col) + 1
    cols.insert(insert_at, label)
    return out[cols]


def daily_trend_by_entities(
    df: pd.DataFrame,
    selected_month: str,
    entity_col: str,
    entity_values: list[str],
) -> tuple[pd.DataFrame, int]:
    """선택 연월·대상별 일(1~말일) 장애건수 추이."""
    empty = pd.DataFrame(columns=["일", entity_col, "장애건수"])
    if not entity_values:
        return empty, 31

    year, month = map(int, selected_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    data = ensure_dataframe(df)
    subset = data[(data["연월"] == selected_month) & (data[entity_col].isin(entity_values))]
    if subset.empty:
        rows = [
            {"일": day, entity_col: ent, "장애건수": 0}
            for ent in entity_values
            for day in range(1, last_day + 1)
        ]
        return pd.DataFrame(rows), last_day

    work = subset.copy()
    work["일"] = pd.to_datetime(work["발생일자"], errors="coerce").dt.day
    work = work.dropna(subset=["일"])
    work["일"] = work["일"].astype(int)

    grouped = (
        work.groupby(["일", entity_col])
        .size()
        .reset_index(name="장애건수")
    )

    rows: list[dict] = []
    for ent in entity_values:
        ent_data = grouped[grouped[entity_col] == ent]
        count_map = dict(zip(ent_data["일"], ent_data["장애건수"]))
        for day in range(1, last_day + 1):
            rows.append({"일": day, entity_col: ent, "장애건수": int(count_map.get(day, 0))})

    return pd.DataFrame(rows), last_day


FLOW_MONTH_TICKS = [1, 5, 10, 15, 20, 25, 30]


def five_day_bucket_counts(
    df: pd.DataFrame,
    selected_month: str,
    key_col: str,
    key_value: str,
) -> tuple[pd.DataFrame, int]:
    """선택 연월·대상의 5일 구간별 장애건수."""
    year, month = map(int, selected_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    data = ensure_dataframe(df)
    subset = data[(data["연월"] == selected_month) & (data[key_col] == key_value)].copy()
    if subset.empty:
        empty = pd.DataFrame(columns=["구간", "기준일", "장애건수"])
        return empty, last_day

    subset["일"] = pd.to_datetime(subset["발생일자"], errors="coerce").dt.day
    subset = subset.dropna(subset=["일"])
    subset["일"] = subset["일"].astype(int)

    bucket_ranges = [
        (1, 5, 3),
        (6, 10, 8),
        (11, 15, 13),
        (16, 20, 18),
        (21, 25, 23),
        (26, last_day, min(28, last_day)),
    ]
    rows: list[dict] = []
    for day_start, day_end, anchor in bucket_ranges:
        if day_start > last_day:
            break
        end = min(day_end, last_day)
        count = int(subset[(subset["일"] >= day_start) & (subset["일"] <= end)].shape[0])
        rows.append(
            {
                "구간": f"{day_start}~{end}일",
                "기준일": anchor if end >= anchor else end,
                "장애건수": count,
            }
        )

    return pd.DataFrame(rows), last_day


def available_months_for_entity(
    df: pd.DataFrame,
    key_col: str,
    key_value: str,
) -> list[str]:
    data = ensure_dataframe(df)
    subset = data[data[key_col] == key_value]
    if subset.empty:
        return []
    return sorted(subset["연월"].unique().tolist())


def _ranked_entities(
    df: pd.DataFrame,
    key_col: str,
    month: str | None = None,
) -> pd.DataFrame:
    """key_col 기준 장애건수 집계 (내림차순)."""
    data = ensure_dataframe(df)
    if month:
        data = data[data["연월"] == month]
    if data.empty or key_col not in data.columns:
        return pd.DataFrame(columns=[key_col, "장애건수"])

    return (
        data.groupby(key_col, dropna=False)
        .size()
        .reset_index(name="장애건수")
        .sort_values(["장애건수", key_col], ascending=[False, True])
    )


def entity_select_options(
    df: pd.DataFrame,
    key_col: str,
    month: str | None = None,
    *,
    show_count: bool = False,
) -> list[dict[str, str | int]]:
    """드롭다운용 옵션 — 장애건수 내림차순."""
    ranked = _ranked_entities(df, key_col, month)
    if ranked.empty:
        return []

    options: list[dict[str, str | int]] = []
    for _, row in ranked.iterrows():
        value = str(row[key_col])
        count = int(row["장애건수"])
        label = f"{value} ({count:,}건)" if show_count else value
        options.append({"value": value, "label": label, "count": count})
    return options


def entities_by_fault_count(
    df: pd.DataFrame,
    key_col: str,
    month: str | None = None,
) -> list[str]:
    """장애건수 내림차순 엔티티 목록 (드롭다운용)."""
    return [str(item["value"]) for item in entity_select_options(df, key_col, month)]


def compute_top10_all(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    aggregates = aggregate_monthly(df)
    return {key: top_n_by_month(value, key) for key, value in aggregates.items()}


def monthly_trend(df: pd.DataFrame, key_col: str, key_value: str) -> pd.DataFrame:
    data = ensure_dataframe(df)
    subset = data[data[key_col] == key_value]
    if subset.empty:
        return pd.DataFrame(columns=["연월", "장애건수", "전월대비증감률"])
    trend = (
        subset.groupby("연월")
        .size()
        .reset_index(name="장애건수")
        .sort_values("연월")
    )
    trend["전월대비증감률"] = trend["장애건수"].pct_change().fillna(0) * 100
    return trend


def benchmark_series(df: pd.DataFrame, key_col: str, key_value: str) -> dict[str, pd.DataFrame]:
    data = ensure_dataframe(df)
    target = monthly_trend(data, key_col, key_value)
    if key_col == "기번" and not data.empty:
        model = data.loc[data["기번"] == key_value, "기종"].iloc[0]
        model_avg = monthly_trend(data, "기종", model).rename(
            columns={"장애건수": "동일기종평균"}
        )
        target = target.merge(model_avg[["연월", "동일기종평균"]], on="연월", how="left")
    overall = (
        data.groupby("연월")
        .size()
        .reset_index(name="전체평균")
    )
    month_count = data["연월"].nunique()
    overall["전체평균"] = overall["전체평균"] / max(data[key_col].nunique(), 1)
    return {"target": target, "overall": overall}


def detect_anomalies(
    counts: pd.DataFrame,
    entity_col: str,
    window: int = ANOMALY_WINDOW,
    sigma: float = ANOMALY_SIGMA,
) -> tuple[pd.DataFrame, str | None]:
    if counts.empty:
        return pd.DataFrame(), "집계 데이터가 없습니다."

    months = counts["연월"].nunique()
    if months < window:
        return pd.DataFrame(), f"이상치 탐지에는 최소 {window}개월 이상 데이터가 필요합니다. (현재 {months}개월)"

    work = counts.copy().sort_values([entity_col, "연월"])
    work["이동평균"] = work.groupby(entity_col)["장애건수"].transform(
        lambda s: s.rolling(window, min_periods=window).mean()
    )
    work["표준편차"] = work.groupby(entity_col)["장애건수"].transform(
        lambda s: s.rolling(window, min_periods=window).std()
    )
    work["이상치여부"] = (
        work["이동평균"].notna()
        & work["표준편차"].notna()
        & ((work["장애건수"] - work["이동평균"]).abs() > sigma * work["표준편차"])
    )
    work["평소대비증가율"] = (
        (work["장애건수"] - work["이동평균"]) / work["이동평균"].replace(0, pd.NA) * 100
    ).round(1)

    anomalies = work[work["이상치여부"]].copy()
    anomalies = anomalies.rename(columns={entity_col: "대상"})
    return anomalies, None


def detect_anomalies_for_devices(df: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    counts = monthly_counts(df, "기번")
    return detect_anomalies(counts, "기번")


def enrich_trend_with_stats(
    trend: pd.DataFrame,
    window: int = ANOMALY_WINDOW,
    sigma: float = ANOMALY_SIGMA,
) -> pd.DataFrame:
    if trend.empty:
        return trend.copy()
    work = trend.copy().sort_values("연월").reset_index(drop=True)
    work["이동평균"] = work["장애건수"].rolling(window, min_periods=window).mean()
    work["표준편차"] = work["장애건수"].rolling(window, min_periods=window).std()
    work["이상치여부"] = (
        work["이동평균"].notna()
        & work["표준편차"].notna()
        & ((work["장애건수"] - work["이동평균"]).abs() > sigma * work["표준편차"])
    )
    work["평소대비증가율"] = (
        (work["장애건수"] - work["이동평균"]) / work["이동평균"].replace(0, pd.NA) * 100
    ).round(1)
    return work


def get_trend_chart_data(
    df: pd.DataFrame,
    key_col: str,
    key_value: str,
) -> pd.DataFrame:
    data = ensure_dataframe(df)
    trend = monthly_trend(data, key_col, key_value)
    if trend.empty:
        return trend

    work = enrich_trend_with_stats(trend)
    entity_count = max(data[key_col].nunique(), 1)
    overall = data.groupby("연월").size().reset_index(name="전체총건수")
    overall["전체평균"] = (overall["전체총건수"] / entity_count).round(1)
    work = work.merge(overall[["연월", "전체평균"]], on="연월", how="left")

    if key_col == "기번":
        model = data.loc[data["기번"] == key_value, "기종"].iloc[0]
        model_line = monthly_trend(data, "기종", model)[["연월", "장애건수"]].rename(
            columns={"장애건수": "동일기종평균"}
        )
        work = work.merge(model_line, on="연월", how="left")

    return work


def get_entity_anomalies(
    df: pd.DataFrame,
    key_col: str,
    key_value: str,
) -> tuple[pd.DataFrame, str | None]:
    chart_data = get_trend_chart_data(df, key_col, key_value)
    months = len(chart_data)
    if months < ANOMALY_WINDOW:
        return pd.DataFrame(), (
            f"이상치 탐지에는 최소 {ANOMALY_WINDOW}개월 이상 데이터가 필요합니다. (현재 {months}개월)"
        )
    anomalies = chart_data[chart_data["이상치여부"]].copy()
    anomalies["대상"] = key_value
    return anomalies, None


def _normalize_scores(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return pd.Series(0.5, index=series.index)
    return (series - min_val) / (max_val - min_val)


def compute_priority_ranking(
    df: pd.DataFrame,
    top_n: int = PRIORITY_TOP_N,
) -> pd.DataFrame:
    """기번별 위험도 점수 산출 (Phase 7)."""
    data = ensure_dataframe(df)
    if data.empty:
        return pd.DataFrame()

    months = sorted(data["연월"].unique())
    recent_months = months[-3:] if len(months) >= 3 else months
    latest_month = months[-1]
    prev_month = months[-2] if len(months) >= 2 else None

    meta = (
        data.groupby("기번", as_index=False)
        .agg(기종=("기종", "first"), 지점명=("지점명", "first"))
    )
    device_counts = monthly_counts(data, "기번")

    recent = device_counts[device_counts["연월"].isin(recent_months)]
    recent_sum = (
        recent.groupby("기번")["장애건수"].sum().reset_index(name="최근3개월건수")
    )

    latest_counts = device_counts[device_counts["연월"] == latest_month][["기번", "장애건수"]]
    if prev_month:
        prev_counts = device_counts[device_counts["연월"] == prev_month][["기번", "장애건수"]]
        growth = latest_counts.merge(prev_counts, on="기번", how="left", suffixes=("_cur", "_prev"))
        growth["전월대비증가율"] = (
            (growth["장애건수_cur"] - growth["장애건수_prev"].fillna(0))
            / growth["장애건수_prev"].replace(0, pd.NA)
            * 100
        ).fillna(0)
        growth = growth[["기번", "전월대비증가율"]]
    else:
        growth = latest_counts[["기번"]].copy()
        growth["전월대비증가율"] = 0.0

    anomaly_counts = pd.DataFrame({"기번": meta["기번"], "이상치횟수": 0})
    if len(months) >= ANOMALY_WINDOW:
        anomalies, _ = detect_anomalies(device_counts, "기번")
        if not anomalies.empty:
            counts = (
                anomalies.groupby("대상")
                .size()
                .reset_index(name="이상치횟수")
                .rename(columns={"대상": "기번"})
            )
            anomaly_counts = meta[["기번"]].merge(counts, on="기번", how="left")
            anomaly_counts["이상치횟수"] = anomaly_counts["이상치횟수"].fillna(0).astype(int)

    recent_avg = recent.copy()
    recent_avg["월평균"] = recent_avg.groupby("기번")["장애건수"].transform("mean")
    device_monthly_avg = recent_avg.groupby("기번")["월평균"].first().reset_index(name="기번월평균")

    model_recent = recent.merge(meta[["기번", "기종"]], on="기번")
    model_stats = (
        model_recent.groupby("기종")
        .agg(모델총건수=("장애건수", "sum"), 모델기번수=("기번", "nunique"))
        .reset_index()
    )
    model_stats["모델월평균"] = model_stats["모델총건수"] / model_stats["모델기번수"] / max(len(recent_months), 1)

    work = meta.merge(recent_sum, on="기번", how="left")
    work = work.merge(growth, on="기번", how="left")
    work = work.merge(anomaly_counts[["기번", "이상치횟수"]], on="기번", how="left")
    work = work.merge(device_monthly_avg, on="기번", how="left")
    work = work.merge(model_stats[["기종", "모델월평균"]], on="기종", how="left")

    work["최근3개월건수"] = work["최근3개월건수"].fillna(0)
    work["전월대비증가율"] = work["전월대비증가율"].fillna(0)
    work["이상치횟수"] = work["이상치횟수"].fillna(0).astype(int)
    work["기종대비편차"] = (
        (work["기번월평균"] - work["모델월평균"])
        / work["모델월평균"].replace(0, pd.NA)
        * 100
    ).fillna(0).round(1)

    score = pd.Series(0.0, index=work.index)
    for col, weight in PRIORITY_WEIGHTS.items():
        score += _normalize_scores(work[col]) * weight
    work["위험도점수"] = (score * 100).round(1)

    ranked = (
        work.sort_values("위험도점수", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    ranked.insert(0, "순위", range(1, len(ranked) + 1))
    return ranked[
        [
            "순위",
            "기번",
            "기종",
            "지점명",
            "위험도점수",
            "최근3개월건수",
            "전월대비증가율",
            "이상치횟수",
            "기종대비편차",
        ]
    ]
