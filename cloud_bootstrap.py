"""배포/최초 실행 시 DB·매핑·샘플 데이터 준비."""
from __future__ import annotations

import io
from pathlib import Path

import db
import data_loader
from config import MAPPING_FILE, SAMPLE_DIR


class _DiskUpload(io.BytesIO):
    """parse_uploaded_file()이 기대하는 .name 속성을 갖춘 파일 객체."""

    def __init__(self, path: Path):
        super().__init__(path.read_bytes())
        self.name = path.name


def ensure_runtime_data() -> None:
    """SQLite 초기화 후, 데이터가 없으면 매핑·샘플 Excel을 생성·적재."""
    db.init_db()
    if not db.load_all_incidents().empty:
        return

    _ensure_mapping()
    _ensure_sample_files()
    _load_sample_uploads()


def _ensure_mapping() -> None:
    if MAPPING_FILE.exists():
        return
    from scripts.create_sample_data import create_mapping_file

    create_mapping_file()


def _ensure_sample_files() -> None:
    if any(SAMPLE_DIR.glob("*.xlsx")):
        return
    from scripts.create_sample_data import main as create_samples

    create_samples()


def _load_sample_uploads() -> None:
    for path in sorted(SAMPLE_DIR.glob("*.xlsx")):
        result = data_loader.parse_uploaded_file(_DiskUpload(path))
        if not result.ok or result.df is None:
            continue
        db.save_month_data(result.df, result.연월, result.filename, mode="replace")
