"""드릴다운 분석 (모듈별장애분석)."""
from __future__ import annotations

import pandas as pd

import db
from config import FAULT_TYPES, normalize_fault_type


def load_grouping_map(confirmed_only: bool = True) -> pd.DataFrame:
    rules = db.load_grouping_rules(confirmed_only=confirmed_only)
    if rules.empty:
        return pd.DataFrame(columns=["장애코드2", "confirmed_type"])
    return rules[["장애코드2", "confirmed_type"]].drop_duplicates()


def attach_grouping(df: pd.DataFrame, confirmed_only: bool = True) -> pd.DataFrame:
    if df.empty:
        return df
    grouping = load_grouping_map(confirmed_only=confirmed_only)
    if grouping.empty:
        out = df.copy()
        out["confirmed_type"] = "미분류"
        return out
    out = df.merge(grouping, on="장애코드2", how="left")
    out["confirmed_type"] = out["confirmed_type"].map(normalize_fault_type).fillna("미분류")
    return out


def filter_scope(
    df: pd.DataFrame,
    연월: str | None = None,
    ai_type: str | None = None,
    세부장애: str | None = None,
    장애코드2: str | None = None,
    지점명: str | None = None,
    기번: str | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if 연월:
        out = out[out["연월"] == 연월]
    if ai_type:
        out = out[out["confirmed_type"] == ai_type]
    if 세부장애:
        out = out[out["세부장애"] == 세부장애]
    if 장애코드2:
        out = out[out["장애코드2"] == 장애코드2]
    if 지점명:
        out = out[out["지점명"] == 지점명]
    if 기번:
        out = out[out["기번"] == 기번]
    return out


def distribution(df: pd.DataFrame, column: str, top_n: int | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[column, "장애건수"])
    counts = (
        df.groupby(column, dropna=False)
        .size()
        .reset_index(name="장애건수")
        .sort_values("장애건수", ascending=False)
    )
    if top_n:
        counts = counts.head(top_n)
    return counts


def daily_trend(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["발생일", "장애건수"])
    work = df.copy()
    work["발생일"] = pd.to_datetime(work["발생일자"], errors="coerce").dt.date
    return (
        work.groupby("발생일")
        .size()
        .reset_index(name="장애건수")
        .sort_values("발생일")
    )


def daily_trend_in_month(df: pd.DataFrame, month: str) -> pd.DataFrame:
    """선택 연월의 일별(1~말일) 장애 건수."""
    import calendar

    if df.empty:
        return pd.DataFrame(columns=["일", "장애건수"])
    work = df[df["연월"] == month].copy()
    year, mon = month.split("-")
    last_day = calendar.monthrange(int(year), int(mon))[1]
    if work.empty:
        return pd.DataFrame({"일": range(1, last_day + 1), "장애건수": [0] * last_day})
    work["일"] = pd.to_datetime(work["발생일자"], errors="coerce").dt.day
    counts = work.groupby("일").size().reset_index(name="장애건수")
    full = pd.DataFrame({"일": range(1, last_day + 1)})
    out = full.merge(counts, on="일", how="left").fillna(0)
    out["장애건수"] = out["장애건수"].astype(int)
    return out


def monthly_trend_all(df: pd.DataFrame) -> pd.DataFrame:
    """전체 기간 월별 장애 건수."""
    if df.empty:
        return pd.DataFrame(columns=["연월", "장애건수"])
    return (
        df.groupby("연월")
        .size()
        .reset_index(name="장애건수")
        .sort_values("연월")
    )


def list_ai_types(df: pd.DataFrame) -> list[str]:
    present = {
        normalize_fault_type(t)
        for t in df["confirmed_type"].dropna().unique()
        if normalize_fault_type(t) and normalize_fault_type(t) != "미분류"
    }
    ordered = [t for t in FAULT_TYPES if t in present]
    extras = sorted(present - set(FAULT_TYPES))
    return ordered + extras or ["미분류"]
