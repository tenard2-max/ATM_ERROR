"""Gemini API 기반 장애코드 유형 그룹핑 + 키워드 폴백."""
from __future__ import annotations

import csv
import io
import re
from typing import Callable

import pandas as pd

from api_settings import get_api_key
from config import (
    FAULT_TYPES,
    GEMINI_MODEL,
    PASSBOOK_FAULT_CONTENTS,
    classify_fault_content,
    normalize_fault_type,
)


def get_api_key_from_env() -> str | None:
    return get_api_key()


def classify_by_keywords(description: str) -> str:
    return classify_fault_content(description)


def fallback_classify(codes_df: pd.DataFrame) -> pd.DataFrame:
    out = codes_df.copy()
    out["ai_type"] = out["장애내용"].apply(classify_by_keywords)
    out["source"] = "fallback"
    return out


def extract_unique_codes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["장애코드2", "세부장애", "장애내용"])

    rows: list[dict[str, str]] = []
    for code, sub in df.groupby("장애코드2", sort=True):
        details = sorted(sub["세부장애"].dropna().astype(str).unique().tolist())
        contents = sub["장애내용"].dropna().astype(str)
        if not contents.empty:
            modes = contents.mode()
            content = str(modes.iloc[0]) if not modes.empty else str(contents.iloc[0])
        else:
            content = ""
        rows.append(
            {
                "장애코드2": str(code),
                "세부장애": ", ".join(details),
                "장애내용": content,
            }
        )
    return pd.DataFrame(rows)


def attach_detail_lists(
    incidents_df: pd.DataFrame,
    grouping_df: pd.DataFrame,
) -> pd.DataFrame:
    """그룹핑 표에 장애코드2별 전체 세부장애 목록 컬럼 추가."""
    if grouping_df.empty:
        return grouping_df

    detail_map: dict[str, list[str]] = {}
    if not incidents_df.empty:
        detail_map = (
            incidents_df.groupby("장애코드2")["세부장애"]
            .apply(lambda s: sorted(s.dropna().astype(str).unique().tolist()))
            .to_dict()
        )

    out = grouping_df.copy()
    lists: list[list[str]] = []
    for code in out["장애코드2"].astype(str):
        items = detail_map.get(code, [])
        if not items:
            raw = out.loc[out["장애코드2"].astype(str) == code, "세부장애"]
            if not raw.empty:
                items = [part.strip() for part in str(raw.iloc[0]).split(",") if part.strip()]
        lists.append(items)
    out["세부장애목록"] = lists
    return out


def _build_prompt(rows: pd.DataFrame) -> str:
    lines = []
    for _, row in rows.iterrows():
        lines.append(f"{row['장애코드2']},{row['장애내용']}")
    joined = "\n".join(lines)
    allowed = ", ".join(FAULT_TYPES)
    passbook_hint = " · ".join(PASSBOOK_FAULT_CONTENTS)
    return f"""
다음은 ATM 장애코드와 장애내용 목록입니다.
각 항목을 [{allowed}] 중 하나로 분류해서
'코드,장애내용,유형' 형식의 CSV 표로만 답변하세요. 다른 설명은 하지 마세요.
아래 장애내용은 반드시 통장부로 분류하세요: {passbook_hint}

{joined}
""".strip()


def _parse_gemini_csv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not text:
        return result
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:csv)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    reader = csv.reader(io.StringIO(cleaned))
    for row in reader:
        if len(row) < 3:
            continue
        code, _, label = row[0].strip(), row[1].strip(), row[2].strip()
        if label not in FAULT_TYPES:
            label = normalize_fault_type(label) or classify_by_keywords(row[1])
        result[code] = label
    return result


def classify_with_gemini(codes_df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    api_key = get_api_key_from_env()
    if not api_key:
        out = fallback_classify(codes_df)
        return out, "API 키가 없어 기본 규칙으로 분류했습니다."

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = _build_prompt(codes_df)
        response = model.generate_content(prompt)
        mapping = _parse_gemini_csv(getattr(response, "text", "") or "")
        out = codes_df.copy()
        out["ai_type"] = out["장애코드2"].map(mapping).map(normalize_fault_type)
        out["ai_type"] = out["ai_type"].fillna(out["장애내용"].apply(classify_by_keywords))
        out["source"] = "gemini"
        return out, "Gemini API로 유형 분류 초안을 생성했습니다."
    except Exception as exc:
        out = fallback_classify(codes_df)
        return out, "기본 규칙으로 분류했습니다."


def run_classification(
    df: pd.DataFrame,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, str]:
    codes = extract_unique_codes(df)
    if progress_callback:
        progress_callback(f"분류 대상 {len(codes)}건 추출")
    return classify_with_gemini(codes)
