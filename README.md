# tts-kokoro

## TL;DR

We tested 8 local text-to-speech models on an M5 Pro (64 GB).

**Kokoro won.** Fast, tiny, natural, 54 voices.

Type `ksay "hello"` and Bella talks to you.

After the first call, speech starts in **0.2 seconds**.

Cost: ~0.7 GB of memory, given back after 10 idle minutes.

---

## How we got here

It started with a simple question.

*Which text-to-speech model should I run on my Mac?*

And a small annoyance.

Kokoro on my M3 MacBook would sometimes sound… cracky 🎧

So we did what any reasonable person does.

We tested everything.

## The contenders

Same sentence for every model:

> "Sunset was calming today. It was like the last brush stroke from the sun on the empty canvas of the sky."

| Model | Disk | Peak RAM | Speed vs real time | Notes |
|---|---|---|---|---|
| **Kokoro** 82M | 0.36 GB | 0.8 GB | 34× faster | 🏆 Our pick. Community favourite for speed. |
| Kitten nano | 0.06 GB | 0.21 GB | 86× faster | Smallest and fastest. Quality not judged. |
| Kitten micro | 0.14 GB | 0.32 GB | 34× faster | |
| Kitten mini | 0.29 GB | 0.47 GB | 24× faster | |
| Soprano 1.1 | 0.28 GB | 1.0 GB | 34× faster | Nowhere near its "2000×" claim on a Mac. |
| Pocket TTS | 0.24 GB | 0.43 GB | 9× faster | 8 built-in voices. |
| Chatterbox | 3.2 GB | 3.4 GB | ~2.5× faster | Best for voice cloning. Community pick for quality. |
| Orpheus 3B | 6.7 GB | 7.4 GB | 2× *slower* | Most emotional (`<sigh>`, `<laugh>`). Offline only. |

Every model fits easily in 64 GB.

So memory wasn't the real difference.

Speed was.

## Why Kokoro

It isn't the smallest. Kitten nano is.

It isn't the most expressive. Orpheus is.

But it is the best **balance**.

Fast enough to feel instant. Small enough to forget about. Good enough to actually enjoy listening to.

That's also what most developers recommend right now:

- Kokoro for speed.
- Chatterbox for quality.
- Orpheus for emotion.
- Piper if you're on a Raspberry Pi.

## About that crackle 🔧

Known causes, and what this repo does about each:

| Cause | Fix |
|---|---|
| Long text confuses the model | Split into sentences, ≤250 characters per chunk |
| Clicks where chunks join | 30 ms crossfade |
| Playback runs ahead of generation | Render the whole file first, then play |
| PyTorch on Mac GPU (MPS/fp16) glitches | Use MLX with bf16 weights instead |
| Speed above ~1.3 | Keep speed at 1.0 |
| Wrong sample rate | Keep 24 kHz end to end |

The result?

No crackle since the move to MLX. Not on the new Mac. Not on the old M3 that started it all ✅

## Using it

```bash
ksay "Hello there"                  # Bella, the default
ksay -v af_nicole "Hello there"     # Nicole
echo "some text" | ksay             # from a pipe
ksay -o hello.wav "Hello"           # also keep the file
ksay --list-voices                  # all 54
ksay --status                       # is the server running?
ksay --stop                         # free the memory now
```

The voice prefix picks the language:

- `af_` / `am_`: American English
- `bf_` / `bm_`: British English
- `hf_` / `hm_`: Hindi (give it Hindi text)

Setup on a new machine:

```bash
brew install espeak-ng
uv sync
alias ksay="/path/to/tts-kokoro/ksay"   # add to ~/.zshrc
```

## The keep-warm trick ⚡

Every `ksay` used to start from scratch.

Start Python. Load the model. Warm it up. Then speak.

About **2.85 seconds** of silence, every time.

Now a small background server keeps Kokoro loaded.

| | Time to first sound | Memory |
|---|---|---|
| Without server | ~2.85 s | ~0.8 GB, only while running |
| First call (server starts) | ~2.8 s | |
| Every call after | **~0.22 s** (13× faster) | ~0.7 GB, 0% CPU while idle |

After 10 minutes of silence, it exits and gives the memory back.

We checked. It held 0.74 GB for 10 minutes, then quietly left. Free memory went from 92% to 94% ✅

Next call? It starts itself again.

The trade-off is simple.

About 1% of your RAM, for speech that feels instant.

One catch: long text still renders fully before playing.

So a 70-second paragraph takes ~1.8 s to start.

For the curious: Ollama keeps models warm for 5 minutes, LM Studio for 60. We picked 10. Change it with `KSAY_IDLE_MIN`.

## The fine print

- Speed and memory were measured. Voice quality was not scored, so trust your ears.
- Most numbers are from a single run on an M5 Pro.
- Chatterbox's "voices" are clones of a reference clip, not built-in voices.

## Related repos

- `tts-chatterbox`: voice cloning
- `tts-orpheus`: emotional, slow
- `tts-lightweight-bench`: Kitten, Soprano, Pocket benchmarks, plus a listening tour where every model announces itself

That's it.

Go make your Mac talk 😊
