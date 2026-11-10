"""Settings and paths. Settings persist to var/settings.json."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
DATA_DIR = PACKAGE_DIR / "data"


def _find_var_dir() -> Path:
    env = os.environ.get("LIVE_TRANSLATE_VAR")
    if env:
        return Path(env).expanduser().resolve()
    # Repo checkout: <repo>/src/live_translate -> <repo>/var
    repo = PACKAGE_DIR.parent.parent
    if (repo / "pyproject.toml").exists():
        return repo / "var"
    return Path.home() / "Library" / "Application Support" / "live-translate"


VAR_DIR = _find_var_dir()
# Converted models (Opus-MT in CTranslate2 format) are not per-run data; keep them next to the HF cache.
MODEL_DIR = Path(os.environ.get("LIVE_TRANSLATE_MODELS", Path.home() / ".cache" / "live-translate")).expanduser()
SETTINGS_PATH = VAR_DIR / "settings.json"
# Tracked in git (unlike var/): benchmark reports and findings, so work on another Mac can build on them.
FINDINGS_DIR = PACKAGE_DIR.parent.parent / "docs" / "findings"
TRANSCRIPT_DIR = VAR_DIR / "transcripts"
LOG_DIR = VAR_DIR / "logs"
TIMEZONE = "Europe/Istanbul"

SpokenLang = Literal["en", "tr", "auto"]
Channel = Literal["mono", "left", "right"]


class Settings(BaseModel):
    # Audio
    device_name: str | None = None  # None means system default input
    channel: Channel = "mono"
    auto_gain: bool = True  # lift quiet inputs (up to +26 dB) before speech detection

    # Language
    spoken_language: SpokenLang = "en"
    auto_from_schedule: bool = True
    gender_neutral: bool = True  # Turkish -> English: "they" instead of a guessed he/she
    schedule_applied_start: str | None = None  # start of the session whose language was last applied

    # Overlay
    visible: bool = True
    font_size: int = Field(56, ge=20, le=120)
    lines: int = Field(2, ge=1, le=4)
    line_height: float = Field(1.36, ge=1.0, le=2.0)  # >= Open Sans ascent+descent, so lines never overlap
    shadow: bool = True
    vertical_offset: int = Field(0, ge=-90, le=90)
    clear_after_s: float = Field(6.0, ge=1.0, le=120.0)
    interim: bool = True

    # Models
    asr_model: str = "mlx-community/whisper-large-v3-turbo"
    asr_audio_ctx: str = "750"  # encoder window: "full" (30 s) or positions ("750" = 15 s, ~2x faster)
    mt_model: str = "opus-mt"  # Opus-MT tc-big on the CPU; TranslateGemma via its mlx-community repo name
    # Per-direction override (None = use mt_model): e.g. Opus-MT for TR->EN, a larger model for EN->TR.
    mt_model_en_tr: str | None = None
    mt_model_tr_en: str | None = None

    # Streaming policy
    asr_step_s: float = Field(0.5, ge=0.2, le=3.0)
    # Final text is translated per sentence (see ClauseSegmenter); these are the cut rules.
    sentence_max_words: int = Field(30, ge=8, le=80)
    sentence_max_s: float = Field(12.0, ge=3.0, le=30.0)
    sentence_gap_s: float = Field(1.0, ge=0.4, le=5.0)
    pause_flush_s: float = Field(0.4, ge=0.1, le=3.0)
    utterance_end_s: float = Field(0.6, ge=0.2, le=3.0)
    max_backlog_s: float = Field(6.0, ge=2.0, le=30.0)


def mt_for(settings: Settings, src: str, tgt: str) -> str:
    """The translation model used for one direction."""
    if (src, tgt) == ("en", "tr") and settings.mt_model_en_tr:
        return settings.mt_model_en_tr
    if (src, tgt) == ("tr", "en") and settings.mt_model_tr_en:
        return settings.mt_model_tr_en
    return settings.mt_model


class SettingsStore:
    """Thread-safe settings holder that writes atomically on every change."""

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._settings = self._load()

    def _load(self) -> Settings:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                known = {k: v for k, v in data.items() if k in Settings.model_fields}
                return Settings.model_validate(known)
            except Exception as exc:  # corrupt file: keep a copy, start from defaults
                backup = self.path.with_suffix(".broken.json")
                self.path.replace(backup)
                print(f"[settings] could not read {self.path} ({exc}); moved to {backup}")
        return Settings()

    @property
    def value(self) -> Settings:
        with self._lock:
            return self._settings

    def update(self, **changes) -> Settings:
        with self._lock:
            merged = self._settings.model_dump() | changes
            self._settings = Settings.model_validate(merged)
            self._save(self._settings)
            return self._settings

    def _save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(settings.model_dump(), indent=2, ensure_ascii=False))
        os.replace(tmp, self.path)
