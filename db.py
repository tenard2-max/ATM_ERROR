"""SQLite 데이터베이스 접근 계층."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable

import pandas as pd

from config import DB_PATH, DATA_DIR


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                연월 TEXT NOT NULL,
                점번 TEXT,
                지점명 TEXT,
                기번 TEXT,
                기종 TEXT,
                발생일자 TEXT,
                세부장애 TEXT,
                장애내용 TEXT,
                장애코드2 TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_incidents_연월 ON incidents(연월);
            CREATE INDEX IF NOT EXISTS idx_incidents_기번 ON incidents(기번);

            CREATE TABLE IF NOT EXISTS upload_meta (
                연월 TEXT PRIMARY KEY,
                건수 INTEGER NOT NULL,
                source_filename TEXT,
                uploaded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS grouping_rules (
                장애코드2 TEXT PRIMARY KEY,
                세부장애 TEXT,
                장애내용 TEXT,
                ai_type TEXT,
                confirmed_type TEXT,
                is_confirmed INTEGER DEFAULT 0,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS anomaly_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_value TEXT NOT NULL,
                연월 TEXT NOT NULL,
                confirmed INTEGER DEFAULT 0,
                memo TEXT,
                updated_at TEXT,
                UNIQUE(target_type, target_value, 연월)
            );
            """
        )


@contextmanager
def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def list_uploaded_months() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT 연월, 건수, source_filename, uploaded_at FROM upload_meta ORDER BY 연월",
            conn,
        )


def month_exists(연월: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM upload_meta WHERE 연월 = ?", (연월,)
        ).fetchone()
    return row is not None


def delete_month(연월: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM incidents WHERE 연월 = ?", (연월,))
        conn.execute("DELETE FROM upload_meta WHERE 연월 = ?", (연월,))


def save_month_data(
    df: pd.DataFrame,
    연월: str,
    source_filename: str,
    mode: str = "replace",
) -> int:
    if mode == "replace":
        delete_month(연월)

    records = df.copy()
    records["연월"] = 연월
    columns = [
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
    payload = records[columns]

    with get_connection() as conn:
        payload.to_sql("incidents", conn, if_exists="append", index=False)
        total_count = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE 연월 = ?", (연월,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO upload_meta (연월, 건수, source_filename, uploaded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(연월) DO UPDATE SET
                건수 = excluded.건수,
                source_filename = excluded.source_filename,
                uploaded_at = excluded.uploaded_at
            """,
            (연월, total_count, source_filename, datetime.now().isoformat(timespec="seconds")),
        )
    return len(payload)


def load_all_incidents() -> pd.DataFrame:
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM incidents", conn)
    if df.empty:
        return df
    df["발생일자"] = pd.to_datetime(df["발생일자"], errors="coerce")
    return df


def save_grouping_rules(df: pd.DataFrame, confirmed: bool = False) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        for _, row in df.iterrows():
            conn.execute(
                """
                INSERT INTO grouping_rules
                    (장애코드2, 세부장애, 장애내용, ai_type, confirmed_type, is_confirmed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(장애코드2) DO UPDATE SET
                    세부장애 = excluded.세부장애,
                    장애내용 = excluded.장애내용,
                    ai_type = excluded.ai_type,
                    confirmed_type = excluded.confirmed_type,
                    is_confirmed = excluded.is_confirmed,
                    updated_at = excluded.updated_at
                """,
                (
                    str(row["장애코드2"]),
                    str(row.get("세부장애", "")),
                    str(row.get("장애내용", "")),
                    str(row.get("ai_type", "")),
                    str(row.get("confirmed_type", row.get("ai_type", ""))),
                    1 if confirmed else 0,
                    now,
                ),
            )


def load_grouping_rules(confirmed_only: bool = False) -> pd.DataFrame:
    query = "SELECT * FROM grouping_rules"
    if confirmed_only:
        query += " WHERE is_confirmed = 1"
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


def is_grouping_confirmed() -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM grouping_rules WHERE is_confirmed = 1"
        ).fetchone()
    return bool(row and row[0] > 0)


def save_anomaly_note(
    target_type: str,
    target_value: str,
    연월: str,
    confirmed: bool,
    memo: str,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO anomaly_notes (target_type, target_value, 연월, confirmed, memo, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_type, target_value, 연월) DO UPDATE SET
                confirmed = excluded.confirmed,
                memo = excluded.memo,
                updated_at = excluded.updated_at
            """,
            (target_type, target_value, 연월, 1 if confirmed else 0, memo, now),
        )


def load_anomaly_notes(
    target_type: str | None = None,
    target_value: str | None = None,
) -> pd.DataFrame:
    query = "SELECT * FROM anomaly_notes"
    params: list = []
    clauses = []
    if target_type:
        clauses.append("target_type = ?")
        params.append(target_type)
    if target_value:
        clauses.append("target_value = ?")
        params.append(target_value)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY 연월"
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)
