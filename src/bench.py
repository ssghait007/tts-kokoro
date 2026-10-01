"""Timing benchmark: load, warm-up, then one timed generation per voice."""
import sys, time
t0 = time.time()
import numpy as np, soundfile as sf
from pathlib import Path
sys.path.insert(0, "src")
import synth
t1 = time.time()
model = synth.load_model(synth.MODEL_ID); t2 = time.time()
TEXT = "Sunset was calming today. It was like the last brush stroke from the sun on the empty canvas of the sky."
def gen(**kw):
    parts, sr = [], None
    for r in model.generate(text=TEXT, speed=1.0, lang_code="a", **kw):
        parts.append(np.array(r.audio, dtype=np.float32).squeeze()); sr = r.sample_rate
    return np.concatenate(parts), sr
def timed(**kw):
    s = time.time(); a, sr = gen(**kw); return a, sr, time.time() - s
Path("out/bench").mkdir(parents=True, exist_ok=True)
_, _, warm = timed(**{"voice":"af_heart"})
print(f"import {t1-t0:.2f}s | load {t2-t1:.2f}s | warm-up gen {warm:.2f}s")
for name, kw in {v: {"voice": v} for v in ["af_heart","af_bella","am_adam"]}.items():
    a, sr, el = timed(**kw); d = len(a) / sr
    sf.write(f"out/bench/{name}.wav", a, sr)
    print(f"{name:10s} audio {d:5.1f}s  gen {el:5.2f}s  RTF {el/d:.2f}  peak {abs(a).max():.2f}")
