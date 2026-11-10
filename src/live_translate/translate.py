"""Translation backends. These run inside the MT worker process (except the guard helpers)."""

from __future__ import annotations

import re
import time
import unicodedata

from .streaming import SENTENCE_END, split_sentences

LANG_NAMES = {"en": "English", "tr": "Turkish"}
TURKISH_ONLY = set("ğışİĞŞ")


def check_translation(src: str, out: str, tgt: str) -> str | None:
    """Return a reason string if the output looks wrong, otherwise None."""
    s, o = src.strip(), out.strip()
    if not o:
        return "empty"
    ratio = len(o) / max(1, len(s))
    if len(s) >= 12 and not (0.3 <= ratio <= 3.5):
        return f"length ratio {ratio:.2f}"
    if any(ord(ch) > 0x2FF and not (0x2000 <= ord(ch) <= 0x206F) and unicodedata.category(ch).startswith("L") for ch in o):
        return "non-Latin script in output"
    if tgt == "en" and sum(ch in TURKISH_ONLY for ch in o) >= 2:
        return "output looks Turkish"
    return None


def clean_output(text: str, src: str = "") -> str:
    text = text.replace("<end_of_turn>", "").strip()
    text = re.sub(r"^(translation|çeviri)\s*:\s*", "", text, flags=re.I)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    text = text.split("\n\n")[0].strip()
    # Fragments: do not let the model close a sentence the speaker has not finished.
    if src and not SENTENCE_END.search(src.strip()):
        text = re.sub(r"(\s*(\.\.\.|\u2026|\.))$", "", text)
    return text


class MlxLmTranslator:
    """TranslateGemma or Tencent HY-MT via mlx-lm, each with its own prompt template."""

    def __init__(self, model: str):
        from mlx_lm import load
        from mlx_lm.sample_utils import make_sampler

        name = model.lower()
        self.is_translategemma = "translategemma" in name
        if not self.is_translategemma and "hy-mt" not in name:
            raise ValueError(f"unsupported translation model {model!r} (TranslateGemma or HY-MT expected)")
        t0 = time.perf_counter()
        self.model, self.tokenizer = load(model)
        self.sampler = make_sampler(temp=0.0)
        self._prefix: dict[tuple[str, str], tuple[list[int], list] | None] = {}
        load_s = time.perf_counter() - t0
        self.translate("Hello, welcome to Python Pizza.", "en", "tr")  # warm-up
        self.translate("Merhaba, Python Pizza'ya hoş geldiniz.", "tr", "en")
        self.info = {"backend": "mlx-lm", "model": model, "load_s": round(load_s, 1)}

    def _render(self, text: str, src: str, tgt: str) -> str:
        if self.is_translategemma:
            msg = {"role": "user", "content": [{"type": "text", "source_lang_code": src, "target_lang_code": tgt, "text": text}]}
        else:  # HY-MT's template for non-Chinese pairs (from its model card)
            msg = {"role": "user", "content": f"Translate the following segment into {LANG_NAMES[tgt]}, without additional explanation.\n\n{text}"}
        return self.tokenizer.apply_chat_template([msg], add_generation_prompt=True, tokenize=False)

    def _encode(self, prompt: str) -> list[int]:
        bos = self.tokenizer.bos_token
        return self.tokenizer.encode(prompt, add_special_tokens=bos is None or not prompt.startswith(bos))

    def _prefix_for(self, src: str, tgt: str):
        """KV cache of the fixed instruction text before the source text, per direction."""
        key = (src, tgt)
        if key in self._prefix:
            return self._prefix[key]
        import mlx.core as mx
        from mlx_lm.models.cache import can_trim_prompt_cache, make_prompt_cache

        marker = "\ue000"
        rendered = self._render(marker, src, tgt)
        entry = None
        if rendered.count(marker) == 1:
            toks = self._encode(rendered.split(marker)[0])
            cache = make_prompt_cache(self.model)
            if can_trim_prompt_cache(cache) and len(toks) > 8:
                toks = toks[:-1]  # leave one token so generation always has new input
                self.model(mx.array(toks)[None], cache=cache)
                mx.eval([c.state for c in cache])
                entry = (toks, cache)
        self._prefix[key] = entry
        return entry

    def translate(self, text: str, src: str, tgt: str) -> str:
        from mlx_lm import stream_generate
        from mlx_lm.models.cache import trim_prompt_cache

        tokens = self._encode(self._render(text, src, tgt))
        kwargs = {}
        cache = None
        entry = self._prefix_for(src, tgt)
        if entry is not None and tokens[: len(entry[0])] == entry[0]:
            prefix, cache = entry
            kwargs["prompt_cache"] = cache
            tokens = tokens[len(prefix) :]
        out = []
        try:
            for resp in stream_generate(self.model, self.tokenizer, tokens, max_tokens=min(256, 16 + 4 * len(text.split())),
                                        sampler=self.sampler, **kwargs):
                out.append(resp.text)
                if any(stop in resp.text for stop in ("<end_of_turn>", "<|eos|>", "<|endoftext|>")) or "\n\n" in "".join(out[-3:]):
                    break
        finally:
            if cache is not None:
                extra = cache[0].offset - len(entry[0])
                if extra > 0 and trim_prompt_cache(cache, extra) != extra:
                    self._prefix.pop((src, tgt), None)  # could not restore; rebuild next time
        return clean_output("".join(out), text)

    def handle(self, req: dict) -> dict:
        if req.get("op") == "ping":
            return {"ok": True}
        t0 = time.perf_counter()
        text = self.translate(req["text"], req["src"], req["tgt"])
        return {"text": text, "ms": (time.perf_counter() - t0) * 1000}


