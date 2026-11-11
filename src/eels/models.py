"""The model catalog: every speech and translation model eels can run, in one place.

The app, the control panel, `download-models` and the benchmark all read this. Settings store a
model's key ("whisper-turbo-15s"). `approx_gb` is the weight size on disk, a guide for choosing;
the control panel shows what each loaded model really uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .config import MODEL_DIR

Job = Literal["speech", "translation"]

OPUS_REPOS = ("Helsinki-NLP/opus-mt-tc-big-en-tr", "Helsinki-NLP/opus-mt-tc-big-tr-en")
WHISPER_TURBO = "mlx-community/whisper-large-v3-turbo"
WHISPER_LARGE = "mlx-community/whisper-large-v3-mlx"


@dataclass(frozen=True)
class Conversion:
    """A model with no ready MLX build: download `source`, convert to MLX `bits` into MODEL_DIR/folder."""

    source: str
    bits: int
    folder: str


@dataclass(frozen=True)
class ModelInfo:
    key: str  # stable id: settings, command line, benchmark reports
    job: Job
    name: str  # "Whisper large-v3-turbo"
    variant: str = ""  # what tells two entries of one model apart: "15 s window", "beam search 4"
    runs_on: Literal["GPU", "CPU"] = "GPU"
    approx_gb: float | None = None
    note: str = ""  # one short line to help choose
    spec: dict = field(default_factory=dict)  # worker arguments (asr.create / translate.create)
    repos: tuple[str, ...] = ()  # Hugging Face repos used as they are
    conversion: Conversion | None = None
    in_panel: bool = True  # offered in the control panel (some entries are benchmark variants only)
    lean: bool = False  # fetched by `download-models --all`: still worth comparing on the event Mac
    default: bool = False

    @property
    def title(self) -> str:
        return f"{self.name}, {self.variant}" if self.variant else self.name


def _whisper(key: str, name: str, repo: str, window: str, approx_gb: float, note: str, **kw) -> ModelInfo:
    ctx = {"15 s": "750", "30 s": "full"}[window]
    spec = {"model": repo, "audio_ctx": ctx}
    return ModelInfo(key, "speech", name, f"{window} window", "GPU", approx_gb, note, spec, (repo,), **kw)


_HYMT_18 = Conversion("tencent/HY-MT1.5-1.8B", 8, "HY-MT1.5-1.8B-mlx-8bit")
_HYMT_7 = Conversion("tencent/HY-MT1.5-7B", 4, "HY-MT1.5-7B-mlx-4bit")
_TG = "mlx-community/translategemma-{}-it-4bit"

# fmt: off
CATALOG: tuple[ModelInfo, ...] = (
    _whisper("whisper-turbo-15s", "Whisper large-v3-turbo", WHISPER_TURBO, "15 s", 1.6,
             "Default: best speed and accuracy measured.", lean=True, default=True),
    _whisper("whisper-turbo-30s", "Whisper large-v3-turbo", WHISPER_TURBO, "30 s", 1.6,
             "About 2x slower, no accuracy gain measured.", lean=True),
    _whisper("whisper-large-v3-15s", "Whisper large-v3", WHISPER_LARGE, "15 s", 3.1,
             "Slower than turbo and not more accurate.", lean=True),
    _whisper("whisper-large-v3-30s", "Whisper large-v3", WHISPER_LARGE, "30 s", 3.1,
             "Slowest Whisper; the benchmark's reference.", lean=True),
    _whisper("whisper-medium", "Whisper medium", "mlx-community/whisper-medium-mlx", "15 s", 1.5,
             "No faster than turbo, weaker Turkish."),
    _whisper("whisper-small", "Whisper small", "mlx-community/whisper-small-mlx", "15 s", 0.5,
             "About 3x faster, many more Turkish errors."),

    ModelInfo("opus-mt", "translation", "Opus-MT", "", "CPU", 0.6, "Default: fast and faithful.",
              {"model": "opus-mt"}, OPUS_REPOS, lean=True, default=True),
    ModelInfo("opus-mt-gpu", "translation", "Opus-MT", "on the GPU", "GPU", 0.6,
              "Same model and output; no faster on the Pro.", {"model": "opus-mt-gpu"}, OPUS_REPOS, lean=True),
    ModelInfo("opus-mt-beam4", "translation", "Opus-MT", "beam search 4", "CPU", 0.6,
              "Slower search; benchmark only.", {"model": "opus-mt", "beam_size": 4}, OPUS_REPOS,
              in_panel=False, lean=True),
    ModelInfo("hymt-1.8b", "translation", "HY-MT1.5 1.8B", "8-bit", "GPU", 1.9,
              "Fluent, sometimes adds words. License excludes EU, UK, South Korea.",
              {"model": str(MODEL_DIR / _HYMT_18.folder)}, conversion=_HYMT_18, lean=True),
    ModelInfo("hymt-7b", "translation", "HY-MT1.5 7B", "4-bit", "GPU", 4.3,
              "License excludes EU, UK, South Korea.",
              {"model": str(MODEL_DIR / _HYMT_7.folder)}, conversion=_HYMT_7, lean=True),
    ModelInfo("translategemma-4b", "translation", "TranslateGemma 4B", "4-bit", "GPU", 2.6,
              "Invents meaning in Turkish to English.", {"model": _TG.format("4b")}, (_TG.format("4b"),)),
    ModelInfo("translategemma-12b", "translation", "TranslateGemma 12B", "4-bit", "GPU", 7.0,
              "Slower and less accurate than Opus-MT on the Pro.", {"model": _TG.format("12b")},
              (_TG.format("12b"),), lean=True),
    ModelInfo("translategemma-27b", "translation", "TranslateGemma 27B", "4-bit", "GPU", 16.0,
              "Too big next to Whisper on 24 GB.", {"model": _TG.format("27b")}, (_TG.format("27b"),)),
)
# fmt: on

BY_KEY: dict[str, ModelInfo] = {m.key: m for m in CATALOG}
DEFAULT_SPEECH = next(m.key for m in CATALOG if m.job == "speech" and m.default)
DEFAULT_TRANSLATION = next(m.key for m in CATALOG if m.job == "translation" and m.default)
REFERENCE_SPEECH = "whisper-large-v3-30s"  # the benchmark's agreement reference


def get(key: str) -> ModelInfo:
    try:
        return BY_KEY[key]
    except KeyError:
        raise KeyError(f"unknown model {key!r}; known: {', '.join(BY_KEY)}") from None


def of_job(job: Job) -> list[ModelInfo]:
    return [m for m in CATALOG if m.job == job]


def find_by_spec(job: Job, spec: dict) -> ModelInfo | None:
    """The catalog entry for an old-style setting: a repo name, maybe with an encoder window."""
    model = str(spec.get("model") or "")
    for m in of_job(job):
        same = m.spec.get("model") == model or (m.conversion and model.rstrip("/").endswith("/" + m.conversion.folder))
        if same and all(spec.get(k, v) == v for k, v in m.spec.items() if k != "model"):
            return m
    return None


def missing(keys: list[str]) -> list[str]:
    """What is not on this Mac yet for these models (checked without network access)."""
    from huggingface_hub import snapshot_download

    from .translate import OpusMtTranslator

    out: list[str] = []
    for m in (get(k) for k in dict.fromkeys(keys)):
        if m.conversion and not (MODEL_DIR / m.conversion.folder / "config.json").exists():
            out.append(f"{m.title} (converted to MLX by download-models)")
        for repo in m.repos:
            opus = repo in OPUS_REPOS
            try:
                snapshot_download(repo, local_files_only=True, allow_patterns=OpusMtTranslator.FILES if opus else None)
            except Exception:
                out.append(repo)
                continue
            if opus and not (MODEL_DIR / repo.split("/")[-1] / "model.bin").exists():
                out.append(f"{repo} (CTranslate2 conversion)")
    return list(dict.fromkeys(out))


def panel_catalog() -> dict:
    """The choices for the control panel, each marked as downloaded or not."""

    def row(m: ModelInfo) -> dict:
        return {
            "key": m.key,
            "name": m.name,
            "variant": m.variant,
            "title": m.title,
            "runs_on": m.runs_on,
            "approx_gb": m.approx_gb,
            "note": m.note,
            "default": m.default,
            "available": not missing([m.key]),
        }

    return {job: [row(m) for m in of_job(job) if m.in_panel] for job in ("speech", "translation")}
