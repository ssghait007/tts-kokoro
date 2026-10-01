"""ksay client: sends text to the keep-warm server (auto-starting it), then plays the result."""
import argparse, json, os, socket, subprocess, sys, time
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
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("-o", "--out", default=None, help="also keep the WAV here")
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
    r = call({"cmd": "say", "text": text, "voice": a.voice, "speed": a.speed, "out": a.out and str(Path(a.out).resolve())})
    if not r["ok"]:
        sys.exit(f"ksay: {r['error']}")
    print(f"{'cold start' if cold else 'warm'}: sound after {time.time()-t0:.2f}s (render {r['gen_s']:.2f}s for {r['audio_s']:.1f}s audio)", file=sys.stderr)
    subprocess.run(["afplay", r["path"]])
    if r["temp"]:
        Path(r["path"]).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