# Product and tool names Opus-MT tends to translate ("Parquet" -> "Parke", "Docker" -> "a docker").
# They are swapped for placeholders before translation and restored afterwards.
PROTECTED_TERMS = [
    "Parquet", "Docker", "Kubernetes", "GitHub", "GitLab", "PyPI", "Jupyter", "NumPy", "pandas", "Polars",
    "Redis", "RabbitMQ", "Celery", "Django", "FastAPI", "Flask", "Pydantic", "Rust", "DuckDB", "MicroPython",
    "Ultralytics", "PyCon", "Python Pizza", "Linux", "macOS", "Raspberry Pi", "Arduino", "OpenAI", "Claude",
    "Kahoot", "Slido", "Discord", "Telegram", "YouTube", "LinkedIn",
]
_TERM_RE = re.compile(r"(?<![\w-])(" + "|".join(re.escape(t) for t in sorted(PROTECTED_TERMS, key=len, reverse=True)) + r")(?![\w-])", re.I)


def _terms_re(extra: tuple[str, ...]) -> re.Pattern:
    if not extra:
        return _TERM_RE
    terms = sorted(set(PROTECTED_TERMS) | set(extra), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(t) for t in terms) + r")(?![\w-])", re.I)


def protect_terms(text: str, extra: list[str] | tuple[str, ...] = ()) -> tuple[str, list[str]]:
    """Swap known names for placeholders. extra: more terms, e.g. speaker names from the schedule."""
    found: list[str] = []

    def sub(m):
        found.append(m.group(0))
        return f"XYZ{len(found)}"

    return _terms_re(tuple(extra)).sub(sub, text), found


def restore_terms(text: str, found: list[str]) -> str | None:
    """Put the original terms back; None if the model dropped or mangled a placeholder."""
    for i, term in enumerate(found, 1):
        if f"XYZ{i}" not in text:
            return None
        text = text.replace(f"XYZ{i}", term, 1)
    return text


