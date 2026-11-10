from pathlib import Path

"""Models the benchmark compares. Names are used on the command line."""

ASR = {
    # name: (worker spec, note)
    "turbo-750": ({"model": "mlx-community/whisper-large-v3-turbo", "audio_ctx": "750"}, "large-v3-turbo, 15 s encoder window"),
    "turbo-full": ({"model": "mlx-community/whisper-large-v3-turbo", "audio_ctx": "full"}, "large-v3-turbo, 30 s encoder window"),
    "large-v3-750": ({"model": "mlx-community/whisper-large-v3-mlx", "audio_ctx": "750"}, "large-v3, 15 s encoder window"),
    "large-v3-full": ({"model": "mlx-community/whisper-large-v3-mlx", "audio_ctx": "full"}, "large-v3, 30 s encoder window (slowest, most accurate Whisper)"),
    "medium-750": ({"model": "mlx-community/whisper-medium-mlx", "audio_ctx": "750"}, "medium (769M, multilingual), 15 s encoder window"),
    "small-750": ({"model": "mlx-community/whisper-small-mlx", "audio_ctx": "750"}, "small (244M, multilingual), 15 s encoder window"),
}

MT = {
    "tg4b": ({"model": "mlx-community/translategemma-4b-it-4bit"}, "TranslateGemma 4B 4-bit"),
    "tg12b": ({"model": "mlx-community/translategemma-12b-it-4bit"}, "TranslateGemma 12B 4-bit"),
    "opus-mt": ({"model": "opus-mt"}, "Opus-MT tc-big via CTranslate2 int8 on the CPU"),
    "opus-mt-gpu": ({"model": "opus-mt-gpu"}, "Opus-MT tc-big in PyTorch on the Apple GPU (Metal)"),
    "opus-mt-beam4": ({"model": "opus-mt", "beam_size": 4}, "Opus-MT tc-big on the CPU, beam search 4 (slower, maybe better)"),
    "hymt1.8b": ({"model": str(Path.home() / ".cache/live-translate/HY-MT1.5-1.8B-mlx-8bit")}, "Tencent HY-MT1.5 1.8B, MLX 8-bit"),
    "hymt7b": ({"model": str(Path.home() / ".cache/live-translate/HY-MT1.5-7B-mlx-4bit")}, "Tencent HY-MT1.5 7B, MLX 4-bit (faster)"),
    "tg27b": ({"model": "mlx-community/translategemma-27b-it-4bit"}, "TranslateGemma 27B 4-bit (about 16 GB)"),
}

REFERENCE_ASR = "mlx-community/whisper-large-v3-mlx"

OPUS_REPOS = ["Helsinki-NLP/opus-mt-tc-big-en-tr", "Helsinki-NLP/opus-mt-tc-big-tr-en"]


# What `download-models --all` fetches: candidates still worth comparing on the event Mac.
# Ruled out on the Air on accuracy (which does not depend on the Mac): small, medium, tg4b;
# tg27b is too big for live use next to Whisper on 24 GB. Add any of them with --include.
LEAN_ASR = ["turbo-750", "turbo-full", "large-v3-750", "large-v3-full"]
LEAN_MT = ["opus-mt", "opus-mt-gpu", "opus-mt-beam4", "hymt1.8b", "hymt7b", "tg12b"]


def model_repos(asr_names: list[str], mt_names: list[str]) -> list[str]:
    """Hugging Face repos for these candidates (local conversions such as HY-MT are prepared separately)."""
    repos = [ASR[n][0]["model"] for n in asr_names if not ASR[n][0]["model"].startswith("/")]
    repos += [MT[n][0]["model"] for n in mt_names
              if not MT[n][0]["model"].startswith(("/", "opus-mt"))]
    if any(n.startswith("opus-mt") for n in mt_names):
        repos += OPUS_REPOS
    return list(dict.fromkeys(repos + [REFERENCE_ASR]))


def all_model_repos() -> list[str]:
    return model_repos(LEAN_ASR, LEAN_MT)
