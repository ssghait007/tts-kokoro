"""ksay client: sends text to the keep-warm server (auto-starting it), then plays the result."""
import argparse, json, os, re, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOCK = Path.home() / ".cache" / "ksay" / "ksay.sock"
LOG = Path.home() / ".cache" / "ksay" / "server.log"


def call(req: dict, timeout: float = 120) -> dict:
    s = socket.socket(socket.AF_UNIX); s.settimeout(timeout); s.connect(str(SOCK))
    s.sendall((json.dumps(req) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk: break
        data += chunk
    s.close()
    if not data:
        raise ConnectionError('empty reply')
    return json.loads(data)


# Yoda-ish effect, tuned against Yoda's lines in "Do. Or do not. There is no try." (Empire Strikes Back):
# Kokoro speed 0.6 gives his slow ~2 syllables/s; pitch +5.3 st (asetrate+atempo keep duration), thin chest
# (HPF 300), mid-forward EQ, 48 Hz tremolo = vocal-fry gravel, slight wobble + crush for rasp.
YODA_VOICE = "am_michael"
YODA_SPEED = 0.60
YODA_PAUSE = {",": 0.19, ".": 0.41}  # silence between phrases (+30 ms trim pads) -> 0.2-0.6 s gaps like the clip
YODA_FILTER = ("asetrate=24000*1.36,aresample=24000,atempo=1/1.36,highpass=f=300,lowpass=f=7500,"
               "equalizer=f=450:t=q:w=1:g=3,equalizer=f=800:t=q:w=1:g=3,equalizer=f=1500:t=q:w=1:g=3,"
               "equalizer=f=5000:t=q:w=1:g=-6,tremolo=f=48:d=0.35,vibrato=f=4:d=0.08,"
               "acrusher=bits=10:mix=0.12:mode=log,acompressor")


def split_phrases(text: str):
    """Split after , ; . ! ? when followed by a space (so 3.5, 1,000 survive). Returns [(phrase, kind)]."""
    out, held = [], ""
    for chunk in re.split(r"(?<=[,;.!?][\"')\]])\s+|(?<=[,;.!?])\s+", text.strip()):
        chunk = (held + " " + chunk).strip() if held else chunk.strip()
        held = ""
        if re.search(r"(?:^|\s)(?:Mr|Mrs|Ms|Dr|St|Prof|vs|e\.g|i\.e)\.$", chunk, re.I):
            held = chunk; continue  # abbreviation, not a phrase end
        if re.search(r"\w", chunk):  # skip punctuation-only bits
            end = chunk.rstrip("\"')]")[-1:]
            out.append((chunk, "." if end in ".!?" else ","))
    if held:
        out.append((held, "."))
    return out


def say_with_pauses(text: str, voice, speed, scale: float, dst: str):
    """Render each phrase separately, trim Kokoro's own silence, join with real silence into dst."""
    import numpy as np, soundfile as sf
    parts, sr = [], 24000
    for phrase, kind in split_phrases(text):
        r = call({"cmd": "say", "text": phrase, "voice": voice, "speed": speed, "out": None})
        if not r["ok"]:
            sys.exit(f"ksay: {r['error']}")
        audio, sr = sf.read(r["path"], dtype="float32")
        if r["temp"]:
            Path(r["path"]).unlink(missing_ok=True)
        if audio.size == 0:
            continue
        loud = np.where(np.abs(audio) > np.abs(audio).max() * 0.02)[0]
        if len(loud):
            pad = int(sr * 0.03); audio = audio[max(0, loud[0] - pad): loud[-1] + pad]
        parts += [audio, np.zeros(int(sr * YODA_PAUSE[kind] * scale), dtype="float32")]
    if not parts:
        sys.exit("ksay: nothing to say")
    audio = np.concatenate(parts[:-1])
    sf.write(dst, audio, sr)
    return len(audio) / sr


def yodify(src: str, dst: str):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-af", YODA_FILTER, dst], check=True)


def ensure_server() -> bool:
    """Return True if we had to start it (cold)."""
    try:
        call({"cmd": "status"}, 5); return False
    except OSError:
        pass
    SOCK.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = dict(os.environ, PYTHONWARNINGS="ignore", HF_HUB_DISABLE_PROGRESS_BARS="1", TOKENIZERS_PARALLELISM="false")
    subprocess.Popen([str(ROOT / ".venv/bin/python"), str(ROOT / "src/server.py")], stdout=open(LOG, "a"), stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    for _ in range(300):  # up to 30 s
        time.sleep(0.1)
        try:
            call({"cmd": "status"}, 5); return True
        except OSError:
            pass
    sys.exit(f"ksay: server did not start, see {LOG}")


def main():
    ap = argparse.ArgumentParser(prog="ksay", description="Speak text with Kokoro via a keep-warm server (default voice af_bella).")
    ap.add_argument("text", nargs="*")
    ap.add_argument("-v", "--voice", default=None)
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("-o", "--out", default=None, help="also keep the WAV here")
    ap.add_argument("--yoda", action="store_true", help="Yoda-ish effect (pitch/slow/rasp via ffmpeg); default voice am_michael")
    ap.add_argument("--pause", type=float, default=1.0, help="--yoda pause length multiplier (e.g. 1.5 = longer)")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true", help="stop the server now (frees memory)")
    a = ap.parse_args()

    if a.stop:
        try: call({"cmd": "stop"}, 5); print("ksay server stopping")
        except OSError: print("ksay server not running")
        return
    if a.status:
        try: r = call({"cmd": "status"}, 5); print(f"running pid {r['pid']}, up {r['up_s']:.0f}s, idle {r['idle_s']:.0f}s, exits after {r['idle_limit_s']/60:.0f} min idle")
        except OSError: print("ksay server not running (starts automatically on next use)")
        return
    if a.list_voices:
        ensure_server(); print("\n".join(call({"cmd": "voices"})["voices"])); return

    text = " ".join(a.text) if a.text else (sys.stdin.read() if not sys.stdin.isatty() else "")
    if not text.strip():
        ap.error("give text as arguments or via stdin")
    t0 = time.time()
    cold = ensure_server()
    if a.speed is not None and a.speed <= 0:
        ap.error("--speed must be > 0")
    if a.yoda:
        if not shutil.which("ffmpeg"):
            sys.exit("ksay: --yoda needs ffmpeg (brew install ffmpeg)")
        a.voice = a.voice or YODA_VOICE
        if a.speed is None: a.speed = YODA_SPEED
        fd, raw = tempfile.mkstemp(suffix=".wav"); os.close(fd)
        play = str(Path(a.out).resolve()) if a.out else raw[:-4] + "-yoda.wav"
        try:
            dur = say_with_pauses(text, a.voice, a.speed, a.pause, raw)
            yodify(raw, play)
            print(f"{'cold start' if cold else 'warm'}: sound after {time.time()-t0:.2f}s ({dur:.1f}s audio)", file=sys.stderr)
            subprocess.run(["afplay", play])
        finally:
            Path(raw).unlink(missing_ok=True)
            if not a.out:
                Path(play).unlink(missing_ok=True)
        return
    if a.speed is None: a.speed = 1.0
    r = call({"cmd": "say", "text": text, "voice": a.voice, "speed": a.speed, "out": a.out and str(Path(a.out).resolve())})
    if not r["ok"]:
        sys.exit(f"ksay: {r['error']}")
    print(f"{'cold start' if cold else 'warm'}: sound after {time.time()-t0:.2f}s (render {r['gen_s']:.2f}s for {r['audio_s']:.1f}s audio)", file=sys.stderr)
    subprocess.run(["afplay", r["path"]])
    if r["temp"]:
        Path(r["path"]).unlink(missing_ok=True)

if __name__ == "__main__":
    main()
