"""Speech recognition backends. These run inside the ASR worker process."""

from __future__ import annotations

import time

import numpy as np

# Segment-level filters (same meaning as Whisper's own thresholds).
NO_SPEECH_PROB = 0.6
LOGPROB_THRESHOLD = -1.0
COMPRESSION_RATIO = 2.4


class _CachedFeatures:
    """Model proxy whose forward_with_cross_qk reuses already-encoded audio features.

    mlx_whisper's find_alignment (word timestamps) calls forward_with_cross_qk(mel, tokens),
    which would run the encoder a second time on the same audio.
    """

    def __init__(self, model, feats):
        self._m = model
        self._feats = feats

    def __getattr__(self, name):
        return getattr(self._m, name)

    def encoder(self, mel):
        return self._feats

    def forward_with_cross_qk(self, mel, tokens):
        logits, _, cross_qk = self._m.decoder(tokens, self._feats)
        return logits, cross_qk


class MlxWhisperBackend:
    """mlx-whisper on the Apple GPU, driven directly so each buffer is encoded exactly once.

    Buffers are always shorter than 30 s here, so we skip transcribe()'s windowing loop:
    encode once, detect the language on those features if needed, decode, then align
    words with a decoder-only pass over the same features.

    audio_ctx="dynamic" runs the encoder only over the buffer plus ~1 s of margin instead
    of the full 30 s window (whisper.cpp's audio_ctx trick).
    """

    def __init__(self, model: str, audio_ctx: str = "full"):
        import mlx.core as mx
        from mlx_whisper.load_models import load_model
        from mlx_whisper.tokenizer import get_tokenizer

        self.mx = mx
        self.model_path = model
        self.audio_ctx_mode = audio_ctx
        t0 = time.perf_counter()
        self.model = load_model(model, dtype=mx.float16)
        self.tokenizers = {
            lang: get_tokenizer(
                self.model.is_multilingual, num_languages=self.model.num_languages, language=lang, task="transcribe"
            )
            for lang in ("en", "tr")
        }
        load_s = time.perf_counter() - t0
        # Warm up both paths (kernel compilation) so the first real request is not slow.
        for lang in ("en", None):
            self.handle({"audio": np.zeros(32000, dtype=np.float32), "language": lang})
        self.info = {"backend": "mlx-whisper", "model": model, "load_s": round(load_s, 1), "audio_ctx": audio_ctx}

    def _ctx_for(self, n_samples: int) -> int:
        n_ctx = self.model.dims.n_audio_ctx
        if self.audio_ctx_mode.isdigit():
            # Fixed reduced window (e.g. "750" = 15 s), falling back to full for longer buffers.
            fixed = int(self.audio_ctx_mode)
            return fixed if n_samples // 320 + 25 <= fixed else n_ctx
        if self.audio_ctx_mode != "dynamic":
            return n_ctx
        # One encoder position covers 320 samples (20 ms). Add 1 s of margin, round up to 64.
        need = n_samples // 320 + 50
        return min(n_ctx, ((need + 63) // 64) * 64)

    def encode(self, audio: np.ndarray):
        from mlx import nn
        from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim

        mx = self.mx
        mel = log_mel_spectrogram(audio, n_mels=self.model.dims.n_mels, padding=N_SAMPLES)
        mel = pad_or_trim(mel, N_FRAMES, axis=-2).astype(mx.float16)
        ctx = self._ctx_for(len(audio))
        enc = self.model.encoder
        if ctx >= self.model.dims.n_audio_ctx:
            feats = enc(mel[None])
        else:
            x = mel[None, : ctx * 2, :]
            x = nn.gelu(enc.conv1(x))
            x = nn.gelu(enc.conv2(x))
            x = x + enc._positional_embedding[: x.shape[1]]
            for block in enc.blocks:
                x, _, _ = block(x)
            feats = enc.ln_post(x)
        mx.eval(feats)
        return mel, feats

    def detect_language(self, feats, allowed: list[str]) -> tuple[str, float]:
        mx = self.mx
        tok = self.tokenizers["en"]
        logits = self.model.logits(mx.array([[tok.sot]]), feats)[0, 0].astype(mx.float32)
        ids = [tok.to_language_token(lang) for lang in allowed]
        sub = mx.softmax(logits[mx.array(ids)], axis=-1).tolist()
        best = max(range(len(allowed)), key=lambda i: sub[i])
        return allowed[best], float(sub[best])

    def transcribe(self, audio: np.ndarray, language: str | None, prompt: str | None) -> dict:
        from mlx_whisper.decoding import DecodingOptions, decode
        from mlx_whisper.timing import find_alignment, merge_punctuations

        audio = audio[-(29 * 16000) :]  # the pipeline keeps buffers well under 30 s; guard anyway
        mel, feats = self.encode(audio)
        lang_prob = None
        if language is None:
            language, lang_prob = self.detect_language(feats, ["en", "tr"])
        opts = DecodingOptions(
            task="transcribe",
            language=language,
            temperature=0.0,
            fp16=True,
            without_timestamps=True,
            prompt=prompt or None,
        )
        cached = _CachedFeatures(self.model, feats)
        res = decode(cached, feats[0], opts)
        words = []
        bad = res.compression_ratio > COMPRESSION_RATIO or (
            res.no_speech_prob > NO_SPEECH_PROB and res.avg_logprob < LOGPROB_THRESHOLD
        )
        tok = self.tokenizers.get(language) or self.tokenizers["en"]
        text_tokens = [t for t in res.tokens if t < tok.eot]
        if text_tokens and not bad:
            num_frames = min(len(audio) // 160, feats.shape[1] * 2)
            alignment = find_alignment(cached, tok, text_tokens, mel[: feats.shape[1] * 2], num_frames)
            merge_punctuations(alignment, "\"'\u201c\u00bf([{-", "\"'.,\uff0c!\uff01?\uff1f:\uff1a\u201d)]}\u3001")
            for w in alignment:
                if w.word.strip():
                    words.append([float(w.start), float(w.end), w.word, float(w.probability)])
        return {
            "words": words,
            "language": language,
            "language_prob": lang_prob,
            "text": res.text,
            "no_speech_prob": float(res.no_speech_prob),
            "avg_logprob": float(res.avg_logprob),
        }

    def handle(self, req: dict) -> dict:
        if req.get("op") == "ping":
            return {"ok": True}
        t0 = time.perf_counter()
        out = self.transcribe(np.asarray(req["audio"], dtype=np.float32), req.get("language"), req.get("prompt"))
        out["ms"] = (time.perf_counter() - t0) * 1000
        return out


def create(model: str = "mlx-community/whisper-large-v3-turbo", audio_ctx: str = "750"):
    return MlxWhisperBackend(model, audio_ctx=audio_ctx)
