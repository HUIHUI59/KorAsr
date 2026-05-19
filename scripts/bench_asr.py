"""Benchmark multiple ASR models on the same audio file(s).

Runs each model on each file, prints a side-by-side table of inference time,
real-time factor (RTF), and transcribed text. Use it to A/B-test the production
model against a finetune (e.g. ghost613) before switching .env.

Usage:
    python scripts/bench_asr.py data/raw/sample.wav
    python scripts/bench_asr.py data/raw/*.wav \
        --models large-v3 large-v3-turbo models/ghost613-ko
"""
import argparse
import sys
import time
from pathlib import Path

# Windows 默认 cp1252，print 韩文/中文会 UnicodeEncodeError 把整个进程崩掉。
# Production start.py 也做了同样的事 — bench_asr.py 要单独跑就必须自己处理。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


DEFAULT_MODELS = [
    "large-v3",
    "large-v3-turbo",
]

# Keep loaded models alive until process exit so ctranslate2 never runs its
# crashing GPU-cleanup path during the bench. ctranslate2 + Windows + CUDA
# segfaults silently when a WhisperModel is destructed, killing the script
# between iterations.
_MODELS_KEEPALIVE = []


def load_audio(path: Path):
    # The WS handler dumps raw float32 LE 16 kHz mono to data/raw/<sid>.pcm,
    # which is what the production pipeline actually sees - prefer it over
    # ffmpeg-decoded wav/mp3 so the bench matches reality.
    if path.suffix.lower() == ".pcm":
        import numpy as np
        return np.fromfile(str(path), dtype=np.float32)
    from faster_whisper.audio import decode_audio
    return decode_audio(str(path), sampling_rate=16000)


def run_one(model_name: str, audio, beam_size: int, initial_prompt: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel
    print(f"  [{model_name}] loading...", flush=True)
    t0 = time.time()
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    _MODELS_KEEPALIVE.append(model)   # prevent GC-triggered ctranslate2 crash
    load_s = time.time() - t0
    print(f"  [{model_name}] loaded in {load_s:.2f}s, transcribing...", flush=True)

    t1 = time.time()
    segments, _info = model.transcribe(
        audio,
        language="ko",
        beam_size=beam_size,
        vad_filter=False,
        initial_prompt=initial_prompt,
        condition_on_previous_text=True,
    )
    text = "".join(s.text for s in segments).strip()
    infer_s = time.time() - t1
    print(f"  [{model_name}] inferred in {infer_s:.2f}s, text {len(text)} chars", flush=True)
    audio_s = len(audio) / 16000 if hasattr(audio, "__len__") else 0
    # NOTE: do NOT `del model + gc.collect()` here — under Windows + CUDA the
    # ctranslate2 cleanup path crashes Python silently (no traceback, just
    # process exit). Leak the references and let process exit handle it; this
    # bench is a one-shot CLI not a server, so the leak is harmless.
    return {
        "model": model_name,
        "load_s": load_s,
        "infer_s": infer_s,
        "audio_s": audio_s,
        "rtf": infer_s / audio_s if audio_s > 0 else 0,
        "text": text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="Audio file(s) to benchmark")
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                    help="Models to compare (model size, HF repo, or local CT2 path)")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16")
    ap.add_argument("--initial-prompt",
                    default="안녕하세요. 다음은 한국어 강의 및 회의 내용입니다.")
    args = ap.parse_args()

    for f in args.files:
        path = Path(f)
        if not path.exists():
            print(f"[SKIP] {path} not found", file=sys.stderr)
            continue
        print(f"\n========== {path.name} ==========", flush=True)
        audio = load_audio(path)
        audio_s = len(audio) / 16000
        print(f"Audio: {audio_s:.2f}s", flush=True)
        results = []
        for m in args.models:
            try:
                r = run_one(m, audio, args.beam_size, args.initial_prompt,
                            args.device, args.compute_type)
                results.append(r)
            except Exception as e:
                import traceback
                print(f"[FAIL] {m}: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()

        print(f"\n{'Model':55s}  {'Load':>6s}  {'Infer':>7s}  {'RTF':>6s}  Text", flush=True)
        print("-" * 130, flush=True)
        for r in results:
            print(f"{r['model']:55s}  {r['load_s']:>6.2f}  {r['infer_s']:>7.2f}  "
                  f"{r['rtf']:>6.3f}  {r['text'][:70]}", flush=True)
        # Also dump full transcripts for qualitative inspection (truncated text in table)
        print("\n--- FULL TRANSCRIPTS ---", flush=True)
        for r in results:
            print(f"\n[{r['model']}]", flush=True)
            print(r['text'], flush=True)


if __name__ == "__main__":
    main()
