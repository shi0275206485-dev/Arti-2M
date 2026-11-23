"""Run gen_videos.py over a shot range in chunks, restarting ComfyUI between chunks.

ComfyUI's RAM use grows by ~1.4 GB per LTX clip and is not released, which gets long runs
killed when the system runs out of memory. Restarting every few clips keeps it bounded.
Shots that already have a clip in clips/index.json are skipped, so this is safe to re-run.

Usage:
    python scripts/run_chunked.py s036 s081 [--chunk 8]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("first")
ap.add_argument("last")
ap.add_argument("--chunk", type=int, default=8)
ap.add_argument("--cache-none", action="store_true", help="start ComfyUI with --cache-none")
args = ap.parse_args()

shots = json.loads(Path("shots/shots.json").read_text(encoding="utf-8"))
cidx = Path("clips/index.json")
done = set(json.loads(cidx.read_text(encoding="utf-8"))) if cidx.exists() else set()
todo = [s["id"] for s in shots if args.first <= s["id"] <= args.last and s["id"] not in done]
print(f"{len(todo)} shots to render: {todo[0] if todo else '-'} .. {todo[-1] if todo else '-'}", flush=True)
py = sys.executable
for i in range(0, len(todo), args.chunk):
    part = todo[i:i + args.chunk]
    subprocess.run([py, "scripts/comfy_server.py", "stop"])
    subprocess.run([py, "scripts/comfy_server.py", "start"] + (["--cache-none"] if args.cache_none else []), check=True)
    subprocess.run([py, "scripts/gen_videos.py", "--only", ",".join(part)], check=True)
print("all chunks done", flush=True)
