"""Generate a song with YuE2 (running inside WSL) and hand it to the MV pipeline.

Usage:
    python scripts/gen_music.py --id city_lights --style "English, piano pop, female vocal, 88 BPM" \
        --lyrics-file lyrics.txt [--seed 42] [--cot full]
    python scripts/gen_music.py --request music/requests/song.json
    python scripts/gen_music.py --request ... --stage plan      # score only, no audio (fast preview)
    python scripts/gen_music.py --id calm --style "warm solo piano, gentle, 72 BPM" --instrumental   # no vocals

--instrumental (no lyrics needed) follows YuE2's instrumental workflow, each step in its own folder:
music/<id>_<ts>_plan (YuE2 plans a score from the style with empty lyrics), music/<id>_<ts>_ins (the skill's
instrumental.py --prepare-only moves the Vocal melody into the Ins voice, CPU only), then music/<id>_<ts>
renders that score with --low-vram as usual. Vocal-free audio is not guaranteed: listen to the result.

Each run goes to a fresh folder music/<id>_<timestamp>/ (YuE2 artifacts: audio.flac,
score.abc, result.json, request.json ...). Unless --no-promote, the result is then
copied to audio/song.wav and analysis/score.abc for the rest of the pipeline.

YuE2 and ComfyUI share the GPU: close ComfyUI before running this.
"""
import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def to_wsl_path(p: Path, distro):
    """D:\\ai-mv\\x -> /mnt/d/ai-mv/x (via wslpath, so custom mounts also work)."""
    cmd = ["wsl"] + (["-d", distro] if distro else []) + ["-e", "wslpath", "-a", str(p)]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def build_request(args):
    data = {}
    if args.request:
        data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    if args.id:
        data["id"] = args.id
    if args.style:
        data["style"] = args.style
    if args.instrumental:
        data["lyrics"] = ""
    elif args.lyrics_file:
        data["lyrics"] = Path(args.lyrics_file).read_text(encoding="utf-8")
    elif args.lyrics:
        data["lyrics"] = args.lyrics.replace("\\n", "\n")
    if args.seed is not None:
        data["seed"] = args.seed
    if args.cot:
        data["cot"] = args.cot
    data.setdefault("cot", "full")
    if args.cfg_scale is not None:
        data["cfg_scale"] = args.cfg_scale
    abc = {k: v for k, v in (("temperature", args.abc_temperature), ("top_p", args.abc_top_p),
                             ("max_tokens", args.abc_max_tokens)) if v is not None}
    if abc:
        data["abc_sampling"] = {**data.get("abc_sampling", {}), **abc}
    if args.max_tokens is not None:
        data["semantic_sampling"] = {**data.get("semantic_sampling", {}), "max_tokens": args.max_tokens}
    if args.instrumental and data["cot"] == "off":
        raise SystemExit("--instrumental needs a planned score: use --cot full or melody")
    data.setdefault("id", "song")
    missing = [k for k in (("style",) if args.instrumental else ("style", "lyrics")) if not data.get(k)]
    if missing:
        raise SystemExit(f"request is missing {missing} (use --style/--lyrics-file or --request)")
    if not all(c.isalnum() or c in "_-" for c in data["id"]):
        raise SystemExit("id may only contain letters, digits, '_' and '-'")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--request", help="JSON with id/style/lyrics/seed/cot (CLI flags override it)")
    ap.add_argument("--id")
    ap.add_argument("--style", help="genre, instruments, vocal, language, BPM")
    ap.add_argument("--lyrics", help="lyrics text; use \\n for new lines")
    ap.add_argument("--lyrics-file")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--cot", choices=("full", "melody", "off"))
    ap.add_argument("--stage", choices=("audio", "plan"), default="audio")
    # YuE2 request knobs (docs/generation.md, skills/yue2-music/references/generation-and-covers.md)
    ap.add_argument("--cfg-scale", type=float, help="text guidance 0-20 (default 1.0; 1.2 = follow style harder, "
                    "runs a second branch: slower, more VRAM)")
    ap.add_argument("--abc-temperature", type=float, help="score planner temperature (default 0.7)")
    ap.add_argument("--abc-top-p", type=float, help="score planner top_p (default 0.9)")
    ap.add_argument("--abc-max-tokens", type=int, help="score planner token limit (default 4096)")
    ap.add_argument("--max-tokens", type=int, help="audio (semantic) token limit (default 9000, ~25 tokens/s)")
    ap.add_argument("--instrumental", action="store_true",
                    help="no vocals / no lyrics: plan -> move melody to Ins -> render (YuE2 instrumental workflow)")
    ap.add_argument("--yue-dir", default="~/AI-Music/YuE", help="YuE2 repo inside WSL")
    ap.add_argument("--distro", help="WSL distro name (default distro if omitted)")
    ap.add_argument("--budget", type=float, default=8, help="GiB VRAM budget for yue2 (--budget)")
    ap.add_argument("--no-low-vram", action="store_true")
    ap.add_argument("--online", action="store_true", help="allow Hugging Face lookups (default: cached files only)")
    ap.add_argument("--no-promote", action="store_true", help="don't copy to audio/song.wav + analysis/score.abc")
    ap.add_argument("--audio-out", default="audio/song.wav")
    ap.add_argument("--promote", metavar="RUN_DIR",
                    help="only promote an existing run (e.g. music/rescue_20261117_...) to audio/song.wav")
    ap.add_argument("--root", help="project root for music/, audio/, analysis/ (default: this repo)")
    args = ap.parse_args()
    if args.root:
        global ROOT
        ROOT = Path(args.root).resolve()

    if args.promote:
        promote(args.promote, args.audio_out)
        return 0
    request = build_request(args)
    run_id = f"{request['id']}_{time.strftime('%Y%m%d_%H%M%S')}"
    request["id"] = run_id
    music_dir = ROOT / "music"
    run_dir = music_dir / run_id
    req_dir = music_dir / "requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    req_path = req_dir / f"{run_id}.json"
    req_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_yue(req, stage, budget=None, resume=False):
        yue_cmd = (f"cd {args.yue_dir} && PYTORCH_ALLOC_CONF=expandable_segments:True .venv/bin/yue2 generate"
                   f" --request '{to_wsl_path(req, args.distro)}'"
                   f" --output '{to_wsl_path(music_dir, args.distro)}'"
                   f" --device cuda --budget {budget or args.budget} --stage {stage}"
                   + ("" if args.no_low_vram else " --low-vram")
                   + ("" if args.online else " --offline")
                   + (" --resume" if resume else ""))
        print(f"[gen_music] wsl> {yue_cmd}", flush=True)
        return subprocess.run(wsl_base + ["-e", "bash", "-lc", yue_cmd])

    wsl_base = ["wsl"] + (["-d", args.distro] if args.distro else [])
    t0 = time.time()
    if args.instrumental and args.stage == "audio":
        # 1) YuE2 plans a score from the style alone
        plan_id = f"{run_id}_plan"
        plan_req = req_dir / f"{plan_id}.json"
        plan_req.write_text(json.dumps(dict(request, id=plan_id), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[gen_music] instrumental 1/3: planning a score ({request['style']})")
        if run_yue(plan_req, "plan").returncode != 0 or not (music_dir / plan_id / "score.abc").exists():
            raise SystemExit("[gen_music] instrumental planning failed")
        score = music_dir / plan_id / "score.abc"
        trimmed = trim_abc(score.read_text(encoding="utf-8"))
        if trimmed is not None:   # plan hit YuE2's token limit mid-line: keep only complete Vocal+Ins groups
            score = music_dir / plan_id / "score_trimmed.abc"
            score.write_text(trimmed, encoding="utf-8")
            print(f"[gen_music] WARNING: the plan was cut off at the token limit; dropped the unfinished last "
                  f"group -> {score.name} (the song may end without an outro)", flush=True)
        # 2) move the Vocal melody into Ins (CPU; the skill's own converter and checks)
        ins_dir = music_dir / f"{run_id}_ins"
        conv = (f"cd {args.yue_dir}/skills/yue2-music/instrumental && {args.yue_dir}/.venv/bin/python"
                f" scripts/instrumental.py run --abc '{to_wsl_path(score, args.distro)}'"
                f" --style {shlex.quote(request['style'])} --empty-lyrics --prepare-only"
                f" --output '{to_wsl_path(ins_dir, args.distro)}'")
        print("[gen_music] instrumental 2/3: moving the melody to the instrument voice", flush=True)
        if subprocess.run(wsl_base + ["-e", "bash", "-lc", conv]).returncode != 0:
            raise SystemExit("[gen_music] instrumental score conversion failed (see above)")
        prepared = json.loads((ins_dir / "prepared/request.json").read_text(encoding="utf-8"))
        prepared["id"] = run_id
        for k in ("seed", "cfg_scale", "semantic_sampling"):   # the render keeps the user's audio settings
            if k in request:
                prepared[k] = request[k]
        request = prepared
        req_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[gen_music] instrumental 3/3: rendering the converted score", flush=True)
    print(f"[gen_music] {run_id}: {request['style']}")
    budget = args.budget
    # cfg_scale != 1 runs a second (unconditional) pass in the same batch: at budget 8 YuE2 caps itself at 6 GiB
    # and dies at the first audio token (seen 2026-11-24 with cfg 1.2, 8.6 GiB still free). Start higher.
    cfg = request.get("cfg_scale", 1.01 if request.get("cot") == "off" else 1.0)
    if args.stage == "audio" and float(cfg) != 1.0 and budget < 12:
        budget = 12
        print(f"[gen_music] cfg_scale {cfg} needs more GPU memory: using budget 12", flush=True)
    proc = run_yue(req_path, args.stage, budget=budget)
    fail = run_dir / "failure.json"
    if proc.returncode != 0 and fail.exists() and "OutOfMemory" in fail.read_text(encoding="utf-8") \
            and budget < 12:
        # long/dense songs can outgrow the budget's memory cap at audio synthesis; the GPU usually has room.
        # --resume only reuses a COMPLETED run (a failed one is "Nonempty output"), so keep the failed attempt
        # under another name and render again from scratch.
        kept = run_dir.with_name(f"{run_dir.name}_oom_b{budget:g}")
        run_dir.rename(kept)
        print(f"[gen_music] out of GPU memory at budget {budget:g} (kept as {kept.name}); retrying with budget 12",
              flush=True)
        proc = run_yue(req_path, args.stage, budget=12)
    elapsed = time.time() - t0
    if proc.returncode != 0:
        fail = run_dir / "failure.json"
        detail = fail.read_text(encoding="utf-8") if fail.exists() else "(no failure.json)"
        raise SystemExit(f"[gen_music] yue2 failed (exit {proc.returncode}) after {elapsed:.0f}s\n{detail}")

    if args.stage == "plan":
        print(f"[gen_music] plan done in {elapsed:.0f}s -> {run_dir / 'score.abc'}")
        return

    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    truncated = [k for k, v in result.get("truncated", {}).items() if v]
    print(f"[gen_music] done in {elapsed:.0f}s: {result['audio_seconds']:.1f}s of audio @ "
          f"{result['sample_rate']} Hz -> {run_dir}")
    if truncated:
        print(f"[gen_music] WARNING: generation truncated at stage(s) {truncated}; "
              "the song may end early. Consider shorter lyrics or a different seed.", file=sys.stderr)

    if args.no_promote:
        return 1 if truncated else 0
    promote(run_dir, args.audio_out)
    return 1 if truncated else 0


def trim_abc(text):
    """If a planned score ends mid-group (YuE2 hit its token limit), return it cut back to the last complete
    group: every voice's music line present and ending in a barline. None when the score is already whole."""
    lines = text.rstrip("\n").split("\n")
    head_end = next((i for i, l in enumerate(lines) if l.startswith("K:")), None)
    if head_end is None:
        return None
    voices = [l.split()[1] for l in lines[:head_end] if l.startswith("V:") and len(l.split()) > 1]
    body = lines[head_end + 1:]
    keep, group, pending = 0, set(), []   # keep = number of body lines that end a complete group
    for i, l in enumerate(body):
        if l.startswith("V:"):
            pending = [l.split()[1] if len(l.split()) > 1 else ""]
        elif l.startswith("%") or not l.strip():
            continue
        elif pending:
            if not l.rstrip().endswith("|"):
                break
            group.add(pending[0])
            pending = []
            if voices and set(voices) <= group:
                keep, group = i + 1, set()
    rest = [l for l in body[keep:] if l.strip() and not l.startswith("%")]
    if not keep or not rest:
        return None
    return "\n".join(lines[:head_end + 1] + body[:keep]) + "\n"


def promote(run_dir, audio_out="audio/song.wav"):
    """Make a finished run the pipeline's current song (audio/song.wav + analysis/)."""
    run_dir = Path(run_dir).resolve()
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found in PATH")
    audio_out = ROOT / audio_out
    audio_out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(run_dir / "audio.flac"),
                    "-c:a", "pcm_s24le", str(audio_out)], check=True)
    analysis = ROOT / "analysis"
    analysis.mkdir(exist_ok=True)
    if (run_dir / "score.abc").exists():
        shutil.copyfile(run_dir / "score.abc", analysis / "score.abc")
    elif (analysis / "score.abc").exists():   # cot=off has no score: don't let analysis use the previous song's
        (analysis / "score.abc").rename(analysis / f"score_old_{time.strftime('%Y%m%d_%H%M%S')}.abc")
    (analysis / "song_source.json").write_text(json.dumps(
        {"run_dir": str(run_dir.relative_to(ROOT)), "request": request,
         "audio_seconds": result["audio_seconds"], "truncated": result.get("truncated")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gen_music] promoted {run_dir.name} -> {audio_out.relative_to(ROOT)}, analysis/score.abc")


if __name__ == "__main__":
    raise SystemExit(main())
