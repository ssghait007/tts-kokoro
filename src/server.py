"""Keep-warm Kokoro server. Loads the model once, serves render requests over a Unix socket,
and exits (freeing all memory) after KSAY_IDLE_MIN idle minutes (default 10). ksay auto-starts it."""
import json, os, socketserver, sys, tempfile, time
from pathlib import Path

os.environ.setdefault("PYTHONWARNINGS", "ignore")
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

sys.path.insert(0, str(Path(__file__).parent))
from synth import DEFAULT_VOICE, LANG_BY_PREFIX, MODEL_ID, SR, chunk_text, crossfade_join, list_voices

SOCK_DIR = Path.home() / ".cache" / "ksay"
SOCK = SOCK_DIR / "ksay.sock"
IDLE_S = float(os.environ.get("KSAY_IDLE_MIN", "10")) * 60

model = load_model(MODEL_ID)


def render(text: str, voice: str, speed: float, out: str | None, write: bool = True) -> dict:
    lang = LANG_BY_PREFIX.get(voice[:1], "a")
    parts, t0 = [], time.time()
    for c in chunk_text(text):
        for r in model.generate(text=c, voice=voice, speed=speed, lang_code=lang):
            parts.append(np.array(r.audio, dtype=np.float32).squeeze())
    audio = crossfade_join(parts, SR)
    path = None
    if write:
        path = out or tempfile.mkstemp(prefix="ksay-", suffix=".wav")[1]
        sf.write(path, audio, SR)
    return dict(ok=True, path=path, temp=out is None, audio_s=len(audio) / SR, gen_s=time.time() - t0)


state = dict(last=time.time(), stop=False, started=time.time())


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        cmd = None
        try:
            req = json.loads(self.rfile.readline())
            cmd = req.get("cmd", "say")
            if cmd in ("say", "voices"):  # status/stop checks must not keep the server alive
                state["last"] = time.time()
            if cmd == "stop":
                state["stop"] = True; resp = dict(ok=True)
            elif cmd == "status":
                resp = dict(ok=True, up_s=time.time() - state["started"], idle_s=time.time() - state["last"], idle_limit_s=IDLE_S, pid=os.getpid())
            elif cmd == "voices":
                resp = dict(ok=True, voices=list_voices())
            else:
                resp = render(req["text"], req.get("voice") or DEFAULT_VOICE, float(req.get("speed", 1.0)), req.get("out"))
        except Exception as e:
            resp = dict(ok=False, error=f"{type(e).__name__}: {e}")
        self.wfile.write((json.dumps(resp) + "\n").encode())
        if req.get("cmd", "say") in ("say", "voices"):
            state["last"] = time.time()  # idle clock starts after the render finishes


class Server(socketserver.UnixStreamServer):
    timeout = 5  # handle_request wakes every 5 s so we can check the idle clock


def main():
    SOCK_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    render("Ready.", DEFAULT_VOICE, 1.0, None, write=False)  # warm-up first (first inference is the slow one)
    SOCK.unlink(missing_ok=True)
    srv = Server(str(SOCK), Handler)  # only accept connections once we are actually ready
    os.chmod(SOCK, 0o600)
    state["last"] = time.time()
    print(f"ksay server pid {os.getpid()} ready, idle exit after {IDLE_S/60:.0f} min", flush=True)
    try:
        while not state["stop"] and time.time() - state["last"] < IDLE_S:
            srv.handle_request()
    finally:
        srv.server_close(); SOCK.unlink(missing_ok=True)
        print("ksay server exiting", flush=True)


if __name__ == "__main__":
    main()
