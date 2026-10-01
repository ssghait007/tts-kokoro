"""Kokoro-82M on Apple Silicon (MLX) with crackle-avoidance built in.

Fixes applied vs. naive usage:
  * text is split on sentence boundaries into short chunks (Kokoro degrades on long inputs)
  * chunks are joined with a short crossfade (no clicks at boundaries)
  * audio is written to a WAV file, never live-streamed (no buffer underruns)
  * speed defaults to 1.0, output stays at the native 24 kHz
"""
import argparse
import re
import time
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

MODEL_ID = "mlx-community/Kokoro-82M-bf16"
SR = 24000


def chunk_text(text: str, max_chars: int = 250) -> list[str]:
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def crossfade_join(parts: list[np.ndarray], sr: int, fade_ms: int = 30) -> np.ndarray:
    n = int(sr * fade_ms / 1000)
    out = parts[0]
    for p in parts[1:]:
        k = min(n, len(out), len(p))
        ramp = np.linspace(0.0, 1.0, k, dtype=np.float32)
        out = np.concatenate([out[:-k], out[-k:] * (1 - ramp) + p[:k] * ramp, p[k:]])
    return out


LANG_BY_PREFIX = {"a": "a", "b": "b", "e": "e", "f": "f", "h": "h", "i": "i", "j": "j", "p": "p", "z": "z"}
DEFAULT_VOICE = "af_bella"


def list_voices() -> list[str]:
    from huggingface_hub import snapshot_download
    root = Path(snapshot_download(MODEL_ID)) / "voices"
    return sorted(f.stem for f in root.glob("*.safetensors"))


def main():
    import subprocess
    import sys

    ap = argparse.ArgumentParser(description="Kokoro-82M TTS (MLX). Text from args, --text-file, or stdin.")
    ap.add_argument("text", nargs="*", help="text to speak")
    ap.add_argument("--text-file", default=None)
    ap.add_argument("--voice", "-v", default=DEFAULT_VOICE, help=f"default {DEFAULT_VOICE}; see --list-voices")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", default=None, help="save WAV here (default: temp file when --play)")
    ap.add_argument("--play", "-p", action="store_true", help="play with afplay after rendering")
    ap.add_argument("--list-voices", action="store_true")
    a = ap.parse_args()

    if a.list_voices:
        print("\n".join(list_voices()))
        return
    if a.text:
        text = " ".join(a.text)
    elif a.text_file:
        text = Path(a.text_file).read_text()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("give text as arguments, --text-file, or via stdin")
    if not text.strip():
        ap.error("empty text")

    lang = LANG_BY_PREFIX.get(a.voice[:1], "a")  # voice prefix picks the phonemizer language
    tmp = a.play and not a.out  # play-only: use a unique temp file and delete it afterwards
    if tmp:
        import tempfile
        out = Path(tempfile.mkstemp(prefix="ksay-", suffix=".wav")[1])
    else:
        out = Path(a.out or "out/kokoro.wav")
    model = load_model(MODEL_ID)
    parts, t0 = [], time.time()
    for c in chunk_text(text):
        for r in model.generate(text=c, voice=a.voice, speed=a.speed, lang_code=lang):
            parts.append(np.array(r.audio, dtype=np.float32).squeeze())
    audio = crossfade_join(parts, SR)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, audio, SR)
    dur, el = len(audio) / SR, time.time() - t0
    print(f"{a.voice}: {dur:.1f}s audio in {el:.1f}s (RTF {el/dur:.2f}x) -> {'(played)' if tmp else out}", file=sys.stderr)
    if a.play:
        subprocess.run(["afplay", str(out)])
    if tmp:
        out.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
