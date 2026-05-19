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


DEFAULT_MODELS = [
    "large-v3",
    "large-v3-turbo",
]


def load_audio(path: Path):
    from faster_whisper.audio import decode_audio
    return decode_audio(str(path), sampling_rate=16000)


def run_one(model_name: str, audio, beam_size: int, initial_prompt: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    load_s = time.time() - t0

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
    audio_s = len(audio) / 16000 if hasattr(audio, "__len__") else 0
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
        print(f"\n========== {path.name} ==========")
        audio = load_audio(path)
        audio_s = len(audio) / 16000
        print(f"Audio: {audio_s:.2f}s")
        results = []
        for m in args.models:
            try:
                r = run_one(m, audio, args.beam_size, args.initial_prompt,
                            args.device, args.compute_type)
                results.append(r)
            except Exception as e:
                print(f"[FAIL] {m}: {e}", file=sys.stderr)

        print(f"\n{'Model':55s}  {'Load':>6s}  {'Infer':>7s}  {'RTF':>6s}  Text")
        print("-" * 130)
        for r in results:
            print(f"{r['model']:55s}  {r['load_s']:>6.2f}  {r['infer_s']:>7.2f}  "
                  f"{r['rtf']:>6.3f}  {r['text'][:70]}")


if __name__ == "__main__":
    main()
