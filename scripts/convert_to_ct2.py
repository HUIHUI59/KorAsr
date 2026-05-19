"""Convert HuggingFace Whisper checkpoint to CTranslate2 for faster-whisper.

faster-whisper 只吃 CT2 格式，而 HF 上的微调模型（如 ghost613/whisper-large-v3-turbo-korean）
是 PyTorch safetensors，必须先转一刀。

Usage:
    python scripts/convert_to_ct2.py ghost613/whisper-large-v3-turbo-korean
    python scripts/convert_to_ct2.py ghost613/whisper-large-v3-turbo-korean \
        --out-dir models/ghost613-ko --quantization float16

After conversion, point .env at the local path:
    ASR_MODEL=C:/leolee/KorAsr/models/ghost613-ko
"""
import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Convert HF Whisper -> CT2 for faster-whisper")
    ap.add_argument("model", help="HF repo id or local PyTorch model path")
    ap.add_argument("--out-dir", help="Output dir. Default: models/<last-segment-of-model>")
    ap.add_argument(
        "--quantization",
        default="float16",
        choices=["float32", "float16", "int8", "int8_float16", "bfloat16"],
        help="float16 = same precision as production .env, recommended on CUDA",
    )
    ap.add_argument("--force", action="store_true", help="Overwrite if out_dir exists")
    args = ap.parse_args()

    out = Path(args.out_dir) if args.out_dir else Path("models") / args.model.split("/")[-1]
    if out.exists() and not args.force:
        print(f"[ERR] {out} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    try:
        from ctranslate2.converters import TransformersConverter
    except ImportError:
        print("[ERR] ctranslate2 not installed. Install via:  pip install ctranslate2", file=sys.stderr)
        sys.exit(2)

    print(f"[CONVERT] {args.model} -> {out}  (quantization={args.quantization})")
    out.parent.mkdir(parents=True, exist_ok=True)

    converter = TransformersConverter(
        args.model,
        copy_files=[
            "tokenizer_config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "special_tokens_map.json",
            "vocab.json",
            "added_tokens.json",
            "merges.txt",
            "normalizer.json",
            "generation_config.json",
        ],
        load_as_float16=(args.quantization in ("float16", "int8_float16")),
    )
    converter.convert(str(out), quantization=args.quantization, force=args.force)

    print()
    print(f"[OK] Converted to {out.resolve()}")
    print(f"[NEXT] Edit .env:")
    print(f"    ASR_MODEL={out.resolve().as_posix()}")
    print(f"Then restart the service. Compare quality with bench_asr.py.")


if __name__ == "__main__":
    main()
