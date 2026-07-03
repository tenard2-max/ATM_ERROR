"""Excel 업로드 파싱·검증·장애코드2 매핑."""
from __future__ import annotations

from dataclasses import dataclass, field

from typing import BinaryIO

import pandas as pd

from config import (
    MAPPING_FILE,
    MAPPING_SOURCE_COL,
    MAPPING_TARGET_COL,
    REQUIRED_COLUMNS,
)


@dataclass
class ParseResult:
    ok: bool
    filename: str
    df: pd.DataFrame | None = None
    연월: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmapped_codes: list[str] = field(default_factory=list)


def read_excel_file(file_obj: BinaryIO, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith(".xlsx"):
        return pd.read_excel(file_obj, engine="openpyxl")
    if name.endswith(".xls"):
        return pd.read_excel(file_obj, engine="xlrd")
    raise ValueError("지원하지 않는 파일 형식입니다. (.xls, .xlsx 만 가능)")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def validate_required_columns(df: pd.DataFrame) -> list[str]:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    return missing


def load_code_mapping() -> dict[str, str]:
    if not MAPPING_FILE.exists():
        return {}
    mapping_df = pd.read_excel(MAPPING_FILE, engine="openpyxl")
    mapping_df.columns = [str(c).strip() for c in mapping_df.columns]
    if MAPPING_SOURCE_COL not in mapping_df.columns:
        raise ValueError(
            f"매핑 파일에 '{MAPPING_SOURCE_COL}' 컬럼이 없습니다: {MAPPING_FILE}"
        )
    target_col = MAPPING_TARGET_COL
    if target_col not in mapping_df.columns:
        target_col = mapping_df.columns[-1]
    mapping_df[MAPPING_SOURCE_COL] = mapping_df[MAPPING_SOURCE_COL].astype(str).str.strip()
    mapping_df[target_col] = mapping_df[target_col].astype(str).str.strip()
    return dict(zip(mapping_df[MAPPING_SOURCE_COL], mapping_df[target_col]))


def apply_code2_mapping(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    if "장애코드2" not in out.columns:
        out["장애코드2"] = pd.NA

    mapping = load_code_mapping()
    out["세부장애"] = out["세부장애"].astype(str).str.strip()
    out["장애코드2"] = out["장애코드2"].astype(object)

    mask_missing = out["장애코드2"].isna() | (out["장애코드2"].astype(str).str.strip() == "")
    out.loc[mask_missing, "장애코드2"] = out.loc[mask_missing, "세부장애"].map(mapping)

    unmapped = sorted(
        out.loc[out["장애코드2"].isna(), "세부장애"].dropna().unique().tolist()
    )
    out["장애코드2"] = out["장애코드2"].fillna(out["세부장애"])
    return out, unmapped


def extract_year_month(df: pd.DataFrame) -> str:
    dates = pd.to_datetime(df["발생일자"], errors="coerce")
    valid = dates.dropna()
    if valid.empty:
        raise ValueError("유효한 발생일자가 없습니다.")
    month = valid.dt.to_period("M").mode()
    if len(month) != 1:
        raise ValueError("파일 내 발생일자가 여러 연월에 걸쳐 있습니다. 월별 파일 1개를 업로드하세요.")
    return str(month.iloc[0])


def preprocess_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_columns(df)
    out = out.dropna(how="all")
    if out.empty:
        raise ValueError("빈 파일입니다.")

    missing = validate_required_columns(out)
    if missing:
        raise ValueError(f"필수 컬럼 누락: {', '.join(missing)}")

    out, _ = apply_code2_mapping(out)
    out["발생일자"] = pd.to_datetime(out["발생일자"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["연월"] = extract_year_month(out)
    for col in ["점번", "지점명", "기번", "기종", "세부장애", "장애내용", "장애코드2"]:
        out[col] = out[col].astype(str).str.strip()
    return out


def parse_uploaded_file(uploaded_file) -> ParseResult:
    filename = uploaded_file.name
    try:
        raw = read_excel_file(uploaded_file, filename)
        df = preprocess_dataframe(raw)
        _, unmapped = apply_code2_mapping(df)
        result = ParseResult(
            ok=True,
            filename=filename,
            df=df,
            연월=df["연월"].iloc[0],
            unmapped_codes=unmapped,
        )
        if unmapped:
            result.warnings.append(
                f"매핑되지 않은 세부장애 {len(unmapped)}건 — 장애코드.xlsx 갱신 후 재업로드 권장"
            )
        return result
    except Exception as exc:
        return ParseResult(ok=False, filename=filename, errors=[str(exc)])


def parse_uploaded_files(uploaded_files) -> list[ParseResult]:
    return [parse_uploaded_file(f) for f in uploaded_files]
