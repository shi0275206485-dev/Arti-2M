"""Generate the first frame of each shot with Qwen Image 2.1 through ComfyUI.

Usage:
    python scripts/gen_frames.py [--shots shots/shots.json] [--only s001,s002 | --range s001-s013]
                                 [--seed-offset 0] [--width 1344 --height 768]

frame.mode picks the workflow: t2i (no member), edit1 (one reference), edit2 (two refs).
Member reference images come from shots.json (frame.refs). Seeds are fixed per shot
(1000 + shot number + seed offset) so a frame can be reproduced; use --seed-offset for
a new variant. Output files never overwrite: shots/frames/<id>_v<offset>_<time>.png.
Writes shots/frames/index.json mapping shot id -> chosen frame (latest unless pinned).
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_client import download_outputs, submit, upload, wait  # noqa: E402
from wf_bindings import fill, load_role  # noqa: E402

WORKFLOWS = {"t2i": "workflows/qwen21_t2i_api.json",
             "edit1": "workflows/qwen21_edit_api.json",
             "edit2": "workflows/qwen21_edit2_api.json",
             "edit3": "workflows/qwen21_edit3_api.json"}
STYLE = ("cinematic cyberpunk K-pop music video still, anamorphic lens, shallow depth of field, "
         "film grain, photorealistic, no text, no watermark")
# keyed by number of MEMBERS (member refs come first; a location plate, if any, comes last)
KEEP = {1: "Keep her face, hairstyle and outfit exactly the same as in image 1.",
        2: "Keep both women's faces, hairstyles and outfits exactly the same as in images 1 and 2."}
PLATE_STYLE = ("cinematic establishing plate, empty set with no people in the foreground, anamorphic lens, "
               "film grain, photorealistic, no text, no watermark")
# Web-agent projects override the look per project
STYLE = os.environ.get("MV_FRAME_STYLE", STYLE)
if os.environ.get("MV_KEEP_NEUTRAL"):
    KEEP = {1: "Keep the face, hairstyle and outfit of the person in image 1 exactly the same.",
            2: "Keep both people's faces, hairstyles and outfits exactly the same as in images 1 and 2."}


def make_plates(args, bases, client):
    """Generate missing location plates (empty sets) with t2i: shots/plates/<location>.png."""
    plates = Path(args.plates)
    locations = json.loads((plates / "locations.json").read_text(encoding="utf-8"))
    for loc, desc in locations.items():
        dest = plates / f"{loc}.png"
        if dest.exists():
            print(f"plate {loc}: exists")
            continue
        base, b = bases["t2i"]
        wf = fill(json.loads(json.dumps(base)), b, {
            "prompt": f"{desc}. {PLATE_STYLE}.", "seed": 500 + sorted(locations).index(loc) + args.seed_offset,
            "width": args.width, "height": args.height, "output": f"ai-mv/plate_{loc}"})
        saved = download_outputs(args.host, wait(args.host, submit(args.host, wf, client)), plates, f"_{loc}_tmp")
        saved[0].rename(dest)
        print(f"plate {loc}: generated")


def select(shots, only, rng):
    if only:
        ids = set(only.split(","))
        return [s for s in shots if s["id"] in ids]
    if rng:
        a, b = rng.split("-")
        return [s for s in shots if a <= s["id"] <= b]
    return shots


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", default="shots/shots.json")
    ap.add_argument("--host", default="127.0.0.1:8188")
    ap.add_argument("--out", default="shots/frames")
    ap.add_argument("--only")
    ap.add_argument("--range")
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--width", type=int, default=1344)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--plates", nargs="?", const="shots/plates", default=None,
                    help="generate missing location plates first (shots/plates/<loc>.png), then stop")
    args = ap.parse_args()
    if args.plates:
        bases = {"t2i": load_role("t2i")}
        make_plates(args, bases, str(uuid.uuid4()))
        return

    shots = select(json.loads(Path(args.shots).read_text(encoding="utf-8")), args.only, args.range)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    bases = {k: load_role(k) for k in WORKFLOWS}   # workflows/bindings.json may swap in other workflows
    client = str(uuid.uuid4())
    t_all = time.time()

    for i, s in enumerate(shots, 1):
        f = s["frame"]
        base, b = bases[f["mode"]]
        prompt = f"{f['prompt']}. {KEEP.get(len(s['members']), '')} {STYLE}.".replace("..", ".")
        seed = 1000 + int(s["id"][1:]) + args.seed_offset
        values = {"prompt": prompt, "seed": seed, "width": args.width, "height": args.height,
                  "output": f"ai-mv/frame_{s['id']}"}
        for k, ref in enumerate(f["refs"], 1):
            values[f"image{k}"] = upload(args.host, ref)
        # built-in edit workflows also get 468.switch=True (output size from 456) via the binding's "fixed"
        wf = fill(json.loads(json.dumps(base)), b, values)
        t0 = time.time()
        pid = submit(args.host, wf, client)
        saved = download_outputs(args.host, wait(args.host, pid), out,
                                 f"{s['id']}_v{args.seed_offset}_{int(time.time())}")
        if not saved:
            raise SystemExit(f"{s['id']}: no output")
        entry = index.get(s["id"], {})
        entry.setdefault("versions", []).append({"file": saved[0].as_posix(), "seed": seed, "prompt": prompt})
        if not entry.get("pinned"):
            entry["chosen"] = saved[0].as_posix()
        index[s["id"]] = entry
        index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[{i}/{len(shots)}] {s['id']} {f['mode']:<5} {time.time() - t0:5.1f}s -> {saved[0].name}", flush=True)
    print(f"done: {len(shots)} frames in {time.time() - t_all:.0f}s")


if __name__ == "__main__":
    main()
