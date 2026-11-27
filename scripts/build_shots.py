"""Turn shots/shot_design.py (creative intent per bar range) into shots/shots.json.

Usage:
    python scripts/build_shots.py [--design shots/shot_design.py] [--beats analysis/beats.json]

Times come from the bar grid in beats.json; lyrics follow the sung timing (analysis/lyrics_timing.json from
lyrics_align.py) when present, else are spread evenly over the vocal bars of each section. Each shot records how its first frame is made (t2i / edit1 / edit2,
with member reference images) and how it is animated (lipsync -> audio-driven model,
otherwise image-to-video). Checks that shots tile the song bar-by-bar with no gaps.
"""
import argparse
import importlib.util
import json
from pathlib import Path

HANDLE = 0.3   # extra seconds generated past the cut, for trimming freedom


def load_design(path):
    spec = importlib.util.spec_from_file_location("design", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return (mod.DESIGN, getattr(mod, "LOCATIONS", {}), getattr(mod, "LOCATION_BY_BAR", {}),
            getattr(mod, "ECHO_CAPTIVE_UNTIL", None))


def load_timing(beats_path):
    """Sung lines from lyrics_align.py (analysis/lyrics_timing.json next to beats.json), or None."""
    p = Path(beats_path).with_name("lyrics_timing.json")
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("lines") or None


def bar_lyrics(beats, timing=None):
    """bar index -> lyric line. With sung timing: the line sung most in that bar (repeats included, nothing in
    silent bars); without: each section's lines spread evenly over its vocal bars."""
    out = {}
    if timing:
        for b in beats["bars"]:
            best, most = None, 0.25 * (b["end"] - b["start"])
            for ln in timing:
                ov = min(b["end"], ln["end"]) - max(b["start"], ln["start"])
                if ov > most:
                    best, most = ln["text"], ov
            if best:
                out[b["index"]] = best
        return out
    for s in beats["sections"]:
        lines = s.get("lyrics") or []
        bars = [b for b in beats["bars"] if b.get("section_index") == s["index"]]
        vbars = [b for b in bars if b["vocal"]] or bars
        if not lines:
            continue
        per = len(vbars) / len(lines)
        for i, b in enumerate(vbars):
            out[b["index"]] = lines[min(int(i / per), len(lines) - 1)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--design", default="shots/shot_design.py")
    ap.add_argument("--beats", default="analysis/beats.json")
    ap.add_argument("--members", default="shots/members.json")
    ap.add_argument("--out", default="shots/shots.json")
    ap.add_argument("--plates", default="shots/plates")
    ap.add_argument("--bars", help="first-last bar the design covers (default: the whole song), e.g. 24-40")
    args = ap.parse_args()

    design, locations, loc_by_bar, captive_until = load_design(args.design)
    plates = Path(args.plates)
    plates.mkdir(parents=True, exist_ok=True)
    (plates / "locations.json").write_text(json.dumps(locations, indent=1, ensure_ascii=False), encoding="utf-8")
    beats = json.loads(Path(args.beats).read_text(encoding="utf-8"))
    members = json.loads(Path(args.members).read_text(encoding="utf-8"))["members"]
    bars = {b["index"]: b for b in beats["bars"]}
    lyr = bar_lyrics(beats, load_timing(args.beats))

    rows = []
    for key, val in design.items():
        groups = val if val and isinstance(val[0], list) else [val]
        for g in groups:
            rows += g
    rows.sort(key=lambda r: r[0])

    # coverage check: every bar (of the chosen range) exactly once
    covered = [i for r in rows for i in range(r[0], r[1] + 1)]
    want = set(bars)
    if args.bars:
        a, b = (int(x) for x in args.bars.split("-"))
        want = {i for i in bars if a <= i <= b}
    missing = sorted(want - set(covered))
    dup = sorted({i for i in covered if covered.count(i) > 1})
    if missing or dup:
        raise SystemExit(f"bar coverage problem: missing {missing}, duplicated {dup}")

    shots = []
    for n, (b0, b1, mem, lip, size, frame, motion) in enumerate(rows, 1):
        start, end = bars[b0]["start"], bars[b1]["end"]
        sec = beats["sections"][bars[b0]["section_index"]]
        refs = [members[m]["reference_image"] for m in mem]
        tag = {m: f"the {members[m].get('noun', 'woman')} from image {i + 1}" for i, m in enumerate(mem)}
        loc = loc_by_bar.get(b0)
        frame_prompt = frame.format(**tag) if mem else frame
        if captive_until is not None and "ECHO" in mem and b0 < captive_until and loc == "hall":
            # story state: before the capsule shatters ECHO must read as trapped, never outside it
            frame_prompt += (f". {tag['ECHO']} is fully enclosed inside the sealed, intact glass capsule, "
                             f"seen from outside through the glass, never standing outside it")
            if "NOVA" in mem:
                frame_prompt += f", while {tag['NOVA']} stands outside the capsule, never inside it"
        if loc:
            refs.append((plates / f"{loc}.png").as_posix())
            k = len(refs)
            # the plate fixes WHERE we are, not the framing: shot size comes from the shot itself
            frame_prompt = (f"{size[0].upper() + size[1:]} shot. {frame_prompt}. Use the location shown in image {k} "
                            f"as the background, with the same architecture, lighting and colors, "
                            f"framed as a {size} shot")
        lines = []
        for i in range(b0, b1 + 1):
            if i in lyr and (not lines or lines[-1] != lyr[i]):
                lines.append(lyr[i])
        shots.append({
            "id": f"s{n:03d}",
            "section": sec["name"], "delivery": sec.get("delivery", ""),
            "bars": [b0, b1], "start": round(start, 3), "end": round(end, 3),
            "seconds": round(end - start, 3), "gen_seconds": round(end - start + HANDLE, 2),
            "lyrics": lines, "members": list(mem), "lipsync": lip, "shot": size,
            "location": loc,
            "frame": {"mode": f"edit{len(refs)}" if refs else "t2i", "refs": refs, "prompt": frame_prompt},
            "video": {"mode": "lipsync" if lip else "i2v", "prompt": motion},
        })

    Path(args.out).write_text(json.dumps(shots, indent=1, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    c = Counter(s["frame"]["mode"] for s in shots)
    v = Counter(s["video"]["mode"] for s in shots)
    total = sum(s["seconds"] for s in shots)
    print(f"{len(shots)} shots covering {total:.1f}s; frames {dict(c)}; video {dict(v)} -> {args.out}")
    for s in shots:
        if s["lipsync"] and s["lipsync"] not in s["members"]:
            raise SystemExit(f"{s['id']}: lipsync member {s['lipsync']} not in shot")


if __name__ == "__main__":
    main()
