"""Find when each lyric line is actually sung: Whisper on the Demucs vocal stem, matched to the written lyrics.

Usage:
    python scripts/lyrics_align.py [--beats analysis/beats.json] [--vocals stems/htdemucs_6s/song/vocals.wav]
        [--write-fix] [--model openai/whisper-large-v3-turbo]

Writes analysis/lyrics_timing.json:
    {"lines": [{"line": k, "section_index": i, "text": "...", "start": s, "end": e,
                "words": [[word, start, end], ...]}, ...],      # in sung order; a repeated line appears again
     "offsets": [{"section_index", "name", "predicted", "sung", "bars"}], "bar_shift": n, ...}

Generated songs don't always follow their lyrics sheet: lines get repeated ("Fate wakes up in my hands" x3),
skipped, and YuE2 can render a different number of bars than its own score says (seen: an intro 8 bars short,
which put every section of the analysis 13.7 s late). If most sections are sung the same whole number of bars
away from where beats.json puts them, that number is reported as bar_shift; --write-fix stores it in
analysis/align_fix.json so analyze_audio.py moves the score grid.

The Whisper words are cached in analysis/asr_words.json (keyed by the vocal file's size/mtime); runs on CPU
(~2.5 min for a 3.7 min song) so the GPU stays free.
"""
import argparse
import hashlib
import json
import re
import statistics
from difflib import SequenceMatcher
from pathlib import Path

MODEL = "openai/whisper-large-v3-turbo"


def norm(w):
    return re.sub(r"[^\w']+", "", w.lower().replace("’", "'"))


def transcribe(vocals, model, cache):
    st = vocals.stat()
    key = f"{st.st_size}:{int(st.st_mtime)}:{model}"
    if cache.exists():
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("key") == key:
            return c["words"]
    import librosa
    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model=model, device="cpu")
    y, _ = librosa.load(str(vocals), sr=16000)
    # sequential long-form decoding: chunk_length_s snaps word times to the chunk edges
    r = asr(y.copy(), return_timestamps="word",
            generate_kwargs={"language": "en", "task": "transcribe", "condition_on_prev_tokens": False,
                             "no_speech_threshold": 0.6, "logprob_threshold": -1.0,
                             "compression_ratio_threshold": 1.35, "temperature": (0.0, 0.2, 0.4)})
    words = [[c["text"].strip(), c["timestamp"][0], c["timestamp"][1] or c["timestamp"][0]]
             for c in r["chunks"] if c["timestamp"][0] is not None and norm(c["text"])]
    cache.write_text(json.dumps({"key": key, "words": words}), encoding="utf-8")
    return words


def written_lines(beats):
    out = []
    for s in beats["sections"]:
        for t in s.get("lyrics") or []:
            toks = [norm(w) for w in t.split() if norm(w)]
            if toks:
                out.append({"line": len(out), "section_index": s["index"], "text": t.strip(), "toks": toks})
    return out


def match(words, lines):
    """Greedy walk over the sung words: at each word take the written line (near the expected one, allowing a
    repeat of the previous lines or a skip ahead) that best matches the next few words."""
    toks = [norm(w[0]) for w in words]
    out, i, k = [], 0, 0
    while i < len(toks) and k <= len(lines):
        best = None
        for j in range(max(0, k - 2), min(len(lines), k + 5)):
            n = len(lines[j]["toks"])
            for m in range(max(1, n - 2), n + 3):
                if i + m > len(toks):
                    break
                r = SequenceMatcher(None, lines[j]["toks"], toks[i:i + m], autojunk=False).ratio()
                r += 0.04 if j == k else 0.0          # prefer the expected next line on near ties
                if best is None or r > best[0]:
                    best = (r, j, m)
        # the expected next line may be misheard more ("The fog pulls back" -> "The fall falls back")
        if best and (best[0] >= 0.6 or (best[1] == k and best[0] >= 0.54)):
            _, j, m = best
            out.append(place(lines[j], words[i:i + m]))
            i, k = i + m, j + 1
        else:
            i += 1
    return out


