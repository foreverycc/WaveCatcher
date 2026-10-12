"""Persistent report and daily schedule preferences (independent of the browser)."""
import json
import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = ROOT / "backend/data/report_settings.json"


class ReportSettings(BaseModel):
    output_directory: str = str(ROOT / "reports")
    chart_days: int = Field(default=365, ge=7, le=730)
    signal_days: int = Field(default=7, ge=1, le=365)
    schedule_enabled: bool = True
    schedule_time: str = "13:30"
    timezone: str = "America/Los_Angeles"
    indices: list[str] = Field(default_factory=lambda: ["SPX", "QQQ", "DJI", "IWM"])

    @field_validator("indices")
    @classmethod
    def unique_indices(cls, values):
        return list(dict.fromkeys(values))

    @field_validator("schedule_time")
    @classmethod
    def valid_time(cls, value):
        import re
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Time must be HH:MM (24-hour time)")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone such as America/Los_Angeles")
        return value

    @field_validator("output_directory")
    @classmethod
    def valid_directory(cls, value):
        path = Path(value.strip()).expanduser()
        if not value.strip() or not path.is_absolute():
            raise ValueError("Enter an absolute folder path")
        return str(path.resolve())


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temporary = f.name
            json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_settings():
    if SETTINGS_PATH.exists():
        return ReportSettings(**json.loads(SETTINGS_PATH.read_text()))
    return ReportSettings()


def save_settings(settings):
    from app.services.index_config import load_index_config
    if settings.schedule_enabled and not settings.indices:
        raise ValueError("Select at least one index for scheduled runs")
    invalid = set(settings.indices) - set(load_index_config())
    if invalid:
        raise ValueError(f"Unknown indices: {', '.join(sorted(invalid))}")
    folder = Path(settings.output_directory)
    folder.mkdir(parents=True, exist_ok=True)
    # Verify actual write permission rather than relying on os.access.
    with tempfile.TemporaryFile(dir=folder):
        pass
    atomic_json(SETTINGS_PATH, settings.model_dump())
    return settings
