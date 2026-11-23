"""Animate each shot's chosen first frame with LTX-2.3 through ComfyUI.

Usage:
    python scripts/gen_videos.py [--only s011,s012 | --range s001-s013] [--width 1280 --height 720]
                                 [--seed-offset 0] [--vocals stems/htdemucs/song/vocals.wav]

video.mode "lipsync" -> workflows/ltx23_ia2v_api.json: the shot's slice of the vocal stem
drives the mouth (audio latent is kept, not regenerated). "i2v" -> workflows/ltx23_i2v_api.json.
First frames come from shots/frames/index.json ("chosen"). Each shot is generated
gen_seconds long (slot + handle). Output never overwrites: clips/<id>_v<offset>_<time>.mp4;
clips/index.json records versions and the chosen one.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_client import download_outputs, submit, upload, wait  # noqa: E402
from wf_bindings import fill, load_role  # noqa: E402

WF = {"i2v": "workflows/ltx23_i2v_api.json", "lipsync": "workflows/ltx23_ia2v_api.json"}
WHO = {"NOVA": "the woman with the silver-white bob and black techwear jacket",
       "ECHO": "the woman with long black-and-magenta hair in a white fiber-optic outfit"}
STYLE = "Cinematic cyberpunk K-pop music video shot, realistic motion, film grain."
# Web-agent projects: per-project member descriptions (members.json "video_desc") and style (env)
_mj = Path("shots/members.json")
if _mj.exists():
    for _name, _m in json.loads(_mj.read_text(encoding="utf-8")).get("members", {}).items():
        if _m.get("video_desc"):
            WHO[_name] = _m["video_desc"]
STYLE = os.environ.get("MV_VIDEO_STYLE", STYLE)


def video_prompt(s):
    text = s["frame"]["prompt"]
    for i, m in enumerate(s["members"]):
        text = text.replace(f"the woman from image {i + 1}", WHO[m]).replace(f"the man from image {i + 1}", WHO[m])
    text = text[0].upper() + text[1:]
    motion = s["video"]["prompt"]
    lip = ""
    if s["video"]["mode"] == "lipsync":
        lip = f" {WHO[s['lipsync']].capitalize()} is singing along to the vocals with clear, accurate mouth movements."
    return f"{text}. Action: {motion}.{lip} {STYLE}"


def cut_vocal(vocals, start, seconds, dest):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}",
                    "-i", str(vocals), "-ac", "2", "-ar", "48000", str(dest)], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", default="shots/shots.json")
    ap.add_argument("--frames", default="shots/frames/index.json")
    ap.add_argument("--vocals", default="stems/htdemucs/song/vocals.wav")
    ap.add_argument("--host", default="127.0.0.1:8188")
    ap.add_argument("--out", default="clips")
    ap.add_argument("--only")
    ap.add_argument("--range")
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()
    if not Path(args.vocals).exists():   # analyze_audio.py --stems writes the 6-stem model's folder
        alt = Path(str(args.vocals).replace("htdemucs/", "htdemucs_6s/"))
        if alt.exists():
            args.vocals = str(alt)

    shots = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    if args.only:
        ids = set(args.only.split(","))
        shots = [s for s in shots if s["id"] in ids]
    elif args.range:
        a, b = args.range.split("-")
        shots = [s for s in shots if a <= s["id"] <= b]
    # one model at a time: all i2v shots, then all lipsync shots (i2v and lipsync may use different workflows,
    # e.g. MiniMax H3 + LTX; alternating would reload ~20-40GB of weights per shot)
    shots.sort(key=lambda s: s["video"]["mode"] != "i2v")
    frames = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    bases = {k: load_role(k) for k in WF}   # workflows/bindings.json may swap in other workflows
    client = str(uuid.uuid4())
    tmp = Path(tempfile.mkdtemp(prefix="aimv_vocal_"))
    t_all = time.time()

    for i, s in enumerate(shots, 1):
        if s["id"] not in frames:
            print(f"[{i}/{len(shots)}] {s['id']}: no first frame yet, skipped")
            continue
        mode = s["video"]["mode"]
        base, b = bases[mode]
        seed = 2000 + int(s["id"][1:]) + args.seed_offset
        values = {"image": upload(args.host, frames[s["id"]]["chosen"]), "prompt": video_prompt(s),
                  "seconds": float(s["gen_seconds"]), "seed": seed, "width": args.width, "height": args.height,
                  "output": f"ai-mv/clip_{s['id']}"}
        if mode == "lipsync":
            clip = tmp / f"{s['id']}_vocal.wav"
            cut_vocal(args.vocals, s["start"], s["gen_seconds"], clip)
            values["audio"] = upload(args.host, clip)
        wf = fill(json.loads(json.dumps(base)), b, values)
        t0 = time.time()
        pid = submit(args.host, wf, client)
        saved = download_outputs(args.host, wait(args.host, pid, timeout=3600), out,
                                 f"{s['id']}_v{args.seed_offset}_{int(time.time())}")
        if not saved:
            raise SystemExit(f"{s['id']}: no output")
        dt = time.time() - t0
        entry = index.get(s["id"], {})
        entry.setdefault("versions", []).append({"file": saved[0].as_posix(), "seed": seed, "mode": mode,
                                                 "frame": frames[s["id"]]["chosen"], "seconds": s["gen_seconds"],
                                                 "size": [args.width, args.height], "gen_time": round(dt, 1)})
        if not entry.get("pinned"):
            entry["chosen"] = saved[0].as_posix()
        index[s["id"]] = entry
        index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[{i}/{len(shots)}] {s['id']} {mode:<7} {s['gen_seconds']:.2f}s clip in {dt:6.1f}s -> {saved[0].name}",
              flush=True)
    print(f"done: {len(shots)} clips in {time.time() - t_all:.0f}s")


if __name__ == "__main__":
    main()
