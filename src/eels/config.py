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
    env = os.environ.get("EELS_VAR")
    if env:
        return Path(env).expanduser().resolve()
    # Repo checkout: <repo>/src/eels -> <repo>/var
    repo = PACKAGE_DIR.parent.parent
    if (repo / "pyproject.toml").exists():
        return repo / "var"
    return Path.home() / "Library" / "Application Support" / "eels"


VAR_DIR = _find_var_dir()
# Converted models (Opus-MT in CTranslate2 format) are not per-run data; keep them next to the HF cache.
MODEL_DIR = Path(os.environ.get("EELS_MODELS", Path.home() / ".cache" / "eels")).expanduser()
SETTINGS_PATH = VAR_DIR / "settings.json"
# Tracked in git (unlike var/): benchmark reports and findings, so work on another Mac can build on them.
FINDINGS_DIR = PACKAGE_DIR.parent.parent / "docs" / "findings"
TRANSCRIPT_DIR = VAR_DIR / "transcripts"
LOG_DIR = VAR_DIR / "logs"
TIMEZONE = "Europe/Istanbul"

SpokenLang = Literal["en", "tr", "auto"]
Engine = Literal["local", "gemini"]
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
    # "local": Whisper + translation model on this Mac. "gemini": Gemini Live Translate (cloud, needs
    # GEMINI_API_KEY and internet); the local models stay loaded and take over if Gemini fails.
    engine: Engine = "local"
    gemini_model: str = "gemini-3.5-live-translate-preview"
    # Which account reaches Gemini: Google Cloud (Vertex AI express mode, Cloud credits apply) or AI Studio.
    gemini_backend: Literal["vertex", "ai_studio"] = "vertex"
    # Vertex AI with an API key needs the full model address: projects/<project>/locations/<region>/...
    gemini_vertex_project: str = ""  # your Google Cloud project ID or number (Setup, Gemini)
    gemini_vertex_location: str = "global"  # where Google lists Live Translate
    # Keep the local models loaded while Gemini is on screen (~3 GB): instant fallback. Off: they
    # are unloaded and load again (~3 s) only if Gemini fails.
    gemini_standby: bool = True
    # Added by the operator in the control panel, after the generated program instruction.
    gemini_extra_instruction: str = Field("", max_length=4000)
    # Local models: keys from models.CATALOG.
    speech_model: str = "whisper-turbo-15s"
    translation_model: str = "opus-mt"
    # Per direction (None = translation_model): e.g. Opus-MT for TR->EN, a larger model for EN->TR.
    translation_model_en_tr: str | None = None
    translation_model_tr_en: str | None = None

    # Streaming policy
    asr_step_s: float = Field(0.5, ge=0.2, le=3.0)
    # Final text is translated per sentence (see ClauseSegmenter); these are the cut rules.
    sentence_max_words: int = Field(30, ge=8, le=80)
    sentence_max_s: float = Field(12.0, ge=3.0, le=30.0)
    sentence_gap_s: float = Field(1.0, ge=0.4, le=5.0)
    pause_flush_s: float = Field(0.4, ge=0.1, le=3.0)
    utterance_end_s: float = Field(0.6, ge=0.2, le=3.0)
    max_backlog_s: float = Field(6.0, ge=2.0, le=30.0)


def translation_model_for(settings: Settings, src: str, tgt: str) -> str:
    """The translation model key used for one direction."""
    if (src, tgt) == ("en", "tr") and settings.translation_model_en_tr:
        return settings.translation_model_en_tr
    if (src, tgt) == ("tr", "en") and settings.translation_model_tr_en:
        return settings.translation_model_tr_en
    return settings.translation_model


def migrate_settings(data: dict) -> dict:
    """Bring a settings file from an older eels up to date: model repo names become catalog keys,
    and a key that is not in the catalog any more falls back to the default."""
    from . import models

    data = dict(data)
    if "asr_model" in data:
        spec = {"model": data.pop("asr_model"), "audio_ctx": data.pop("asr_audio_ctx", "750")}
        found = models.find_by_spec("speech", spec)
        data["speech_model"] = found.key if found else models.DEFAULT_SPEECH
    for old, new in (
        ("mt_model", "translation_model"),
        ("mt_model_en_tr", "translation_model_en_tr"),
        ("mt_model_tr_en", "translation_model_tr_en"),
    ):
        if old in data:
            value = data.pop(old)
            found = models.find_by_spec("translation", {"model": value}) if value else None
            data[new] = found.key if found else (models.DEFAULT_TRANSLATION if new == "translation_model" else None)
    for key, job, default in (
        ("speech_model", "speech", models.DEFAULT_SPEECH),
        ("translation_model", "translation", models.DEFAULT_TRANSLATION),
        ("translation_model_en_tr", "translation", None),
        ("translation_model_tr_en", "translation", None),
    ):
        value = data.get(key)
        if value is not None and (value not in models.BY_KEY or models.BY_KEY[value].job != job):
            data[key] = default
    return data


class SettingsStore:
    """Thread-safe settings holder that writes atomically on every change."""

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._settings = self._load()

    def _load(self) -> Settings:
        if self.path.exists():
            try:
                data = migrate_settings(json.loads(self.path.read_text()))
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
