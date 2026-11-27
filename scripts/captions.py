"""Karaoke lyric captions (ASS) for the finished cut; assemble.py --captions burns them in.

Usage:
    python scripts/captions.py [--style classic|bold|minimal] [--width 1280 --height 720]
        [--start 0 --end 44.6] [--out output/captions.ass]

With analysis/lyrics_timing.json (scripts/lyrics_align.py: Whisper on the vocal stem matched to the written
lyrics) each line is shown when it is actually sung, repeats included, and every word lights up (\\kf) at its
sung time. Without it, lines are spread over a section's vocal bars (the same as the shot list) and words (CJK:
characters) light up evenly over the line.
"""
import argparse
import json
import re
from pathlib import Path

from build_shots import bar_lyrics, load_timing

# name: (font size as a share of the short side, alignment, margin_v share, bold, primary (sung), secondary (to sing),
#        karaoke)
STYLES = {
    "classic": (0.055, 2, 0.07, 0, "&H00E7D636", "&H00FFFFFF", True),   # cyan fill over white, bottom centre
    "bold": (0.085, 2, 0.16, 1, "&H0000D7FF", "&H00FFFFFF", True),      # big gold fill, lower third
    "minimal": (0.040, 1, 0.05, 0, "&H00FFFFFF", "&H00FFFFFF", False),  # small, bottom left, no highlight
}


def ts(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def tokens(line):
    """Words for Latin text, single characters for CJK (each gets its own karaoke step)."""
    out = []
    for w in line.split():
        if re.search(r"[぀-ヿ㐀-鿿가-힯]", w):
            out += list(w)
        else:
            out.append(w + " ")
    return out


def lines_with_times(beats):
    lyr = bar_lyrics(beats)
    bars = {b["index"]: b for b in beats["bars"]}
    out = []
    for i in sorted(lyr):
        line = re.sub(r"\s+", " ", lyr[i]).strip()
        if not line:
            continue
        if out and out[-1]["text"] == line and out[-1]["last"] == i - 1:
            out[-1]["end"], out[-1]["last"] = bars[i]["end"], i
        else:
            out.append({"text": line, "start": bars[i]["start"], "end": bars[i]["end"], "last": i})
    return out


def timed_events(timing, cut0, cut1, karaoke):
    """One caption per sung line: up a moment before the first word, held a little after the last (until the
    next line), each word's highlight running over its own sung time."""
    out = []
    timing = sorted(timing, key=lambda x: x["start"])
    for n, ln in enumerate(timing):
        nxt = timing[n + 1]["start"] if n + 1 < len(timing) else ln["end"] + 2.0
        show0 = ln["start"] - 0.3
        show1 = min(ln["end"] + 0.8, nxt - 0.3)          # gone when the next line comes up: never two at once
        show1 = max(show1, min(ln["end"], nxt - 0.3), show0 + 0.3)
        a, b = max(show0, cut0), min(show1, cut1)
        if b - a < 0.3:
            continue
        words = ln["words"] or [[ln["text"], ln["start"], ln["end"]]]
        if karaoke:
            parts, t = [], a
            for i, (w, ws, we) in enumerate(words):
                w = w.replace("{", "(").replace("}", ")") + ("" if i == len(words) - 1 else " ")
                if we <= a:                      # already sung before the cut starts
                    parts.append(f"{{\\k0}}{w}")
                    continue
                gap = max(0.0, ws - t)
                if gap >= 0.01:
                    parts.append(f"{{\\k{round(gap * 100)}}}")
                dur = max(0.05, we - max(ws, t))
                parts.append(f"{{\\kf{round(dur * 100)}}}{w}")
                t = max(ws, t) + dur
            text = "".join(parts)
        else:
            text = ln["text"].replace("{", "(").replace("}", ")")
        out.append(f"Dialogue: 0,{ts(a - cut0)},{ts(b - cut0)},Lyric,,0,0,0,,{{\\fad(120,120)}}{text.strip()}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beats", default="analysis/beats.json")
    ap.add_argument("--style", default="classic", choices=sorted(STYLES))
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--start", type=float, default=0.0, help="start of the cut in song time (s)")
    ap.add_argument("--end", type=float, help="end of the cut in song time (s)")
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--out", default="output/captions.ass")
    args = ap.parse_args()

    beats = json.loads(Path(args.beats).read_text(encoding="utf-8"))
    size, align, mv, bold, primary, secondary, karaoke = STYLES[args.style]
    short = min(args.width, args.height)
    end = args.end if args.end is not None else beats["duration"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {args.width}
PlayResY: {args.height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,{args.font},{round(short * size)},{primary},{secondary},&H00000000,&H80000000,{bold},0,0,0,100,100,0,0,1,{max(2, round(short * 0.004))},{1 if args.style == "minimal" else 0},{align},{round(args.width * 0.06)},{round(args.width * 0.06)},{round(args.height * mv)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    timing = load_timing(args.beats)
    if timing:
        events = timed_events(timing, args.start, end, karaoke)
    for ln in ([] if timing else lines_with_times(beats)):
        a, b = max(ln["start"], args.start), min(ln["end"], end)
        if b - a < 0.3:
            continue
        text = ln["text"].replace("{", "(").replace("}", ")")
        if karaoke:
            toks = tokens(text)
            sung = (ln["end"] - ln["start"]) * 0.85   # the line is usually sung before the bar ends
            cs = max(1, round(sung * 100 / max(1, len(toks))))
            done = min(len(toks), int((a - ln["start"]) * 100 // cs))   # cut starts mid-line: already sung
            text = "".join(f"{{\\k0}}{t}" for t in toks[:done]) + "".join(f"{{\\kf{cs}}}{t}" for t in toks[done:])
        events.append(f"Dialogue: 0,{ts(a - args.start)},{ts(b - args.start)},Lyric,,0,0,0,,"
                      f"{{\\fad(120,120)}}{text.strip()}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(head + "\n".join(events) + "\n", encoding="utf-8-sig")
    print(f"captions: {len(events)} lines, style {args.style} -> {args.out}")


if __name__ == "__main__":
    main()
