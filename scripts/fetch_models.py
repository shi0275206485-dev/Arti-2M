"""Download the models an official ComfyUI template needs into the models dir.

Usage:
    python scripts/fetch_models.py image_qwen_image_2_1_t2i image_qwen_image_2_1_image_edit [--dry-run]
    python scripts/fetch_models.py --list qwen        # search template names

Reads model names/URLs/directories from the template JSONs shipped with the local
ComfyUI install, skips files already present, resumes partial downloads (*.part).
"""
import argparse
import glob
import json
import re
import sys
import time
from pathlib import Path

import requests

TEMPLATES = Path(r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Lib\site-packages"
                 r"\comfyui_workflow_templates_json\templates")
MODELS = Path(r"E:\models")


def template_models(name):
    paths = glob.glob(str(TEMPLATES / "**" / f"{name}.json"), recursive=True)
    if not paths:
        raise SystemExit(f"template not found: {name}")
    wf = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    found = {}

    def walk(o):
        if isinstance(o, dict):
            url = o.get("url")
            if isinstance(url, str) and url.startswith("https://") and o.get("name") and o.get("directory"):
                found[o["name"]] = (o["directory"], url)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(wf)
    return found


def download(url, dest):
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
        if r.status_code == 416:          # already complete
            part.rename(dest)
            return
        r.raise_for_status()
        if have and r.status_code != 206:
            have = 0                      # server ignored Range; restart
        total = have + int(r.headers.get("content-length", 0))
        t0, last, done = time.time(), 0, have
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(chunk_size=8 << 20):
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 15:
                    last = time.time()
                    rate = (done - have) / (last - t0 + 1e-9) / 1e6
                    print(f"    {dest.name}: {done / 1e9:.1f}/{total / 1e9:.1f} GB  {rate:.0f} MB/s", flush=True)
    if total and part.stat().st_size != total:
        raise IOError(f"incomplete download {dest.name}: {part.stat().st_size} of {total}")
    part.rename(dest)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("templates", nargs="*")
    ap.add_argument("--list", metavar="PATTERN")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models-dir", default=str(MODELS))
    ap.add_argument("--skip", default="", help="comma-separated filenames to skip")
    args = ap.parse_args()

    if args.list:
        for p in sorted(TEMPLATES.glob("*.json")):
            if re.search(args.list, p.stem, re.I) and not p.stem.startswith("index"):
                print(p.stem)
        return
    root = Path(args.models_dir)
    skip = set(filter(None, args.skip.split(",")))
    wanted = {}
    for t in args.templates:
        wanted.update(template_models(t))
    todo = []
    for name, (directory, url) in sorted(wanted.items()):
        dest = root / directory / name
        state = "skip" if name in skip else ("present" if dest.exists() else "download")
        print(f"  [{state:<8}] {directory}/{name}")
        if state == "download":
            todo.append((url, dest))
    if args.dry_run or not todo:
        return
    for i, (url, dest) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {dest.name}", flush=True)
        for attempt in range(5):
            try:
                download(url, dest)
                break
            except (requests.RequestException, IOError) as e:
                print(f"    retry {attempt + 1}: {e}", flush=True)
                time.sleep(10)
        else:
            sys.exit(f"failed: {dest.name}")
    print("all done")


if __name__ == "__main__":
    main()
