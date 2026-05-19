"""Workaround: ghost613/whisper-large-v3-turbo-korean is missing
generation_config.json (uploader oversight), which ctranslate2's
TransformersConverter requires. Borrow it from the base model
openai/whisper-large-v3-turbo, then convert.

Usage:
    python scripts/fix_ghost613_convert.py

Output:
    models/whisper-large-v3-turbo-korean/  (CT2 fp16, ready for faster-whisper)
"""
import shutil
import sys
from pathlib import Path

REPO = "ghost613/whisper-large-v3-turbo-korean"
BASE = "openai/whisper-large-v3-turbo"
SRC_DIR = Path("models/_ghost613_src")
OUT_DIR = Path("models/whisper-large-v3-turbo-korean")


def main():
    from huggingface_hub import snapshot_download, hf_hub_download
    from ctranslate2.converters import TransformersConverter

    print(f"[1/3] Materialising {REPO} into {SRC_DIR} ...")
    SRC_DIR.parent.mkdir(parents=True, exist_ok=True)
    src = Path(snapshot_download(repo_id=REPO, local_dir=str(SRC_DIR)))
    print(f"      -> {src}")

    gen_cfg = src / "generation_config.json"
    if gen_cfg.exists():
        print(f"[2/3] generation_config.json already present")
    else:
        print(f"[2/3] Borrowing generation_config.json from {BASE} ...")
        borrowed = hf_hub_download(repo_id=BASE, filename="generation_config.json")
        shutil.copy(borrowed, gen_cfg)
        print(f"      -> {gen_cfg}")

    if OUT_DIR.exists():
        print(f"[3/3] Removing stale {OUT_DIR} ...")
        shutil.rmtree(OUT_DIR)

    print(f"[3/3] Converting to CT2 float16 -> {OUT_DIR} ...")
    converter = TransformersConverter(
        str(src),
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
        load_as_float16=True,
    )
    converter.convert(str(OUT_DIR), quantization="float16")

    print()
    print(f"[OK] Done. Set in .env:")
    print(f"    ASR_MODEL={OUT_DIR.resolve().as_posix()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
