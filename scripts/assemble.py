"""Cut generated clips onto the beat grid and mux with the song.

Shot-list mode (use this): every shot from shots/shots.json fills its own bar-aligned slot
with its chosen clip from clips/index.json (first-frame still if no clip yet):
    python scripts/assemble.py --shots shots/shots.json --audio audio/song.wav \
        [--start 0 --end 44.6] [--out output/mv.mp4]

Legacy mode (no shot list):
    python scripts/assemble.py --beats analysis/beats.json --clips clips \
        --audio audio/song.wav [--bars-per-cut 2] [--chorus-bars 1] [--out output/mv.mp4]

Clips are used in filename order (s01_..., s02_...), looping if there are fewer
clips than cuts. Each cut spans N bars (fewer in high-energy sections).
Clips shorter than their slot are slowed down to fit; longer ones are trimmed.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".gif"}
FAST_SECTIONS = ("chorus", "hook", "drop")


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def build_cuts(beats, bars_per_cut, chorus_bars, energy_threshold):
    downbeats = beats["downbeats"]
    duration = beats["duration"]
    sections = beats["sections"]

    def is_fast(t):
        # score-derived sections carry names; chorus-like ones cut faster regardless of energy
        for s in sections:
            if s["start"] <= t < s["end"]:
                name = s.get("name", "").lower().replace("-", "")
                if any(k in name for k in FAST_SECTIONS) and "pre" not in name:
                    return True
                return s["mean_energy"] >= energy_threshold
        return False

    points = [0.0]
    i = 0
    while i < len(downbeats):
        t = downbeats[i]
        step = chorus_bars if is_fast(t) else bars_per_cut
        if t > points[-1] + 0.5:
            points.append(t)
        i += step
    # snap section boundaries in as cut points too
    for s in sections:
        if all(abs(s["start"] - p) > 0.5 for p in points):
            points.append(s["start"])
    points = sorted(p for p in points if p < duration - 0.5) + [duration]
    return list(zip(points[:-1], points[1:]))


TRANSITIONS = {"flash": ("white", 0.25), "dip": ("black", 0.3), "fade": ("black", 0.6)}
GRADES = {"warm": "colorbalance=rs=.06:gs=.02:bs=-.06", "cool": "colorbalance=rs=-.05:gs=0:bs=.06",
          "tealorange": "colorbalance=rs=-.08:bs=.08:rh=.08:bh=-.08,eq=saturation=1.1",
          "bw": "hue=s=0,eq=contrast=1.1", "vintage": "curves=preset=vintage", "contrast": "eq=contrast=1.15:saturation=1.1"}


def _hits(times, dur, decay):
    """ffmpeg expression (of t, seconds into the part) that is 1 at each hit and decays linearly over `decay` s."""
    terms = [f"between(t,{t:.3f},{t + decay:.3f})*({t + decay:.3f}-t)/{decay}" for t in times if -decay < t < dur]
    return "+".join(terms)


def fx_filter(fx, a, b, W, H):
    """Music-driven effects for the part [a, b): brightness pulse and punch-in zoom on drum hits (Neural Frames
    style stem reactivity, done in ffmpeg). fx: {"times": [...], "pulse": 0..1, "punch": 0..1, "ranges": [[s,e]]}."""
    if not fx:
        return ""
    times = [t - a for t in fx["times"] if a - 0.4 <= t < b
             and (not fx.get("ranges") or any(s <= t < e for s, e in fx["ranges"]))]
    if not times:
        return ""
    out = ""
    if fx.get("punch"):
        z = f"{0.06 * fx['punch']:.3f}*({_hits(times, b - a, 0.35)})"
        out += (f",scale=w='trunc(iw*(1+{z})/2)*2':h='trunc(ih*(1+{z})/2)*2':eval=frame,"
                f"crop={W}:{H}")
    if fx.get("pulse"):
        out += f",eq=brightness='{0.22 * fx['pulse']:.3f}*({_hits(times, b - a, 0.22)})':eval=frame"
    return out


def assemble_shots(args):
    """Shot-list mode: each shot fills exactly its [start, end) slot from shots.json.

    Frame counts come from the absolute timeline (round(end*fps) - round(start*fps)) so the
    picture never drifts against the song. Clips are taken from their first frame, which keeps
    lip-sync clips (generated from the vocal slice starting at the shot start) in sync. Shots
    without a chosen clip fall back to their first-frame still, then to black.
    """
    shots = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    cidx = Path(args.clips_index)
    clips = json.loads(cidx.read_text(encoding="utf-8")) if cidx.exists() and not args.stills else {}
    fidx = Path(args.frames_index)
    frames = json.loads(fidx.read_text(encoding="utf-8")) if fidx.exists() else {}
    t_from = args.start if args.start is not None else 0.0
    t_to = args.end if args.end is not None else shots[-1]["end"]
    sel = [s for s in shots if s["end"] > t_from + 1e-3 and s["start"] < t_to - 1e-3]
    # Time not covered by any shot (an intro before the first bar, gaps, an outro) must still get frames,
    # or everything after it slides earlier against the song. Fill it with the stage plate (or black).
    timeline, cursor = [], t_from
    for s in sel:
        if s["start"] > cursor + 1e-3:
            timeline.append({"id": None, "start": cursor, "end": s["start"]})
        timeline.append(s)
        cursor = max(cursor, s["end"])
    if t_to > cursor + 1e-3:
        timeline.append({"id": None, "start": cursor, "end": t_to})
    filler = Path(args.filler) if args.filler and Path(args.filler).exists() else None
    W, H, FPS = args.width, args.height, args.fps
    edits = json.loads(Path(args.edits).read_text(encoding="utf-8")) if args.edits and Path(args.edits).exists() else {}
    fx = json.loads(Path(args.fx).read_text(encoding="utf-8")) if args.fx and Path(args.fx).exists() else None
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=yuv420p"
    used = {"clip": 0, "still": 0, "black": 0, "filler": 0}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        for n, s in enumerate(timeline):
            a, b = max(s["start"], t_from), min(s["end"], t_to)
            nframes = round(b * FPS) - round(a * FPS)
            if nframes <= 0:
                continue
            offset = a - s["start"]                       # when the range starts mid-shot
            part = tmp / f"part_{n:04d}.mp4"
            src = clips.get(s["id"], {}).get("chosen") if s["id"] else None
            if s["id"] is None:
                kind = "filler"
                print(f"no shot covers {a:.2f}-{b:.2f}s -> {'stage plate' if filler else 'black'}")
                if filler:
                    vf = fit
                    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(filler)]
                else:
                    vf = "format=yuv420p"
                    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}"]
            elif src and Path(src).exists():
                kind = "clip"
                if s.get("video", {}).get("mode") != "lipsync":   # lip-sync must start at 0 to stay in sync
                    spare = max(0.0, probe_duration(src) - s["seconds"])
                    offset += max(0.0, min(float(edits.get(s["id"], {}).get("offset") or 0), spare))
                pad = max(0.0, (offset + nframes / FPS) - probe_duration(src))
                vf = fit + (f",tpad=stop_mode=clone:stop_duration={pad + 0.1:.3f}" if pad > 0 else "")
                cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{offset:.3f}", "-i", src]
            elif s["id"] and frames.get(s["id"], {}).get("chosen"):
                kind = "still"
                vf = fit
                cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
                       "-i", frames[s["id"]]["chosen"]]
            elif filler:   # shot without a frame yet (e.g. just changed in the storyboard editor): the empty stage
                kind = "filler"
                vf = fit
                cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(filler)]
            else:
                kind = "black"
                vf = "format=yuv420p"
                cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}"]
            used[kind] += 1
            if kind != "black":
                vf += fx_filter(fx, a, b, W, H)
            tr = TRANSITIONS.get(edits.get(s["id"], {}).get("trans")) if s["id"] and a == s["start"] else None
            if tr:   # transition INTO this shot, inside its own slot (the cut stays on the beat)
                vf += f",fade=t=in:st=0:d={tr[1]}:color={tr[0]}"
            subprocess.run(cmd + ["-vf", vf, "-frames:v", str(nframes), "-an", "-c:v", "libx264",
                                  "-preset", "veryfast", "-crf", "18", "-r", str(FPS),
                                  # same timescale for every part, or concat-copy drops frames
                                  "-video_track_timescale", str(FPS * 1000), str(part)], check=True)
            parts.append(part)
        listfile = tmp / "list.txt"
        listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        # finishing pass (one re-encode): colour grade -> upscale -> burned-in lyric captions
        post = []
        if args.grade in GRADES:
            post.append(GRADES[args.grade])
        if args.upscale:
            uw, uh = args.upscale.split("x")
            post.append(f"scale={uw}:{uh}:flags=lanczos")
        if args.captions and Path(args.captions).exists():
            post.append(f"subtitles={Path(args.captions).as_posix()}")
        vcodec = ["-vf", ",".join(post), "-c:v", "libx264", "-preset", "medium", "-crf", "17"] if post \
            else ["-c:v", "copy"]
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-ss", f"{t_from:.3f}", "-t", f"{t_to - t_from:.3f}", "-i", args.audio,
             "-map", "0:v", "-map", "1:a", *vcodec, "-c:a", "aac", "-b:a", "320k",
             "-t", f"{t_to - t_from:.3f}", str(out)], check=True)
    if post:
        print(f"finishing: {', '.join(p.split('=')[0] for p in post)}")
    print(f"{len(parts)} parts ({used['clip']} clips, {used['still']} stills, {used['black']} black, "
          f"{used['filler']} uncovered ranges filled), "
          f"{t_from:.2f}-{t_to:.2f}s -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", help="shot-list mode: shots/shots.json (recommended)")
    ap.add_argument("--clips-index", default="clips/index.json")
    ap.add_argument("--frames-index", default="shots/frames/index.json")
    ap.add_argument("--filler", default="shots/plates/stage.png",
                    help="still for time no shot covers (intro before bar 1 etc.); black if missing")
    ap.add_argument("--start", type=float, help="shot-list mode: render from this time (s)")
    ap.add_argument("--end", type=float, help="shot-list mode: render up to this time (s)")
    ap.add_argument("--stills", action="store_true",
                    help="shot-list mode: first-frame stills only, ignore clips (animatic preview)")
    ap.add_argument("--edits", help="per-shot edits JSON {sid: {offset: s, trans: flash|dip|fade}}")
    ap.add_argument("--fx", help="music-driven effects JSON {times, pulse, punch, ranges} (scripts/beat_fx.py)")
    ap.add_argument("--captions", help="ASS subtitle file to burn in (scripts/captions.py)")
    ap.add_argument("--grade", choices=sorted(GRADES), help="colour grade preset")
    ap.add_argument("--upscale", help="scale the finished cut, e.g. 1920x1080 (plain lanczos, not AI)")
    ap.add_argument("--beats")
    ap.add_argument("--clips")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", default="output/mv.mp4")
    ap.add_argument("--bars-per-cut", type=int, default=2)
    ap.add_argument("--chorus-bars", type=int, default=1)
    ap.add_argument("--energy-threshold", type=float, default=0.6)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=24)
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found in PATH")
    if args.shots:
        return assemble_shots(args)
    if not (args.beats and args.clips):
        raise SystemExit("legacy mode needs --beats and --clips (or use --shots)")

    beats = json.loads(Path(args.beats).read_text(encoding="utf-8"))
    clips = sorted(p for p in Path(args.clips).iterdir() if p.suffix.lower() in VIDEO_EXT)
    if not clips:
        raise SystemExit(f"no clips in {args.clips}")
    cuts = build_cuts(beats, args.bars_per_cut, args.chorus_bars, args.energy_threshold)
    print(f"{len(cuts)} cuts, {len(clips)} clips")

    W, H, FPS = args.width, args.height, args.fps
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        for n, (start, end) in enumerate(cuts):
            slot = end - start
            clip = clips[n % len(clips)]
            src_dur = probe_duration(clip)
            speed = min(1.0, src_dur / slot)  # <1 means slow down to fill the slot
            vf = (f"setpts=PTS/{speed:.6f},"
                  f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"fps={FPS},format=yuv420p")
            part = tmp / f"part_{n:04d}.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-t", f"{slot:.3f}",
                 "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 str(part)], check=True)
            parts.append(part)

        listfile = tmp / "list.txt"
        listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-i", args.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "320k", "-shortest", str(out)], check=True)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
