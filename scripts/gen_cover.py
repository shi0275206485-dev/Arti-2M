"""Generate square cover art for a song with the project's t2i workflow (Qwen Image 2.1 by default) through ComfyUI.

Usage (inside a song directory, ComfyUI running):
    python scripts/gen_cover.py --prompt "..." [--seed 7] [--size 1024]

Writes covers/cover_<time>.png (never overwrites) and copies the newest to cover.png.
The workflow comes from the repo's workflows/ (songs have no workflows/ of their own).
"""
import argparse
import shutil
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_client import download_outputs, submit, wait  # noqa: E402
from wf_bindings import fill, load_role  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# "album cover" / a quoted title make the model paint a title plus garbled small print: ask for plain artwork
SUFFIX = ("square artwork, strong centered composition, high detail, clean image with no text, no letters, "
          "no words, no typography, no logo, no watermark, no border, no frame")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--host", default="127.0.0.1:8188")
    args = ap.parse_args()

    wf, b = load_role("t2i", root=ROOT)
    prompt = f"{args.prompt.rstrip('. ')}. {SUFFIX}."
    wf = fill(wf, b, {"prompt": prompt, "seed": args.seed, "width": args.size, "height": args.size,
                      "output": "ai-mv/cover"})
    out = Path("covers")
    out.mkdir(exist_ok=True)
    t0 = time.time()
    saved = download_outputs(args.host, wait(args.host, submit(args.host, wf, str(uuid.uuid4()))), out,
                             f"cover_{time.strftime('%Y%m%d_%H%M%S')}")
    if not saved:
        raise SystemExit("ComfyUI returned no image")
    shutil.copyfile(saved[0], "cover.png")
    print(f"cover: {saved[0].as_posix()} ({time.time() - t0:.0f}s, seed {args.seed})")
    print(f"COVER_FILE {saved[0].as_posix()}")


if __name__ == "__main__":
    main()
