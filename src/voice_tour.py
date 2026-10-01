"""Render every Kokoro voice of a language set (en, hi) saying its own name, then a sentence; play them in order."""
import argparse
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

from synth import MODEL_ID, SR, crossfade_join

SETS = {
    "en": dict(
        sentence="Sunset was calming today. It was like the last brush stroke from the sun on the empty canvas of the sky.",
        intro="Voice, {prefix}, {name}.",
        voices=(
            "af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky "
            "am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa "
            "bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis"
        ).split(),
    ),
    "hi": dict(
        sentence="आज का सूर्यास्त बहुत शांत था। जैसे सूरज ने आसमान के खाली कैनवास पर आख़िरी बार ब्रश चलाया हो।",
        intro="आवाज़, {prefix}, {name}।",
        voices="hf_alpha hf_beta hm_omega hm_psi".split(),
    ),
}


def say(model, text, voice):
    lang = voice[0]  # 'a' American, 'b' British
    parts = [np.array(r.audio, dtype=np.float32).squeeze()
             for r in model.generate(text=text, voice=voice, speed=1.0, lang_code=lang)]
    return crossfade_join(parts, SR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="out/tour")
    ap.add_argument("--set", choices=SETS, default="en")
    ap.add_argument("--no-play", action="store_true")
    a = ap.parse_args()
    cfg = SETS[a.set]
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    model = load_model(MODEL_ID)
    files = []
    for v in cfg["voices"]:
        prefix, name = v.split("_")
        intro = cfg["intro"].format(prefix=" ".join(prefix.upper()), name=name)
        gap = np.zeros(int(SR * 0.5), dtype=np.float32)
        audio = np.concatenate([say(model, intro, v), gap, say(model, cfg["sentence"], v)])
        f = out / f"{v}.wav"; sf.write(f, audio, SR); files.append(f)
        print("rendered", v, flush=True)
    if not a.no_play:
        for f in files:
            print("playing", f.stem, flush=True)
            subprocess.run(["afplay", str(f)])


if __name__ == "__main__":
    main()