def place(line, sung):
    """Time every written word from the sung words it lines up with; the rest are interpolated."""
    st = [norm(w[0]) for w in sung]
    times = [None] * len(line["toks"])
    for op, a1, a2, b1, b2 in SequenceMatcher(None, line["toks"], st, autojunk=False).get_opcodes():
        if op in ("equal", "replace"):
            for x in range(a2 - a1):
                y = b1 + min(x * (b2 - b1) // max(1, a2 - a1), b2 - b1 - 1) if b2 > b1 else None
                if y is not None:
                    times[a1 + x] = (sung[y][1], sung[y][2])
    s0, e0 = sung[0][1], sung[-1][2]
    known = [i for i, t in enumerate(times) if t]
    for i, t in enumerate(times):
        if t is None:
            prev = max((x for x in known if x < i), default=None)
            nxt = min((x for x in known if x > i), default=None)
            a = times[prev][1] if prev is not None else s0
            b = times[nxt][0] if nxt is not None else e0
            times[i] = (a, max(a, b))
    words = [w for w in line["text"].split() if norm(w)]
    return {"line": line["line"], "section_index": line["section_index"], "text": line["text"],
            "start": round(s0, 2), "end": round(e0, 2),
            "words": [[w, round(a, 2), round(b, 2)] for w, (a, b) in zip(words, times)]}


def offsets(beats, sung):
    bar_len = beats["beats_per_bar"] * 60.0 / beats["tempo_bpm"]
    out = []
    for s in beats["sections"]:
        first = next((x for x in sung if x["section_index"] == s["index"]), None)
        if not first or not s.get("lyrics"):
            continue
        sb = [b for b in beats["bars"] if b.get("section_index") == s["index"]]
        vb = [b for b in sb if b["vocal"]] or sb
        if not vb:
            continue
        pred = vb[0]["start"]
        out.append({"section_index": s["index"], "name": s["name"], "predicted": round(pred, 2),
                    "sung": first["start"], "bars": round((first["start"] - pred) / bar_len, 2)})
    return out, bar_len


def bar_shift(beats, offs, bar_len):
    """A whole-bar shift most sections agree on (lines often start a beat or two before the bar: pickups)."""
    if len(offs) < 2:
        return 0
    med = statistics.median(o["bars"] for o in offs)
    end = beats.get("alignment", {}).get("end_check_s")
    n = round(med)
    if end is not None and abs(end / bar_len - round(end / bar_len)) < 0.15 and abs(end / bar_len - med) < 1.0:
        n = round(end / bar_len)        # the audio's length says exactly how many bars are missing
    if abs(n) < 1:
        return 0
    agree = sum(abs(o["bars"] - n) <= 1.0 for o in offs)
    return n if agree >= 0.7 * len(offs) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beats", default="analysis/beats.json")
    ap.add_argument("--vocals", default="stems/htdemucs_6s/song/vocals.wav")
    ap.add_argument("--out", default="analysis/lyrics_timing.json")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--write-fix", action="store_true", help="store a detected bar shift in analysis/align_fix.json")
    args = ap.parse_args()

    beats = json.loads(Path(args.beats).read_text(encoding="utf-8"))
    vocals = Path(args.vocals)
    if not vocals.exists():
        raise SystemExit(f"no vocal stem at {vocals}; run analyze_audio.py --stems first")
    lines = written_lines(beats)
    if not lines:
        raise SystemExit("no lyrics in beats.json")
    words = transcribe(vocals, args.model, Path(args.out).with_name("asr_words.json"))
    words = [w for w in words if norm(w[0])]
    sung = match(words, lines)
    offs, bar_len = offsets(beats, sung)
    shift = bar_shift(beats, offs, bar_len)
    if beats.get("alignment", {}).get("bar_shift"):
        shift = 0      # beats.json is already corrected; offsets are relative to the corrected grid
    covered = len({x["line"] for x in sung})
    res = {"model": args.model, "lines": sung, "offsets": offs, "bar_shift": shift,
           "written_lines": len(lines), "matched_lines": covered, "sung_lines": len(sung)}
    Path(args.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"lyrics: {len(sung)} sung lines matched ({covered}/{len(lines)} written lines) -> {args.out}")
    for o in offs:
        print(f"  {o['name']:<11} predicted {o['predicted']:7.2f}s  sung {o['sung']:7.2f}s  ({o['bars']:+.2f} bars)")
    if shift:
        print(f"  the audio is {shift:+d} bars off the score grid")
        if args.write_fix:
            score = Path(args.beats).with_name("score.abc")
            if not score.exists():
                print("  no score.abc: nothing to fix")
            else:
                fix = Path(args.beats).with_name("align_fix.json")
                fix.write_text(json.dumps({"score_sha256": hashlib.sha256(score.read_bytes()).hexdigest(),
                                           "bar_shift": shift}, indent=1), encoding="utf-8")
                print(f"  wrote {fix}; re-run analyze_audio.py")


if __name__ == "__main__":
    main()
