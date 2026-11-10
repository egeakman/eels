"""Model catalog for the control panel, and checks for what is downloaded."""

from __future__ import annotations

from pathlib import Path

from .config import MODEL_DIR

LOCAL = str(MODEL_DIR)  # models converted on this Mac (HY-MT, by download-models --all)

# Speech recognition: (model repo, encoder window) -> label
ASR_OPTIONS = [
    ("mlx-community/whisper-large-v3-turbo", "750", "Whisper large-v3-turbo, 15 s window (default)"),
    ("mlx-community/whisper-large-v3-turbo", "full", "Whisper large-v3-turbo, 30 s window (about 2x slower)"),
    ("mlx-community/whisper-medium-mlx", "750", "Whisper medium (no faster than turbo, weaker Turkish)"),
    ("mlx-community/whisper-small-mlx", "750", "Whisper small (about 3x faster, many more Turkish errors)"),
    ("mlx-community/whisper-large-v3-mlx", "750", "Whisper large-v3, 15 s window (too slow on the Air; try on the Pro)"),
    ("mlx-community/whisper-large-v3-mlx", "full", "Whisper large-v3, 30 s window (slowest, most accurate Whisper)"),
]

# Translation: model name in settings -> label
MT_OPTIONS = [
    ("opus-mt", "Opus-MT on the CPU (default, ~0.1 s per sentence)"),
    ("opus-mt-gpu", "Opus-MT on the GPU (Metal, same model; compare on the Pro)"),
    (f"{LOCAL}/HY-MT1.5-1.8B-mlx-8bit", "Tencent HY-MT1.5 1.8B on the GPU (~0.2-0.8 s; license excludes EU/UK)"),
    (f"{LOCAL}/HY-MT1.5-7B-mlx-4bit", "Tencent HY-MT1.5 7B on the GPU, 4-bit (license excludes EU/UK)"),
    ("mlx-community/translategemma-4b-it-4bit", "TranslateGemma 4B on the GPU (~0.6-1 s per clause)"),
    ("mlx-community/translategemma-12b-it-4bit", "TranslateGemma 12B on the GPU (~2-3 s on the Air; check on the Pro)"),
    ("mlx-community/translategemma-27b-it-4bit", "TranslateGemma 27B on the GPU (about 16 GB; Pro only)"),
]

OPUS_REPOS = ["Helsinki-NLP/opus-mt-tc-big-en-tr", "Helsinki-NLP/opus-mt-tc-big-tr-en"]


def expand_models(names: list[str]) -> list[str]:
    """Model names in settings to Hugging Face repos ("opus-mt" is a pair of repos)."""
    repos = []
    for n in names:
        repos += OPUS_REPOS if n.startswith("opus-mt") else [n]
    return repos


def models_present(names: list[str]) -> list[str]:
    """Return the models that are not available locally (no network access)."""
    from huggingface_hub import snapshot_download

    from .translate import OpusMtTranslator

    missing = []
    for repo in expand_models(names):
        if repo.startswith(("/", "~")):  # a locally converted model
            if not Path(repo).expanduser().exists():
                missing.append(repo)
            continue
        patterns = OpusMtTranslator.FILES if repo.startswith("Helsinki-NLP/") else None
        try:
            snapshot_download(repo, local_files_only=True, allow_patterns=patterns)
        except Exception:
            missing.append(repo)
            continue
        if repo.startswith("Helsinki-NLP/") and not (MODEL_DIR / repo.split("/")[-1] / "model.bin").exists():
            missing.append(f"{repo} (CTranslate2 conversion)")
    return missing


def catalog() -> dict:
    """Options for the control panel, each marked as downloaded or not."""
    asr = []
    for model, ctx, label in ASR_OPTIONS:
        asr.append({"model": model, "audio_ctx": ctx, "label": label, "available": not models_present([model])})
    mt = []
    for model, label in MT_OPTIONS:
        mt.append({"model": model, "label": label, "available": not models_present([model])})
    return {"asr": asr, "mt": mt}