class OpusMtTranslator:
    """Helsinki-NLP Opus-MT tc-big via CTranslate2 int8 on the CPU (~0.15 s per clause)."""

    MODELS = {
        ("en", "tr"): "Helsinki-NLP/opus-mt-tc-big-en-tr",
        ("tr", "en"): "Helsinki-NLP/opus-mt-tc-big-tr-en",
    }
    # Only what conversion and the tokenizer need (the repos also hold PyTorch and TF copies).
    FILES = ["config.json", "generation_config.json", "*.spm", "vocab.json", "tokenizer_config.json",
             "special_tokens_map.json", "model.safetensors"]

    def __init__(self, model: str = "opus-mt", beam_size: int = 2, **_):
        """model "opus-mt": CTranslate2 int8 on the CPU (CTranslate2 has no Apple GPU support).
        model "opus-mt-gpu": the same models in PyTorch on the Apple GPU (Metal/MPS)."""
        import transformers
        from huggingface_hub import snapshot_download

        t0 = time.perf_counter()
        self.device = "mps" if model == "opus-mt-gpu" else "cpu"
        self.beam_size = beam_size
        self.pairs = {}
        for pair, repo in self.MODELS.items():
            local = snapshot_download(repo, allow_patterns=self.FILES)
            tok = transformers.AutoTokenizer.from_pretrained(local)
            if self.device == "mps":
                net = transformers.MarianMTModel.from_pretrained(local).to("mps").eval()
                net.generation_config.max_length = None  # we pass max_new_tokens
                self.pairs[pair] = (net, tok)
            else:
                self.pairs[pair] = (self._ct2(repo, local), tok)
        self.info = {"backend": "torch-mps" if self.device == "mps" else "ctranslate2", "model": "opus-mt-tc-big",
                     "device": self.device, "load_s": round(time.perf_counter() - t0, 1)}

    @staticmethod
    def _ct2(repo: str, local: str):
        import ctranslate2

        from .config import MODEL_DIR

        out_dir = MODEL_DIR / repo.split("/")[-1]
        if not (out_dir / "model.bin").exists():
            ctranslate2.converters.TransformersConverter(local).convert(str(out_dir), quantization="int8", force=True)
        return ctranslate2.Translator(str(out_dir), device="cpu", compute_type="int8", inter_threads=1,
                                      intra_threads=performance_cores())

    def _translate(self, text: str, src: str, tgt: str) -> str:
        net, tok = self.pairs[(src, tgt)]
        if self.device == "mps":
            import torch

            inputs = tok(text, return_tensors="pt").to("mps")
            with torch.inference_mode():
                out = net.generate(**inputs, num_beams=self.beam_size, max_new_tokens=256)
            return tok.decode(out[0], skip_special_tokens=True)
        tokens = tok.convert_ids_to_tokens(tok.encode(text))
        res = net.translate_batch([tokens], beam_size=self.beam_size)
        return tok.decode(tok.convert_tokens_to_ids(res[0].hypotheses[0]), skip_special_tokens=True)

    def handle(self, req: dict) -> dict:
        if req.get("op") == "ping":
            return {"ok": True}
        t0 = time.perf_counter()
        src, tgt, text = req["src"], req["tgt"], req["text"]
        # Opus-MT is a sentence-level model: given two sentences it often translates only one.
        outs = [self._one(piece, src, tgt, req.get("protect", ())) for piece in split_sentences(text)]
        return {"text": " ".join(o for o in outs if o), "ms": (time.perf_counter() - t0) * 1000}

    def _one(self, text: str, src: str, tgt: str, protect) -> str:
        protected, found = protect_terms(text, protect)
        out = None
        if found:
            out = restore_terms(self._translate(protected, src, tgt), found)
        if out is None:
            out = self._translate(text, src, tgt)
        return clean_output(out, text)


def performance_cores() -> int:
    """Number of performance CPU cores (4 on an M4 MacBook Air, 8-10 on an M4 Pro)."""
    import os
    import subprocess

    try:
        n = int(subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True).stdout)
        return max(1, n)
    except Exception:
        return max(1, (os.cpu_count() or 4) // 2)


def create(model: str = "opus-mt", **kwargs):
    if model.startswith("opus-mt"):
        return OpusMtTranslator(model, **kwargs)
    return MlxLmTranslator(model)
