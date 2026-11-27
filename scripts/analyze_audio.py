"""Analyze a song: tempo, beats, downbeats, bars, sections, per-beat energy.

Usage:
    python scripts/analyze_audio.py audio/song.wav [--score analysis/score.abc] [--stems]

With a YuE2 score (default: analysis/score.abc if present), the song structure
(bars, sections, chords, vocal bars) comes from the score and is aligned onto the
audio: the first sounding note anchors the grid, then the beat period and phase are
fitted by a beat-grid search on the onset envelope. Lyrics (from analysis/song_source.json or
--lyrics-file) are attached to sections by tag name.
Without a score it falls back to audio-only segmentation (--no-score forces this).

Writes analysis/beats.json (and stems/ via Demucs if --stems).
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from abc_score import attach_lyrics, parse_score  # noqa: E402

SR = 22050


# ----------------------------------------------------------------- audio features
def audio_features(path, start_bpm=None):
    y, sr = librosa.load(path, sr=SR, mono=True)
    duration = len(y) / sr
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    kw = {"start_bpm": start_bpm} if start_bpm else {}
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, **kw)
    rms = librosa.feature.rms(y=y)[0]
    rms_t = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    audible = rms_t[rms > rms.max() * 0.02]
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="time", backtrack=True)
    return {
        "y": y, "sr": sr, "duration": duration, "onset_env": onset_env,
        "tempo": float(np.atleast_1d(tempo)[0]),
        "beat_frames": beat_frames,
        "beat_times": librosa.frames_to_time(beat_frames, sr=sr),
        "rms": rms, "rms_t": rms_t,
        "audible": (float(audible[0]), float(audible[-1])) if len(audible) else (0.0, duration),
        "first_onset": float(onsets[0]) if len(onsets) else 0.0,
    }


def energy_at(feat, times):
    """Normalized 0..1 RMS energy averaged over each [t_i, t_{i+1}) span."""
    rms, rt = feat["rms"], feat["rms_t"]
    edges = list(times) + [feat["duration"]]
    vals = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (rt >= a) & (rt < b)
        vals.append(float(rms[m].mean()) if m.any() else 0.0)
    v = np.array(vals)
    return (v - v.min()) / (np.ptp(v) + 1e-9) if len(v) else v


# ------------------------------------------------------------ score-driven path
def grid_search(y, sr, p0, span=0.04, hop=128):
    """Find the steady beat grid (period, phase) whose points carry the most onset strength.

    More robust than librosa's beat tracker on breakbeat/DnB drums, and not limited by
    the tracker's frame quantization. Searches tempo within +-span of the score tempo.
    """
    oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    ft = np.arange(len(oe)) * hop / sr
    end = ft[-1]

    def score_at(p, phases):
        return np.array([np.interp(np.arange(o, end, p), ft, oe).mean() for o in phases])

    def search(periods, n_ph):
        best = (-1.0, p0, 0.0, 1.0)
        for p in periods:
            ph = np.linspace(0, p, n_ph, endpoint=False)
            sc = score_at(p, ph)
            i = int(np.argmax(sc))
            if sc[i] > best[0]:
                best = (float(sc[i]), float(p), float(ph[i]), float(sc[i] / (sc.mean() + 1e-9)))
        return best

    bpm0 = 60.0 / p0
    coarse = search(60.0 / np.arange(bpm0 * (1 - span), bpm0 * (1 + span), 0.1), 48)
    b = 60.0 / coarse[1]
    fine = search(60.0 / np.arange(b - 0.12, b + 0.12, 0.01), 96)
    return fine[1], fine[2], fine[3]


def align_score(score, feat, warnings):
    """Return (t0, period, diagnostics): audio_time(beat) = t0 + beat * period."""
    p0 = 60.0 / score["tempo_bpm"]
    anchor = score["first_onset_beat"] or 0.0
    first = feat["first_onset"]

    p, phase, contrast = grid_search(feat["y"], feat["sr"], p0)
    # pick the grid line that best matches "score beat `anchor` sounds at the first onset"
    t0 = phase + np.round((first - anchor * p - phase) / p) * p
    diag = {"score_period": round(p0, 4), "period": round(p, 4), "anchor_beat": anchor,
            "first_onset": round(first, 3), "grid_contrast": round(contrast, 2),
            "anchor_offset_beats": round((first - anchor * p - t0) / p, 3)}
    if abs(p / p0 - 1) > 0.01:
        warnings.append(f"audio tempo {60 / p:.1f} BPM differs from score Q {60 / p0:.1f} BPM; using audio tempo")
    if contrast < 1.3:
        warnings.append(f"weak beat grid (contrast {contrast:.2f}); check alignment by ear")
    if abs(diag["anchor_offset_beats"]) > 0.3:
        warnings.append("first note falls between grid beats; bar phase may be off by one beat")

    # cross-check against librosa's tracked beats (informational)
    bt = feat["beat_times"]
    if len(bt):
        res = bt - (t0 + np.round((bt - t0) / p) * p)
        keep = np.abs(res) < 0.25 * p
        diag.update({"tracked_beats": int(len(bt)), "matched_beats": int(keep.sum()),
                     "fit_residual_ms": round(float(np.sqrt(np.mean(res[keep] ** 2))) * 1000, 1)
                     if keep.any() else None})
    if score["last_end_beat"] is not None:
        predicted_end = t0 + score["last_end_beat"] * p
        diag["end_check_s"] = round(feat["audible"][1] - predicted_end, 3)
        # a reverb/fade tail after the last note is normal; ending early or a very long
        # tail suggests the audio doesn't follow the score
        if diag["end_check_s"] < -2 * p or diag["end_check_s"] > max(4.0, 8 * p):
            warnings.append(f"last note predicted at {predicted_end:.2f}s but audio ends "
                            f"{feat['audible'][1]:.2f}s; alignment may drift")
    diag["t0"] = round(float(t0), 4)
    return float(t0), float(p), diag


def load_align_fix(args):
    """analysis/align_fix.json {"score_sha256", "bar_shift"}: the audio doesn't follow the score's length
    (e.g. YuE2 rendered the intro 8 bars shorter than it wrote), found from the sung lyrics by
    lyrics_align.py. Every score bar moves by bar_shift bars (negative = earlier)."""
    path = Path(args.score).with_name("align_fix.json")
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("score_sha256") != hashlib.sha256(Path(args.score).read_bytes()).hexdigest():
        return 0
    return int(data.get("bar_shift") or 0)


def analyze_with_score(args, score, warnings):
    feat = audio_features(args.audio, start_bpm=score["tempo_bpm"])
    dur = feat["duration"]
    t0, p, diag = align_score(score, feat, warnings)
    bpb = score["beats_per_bar"]
    bar_len = bpb * p
    shift = load_align_fix(args)
    if shift:
        t0 += shift * bar_len
        diag["bar_shift"] = shift
        diag["t0"] = round(t0, 4)
        if "end_check_s" in diag:
            diag["end_check_s"] = round(diag["end_check_s"] - shift * bar_len, 3)
        warnings[:] = [w for w in warnings if not w.startswith("last note predicted")]
        warnings.append(f"score moved {shift:+d} bars to match the sung lyrics (analysis/align_fix.json)")
    elif "end_check_s" in diag and abs(diag["end_check_s"]) > 1.5 * bar_len:
        n = diag["end_check_s"] / bar_len
        if abs(n - round(n)) < 0.15:
            warnings.append(f"audio is {round(n):+d} whole bars off the score's length: YuE2 probably "
                            f"skipped or added bars; lyrics_align.py can find where")

    beats, downbeats, bars = [], [], []
    n_beats_total = int(round(score["n_bars"] * bpb))
    for i in range(n_beats_total + 1):
        t = t0 + i * p
        if 0 <= t < dur:
            beats.append(t)
    for b in score["bars"]:
        start, end = t0 + b["index"] * bar_len, t0 + (b["index"] + 1) * bar_len
        if end <= 0 or start >= dur:
            continue
        if start >= 0:
            downbeats.append(start)
        bars.append({**b, "start": max(0.0, start), "end": min(dur, end)})

    beat_energy = energy_at(feat, beats)
    bar_energy = energy_at(feat, [b["start"] for b in bars])
    for b, e in zip(bars, bar_energy):
        b["energy"] = round(float(e), 3)

    src_sections = load_structure(args, score, warnings) or score["sections"]
    sections = []
    for s in src_sections:
        sb = [b for b in bars if s["start_bar"] <= b["index"] < s["start_bar"] + s["n_bars"]]
        if not sb:
            continue
        for b in sb:
            b["section"] = s["name"]
        sec = {
            "index": len(sections), "name": s["name"],
            "start": sb[0]["start"], "end": sb[-1]["end"],
            "start_bar": s["start_bar"], "n_bars": s["n_bars"],
            "vocal_bars": sum(b["vocal"] for b in sb),
            "mean_energy": round(float(np.mean([b["energy"] for b in sb])), 3),
        }
        for k in ("delivery", "note"):
            if s.get(k):
                sec[k] = s[k]
        sections.append(sec)
    if sections:
        sections[0]["start"] = 0.0
        sections[-1]["end"] = dur
    lyrics = load_lyrics(args)
    if lyrics:
        attach_lyrics(sections, lyrics)

    for b in bars:
        b["section_index"] = next((s["index"] for s in sections
                                   if s["start_bar"] <= b["index"] < s["start_bar"] + s["n_bars"]), None)
    return {
        "audio": str(args.audio), "duration": dur, "source": "score+audio",
        "score": str(args.score),
        "tempo_bpm": 60.0 / p, "score_tempo_bpm": score["tempo_bpm"],
        "meter": score["meter"], "beats_per_bar": bpb,
        "beats": beats, "downbeats": downbeats,
        "beat_energy": [float(e) for e in beat_energy],
        "sections": sections, "bars": bars,
        "alignment": diag,
    }


def load_structure(args, score, warnings):
    """Optional manual section override: when the score's section comments are wrong
    (e.g. pre-chorus merged into verse, or the audio doesn't follow the score).

    analysis/structure.json:
      {"score_sha": "...optional...", "sections": [
         {"name": "verse", "start_bar": 9, "n_bars": 8, "delivery": "rap", "note": "..."}, ...]}
    Sections must be contiguous and cover every score bar.
    """
    path = Path(args.structure) if args.structure else Path(args.score).with_name("structure.json")
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sha = hashlib.sha256(Path(args.score).read_bytes()).hexdigest()
    if data.get("score_sha256") and data["score_sha256"] != sha:
        warnings.append(f"{path} was written for a different score; ignored")
        return None
    secs = sorted(data["sections"], key=lambda s: s["start_bar"])
    pos = 0
    for s in secs:
        if s["start_bar"] != pos:
            raise SystemExit(f"{path}: sections must be contiguous; expected start_bar {pos}, got {s}")
        pos += s["n_bars"]
    if pos != score["n_bars"]:
        raise SystemExit(f"{path}: sections cover {pos} bars but the score has {score['n_bars']}")
    warnings.append(f"section names overridden by {path}")
    return secs


def load_lyrics(args):
    if args.lyrics_file:
        return Path(args.lyrics_file).read_text(encoding="utf-8")
    src = Path(args.score).with_name("song_source.json")
    if src.exists():
        return json.loads(src.read_text(encoding="utf-8")).get("request", {}).get("lyrics")
    return None


# ------------------------------------------------------------- audio-only path
def detect_sections(y, sr, beat_frames, n_sections):
    """Segment the song into structural sections using beat-synced chroma+MFCC."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    feats = np.vstack([librosa.util.normalize(chroma, axis=1),
                       librosa.util.normalize(mfcc, axis=1)])
    synced = librosa.util.sync(feats, beat_frames, aggregate=np.median)
    k = max(2, min(n_sections, synced.shape[1] - 1))
    bounds = librosa.segment.agglomerative(synced, k)
    bound_frames = librosa.util.fix_frames(beat_frames[bounds[bounds < len(beat_frames)]], x_min=0)
    times = librosa.frames_to_time(bound_frames, sr=sr)
    return sorted(set(float(round(t, 3)) for t in times))


def analyze_audio_only(args):
    feat = audio_features(args.audio)
    y, sr, dur = feat["y"], feat["sr"], feat["duration"]
    beat_frames, beat_times = feat["beat_frames"], feat["beat_times"]
    bpb = args.beats_per_bar
    strengths = feat["onset_env"][np.clip(beat_frames, 0, len(feat["onset_env"]) - 1)]
    phase = int(np.argmax([strengths[q::bpb].mean() if len(strengths[q::bpb]) else 0
                           for q in range(bpb)]))
    downbeats = beat_times[phase::bpb]
    energy = energy_at(feat, beat_times)

    bounds = detect_sections(y, sr, beat_frames, args.sections)
    if not bounds or bounds[0] > 0.01:
        bounds = [0.0] + bounds
    sections = []
    for i, start in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else dur
        mask = (beat_times >= start) & (beat_times < end)
        sections.append({"index": i, "name": f"section{i}", "start": start, "end": float(end),
                         "mean_energy": round(float(energy[mask].mean()) if mask.any() else 0.0, 3)})
    return {
        "audio": str(args.audio), "duration": dur, "source": "audio",
        "tempo_bpm": feat["tempo"], "beats_per_bar": bpb,
        "beats": [float(t) for t in beat_times], "downbeats": [float(t) for t in downbeats],
        "beat_energy": [float(e) for e in energy], "sections": sections,
    }


# ----------------------------------------------------------------------- main
def rounded(o):
    if isinstance(o, float):
        return round(o, 3)
    if isinstance(o, dict):
        return {k: rounded(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rounded(v) for v in o]
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("--out", default="analysis/beats.json")
    ap.add_argument("--score", default="analysis/score.abc", help="YuE2 score.abc (used if it exists)")
    ap.add_argument("--no-score", action="store_true", help="ignore the score; audio-only analysis")
    ap.add_argument("--structure", help="section override JSON (default: structure.json next to the score)")
    ap.add_argument("--lyrics-file", help="lyrics with [Verse]/[Chorus] tags (default: analysis/song_source.json)")
    ap.add_argument("--stems", action="store_true", help="run Demucs stem separation")
    ap.add_argument("--sections", type=int, default=8, help="audio-only: number of sections")
    ap.add_argument("--beats-per-bar", type=int, default=4, help="audio-only: beats per bar")
    args = ap.parse_args()

    warnings = []
    use_score = not args.no_score and Path(args.score).exists()
    if use_score:
        score = parse_score(Path(args.score).read_text(encoding="utf-8"))
        warnings += score["warnings"]
        if not score["n_bars"] or score["first_onset_beat"] is None:
            warnings.append("score has no notes; falling back to audio-only analysis")
            use_score = False
    result = analyze_with_score(args, score, warnings) if use_score else analyze_audio_only(args)
    result["warnings"] = warnings

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rounded(result), indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[{result['source']}] tempo {result['tempo_bpm']:.1f} BPM, {len(result['beats'])} beats, "
          f"{len(result['downbeats'])} downbeats, {len(result['sections'])} sections -> {out}")
    if "alignment" in result:
        a = result["alignment"]
        print(f"  alignment: t0 {a['t0']:+.3f}s, period {a['period']:.4f}s, "
              f"{a.get('matched_beats', '?')}/{a.get('tracked_beats', '?')} tracked beats matched, "
              f"rms residual {a.get('fit_residual_ms', '?')} ms, end check {a.get('end_check_s', '?')} s")
    for s in result["sections"]:
        extra = f" bars {s['start_bar']}-{s['start_bar'] + s['n_bars'] - 1}" if "start_bar" in s else ""
        lyr = f" | {s['lyrics'][0]} ..." if s.get("lyrics") else ""
        print(f"  {s['name']:<10} {s['start']:7.2f} - {s['end']:7.2f}s{extra} "
              f"energy {s['mean_energy']:.2f}{lyr}")
    for w in warnings:
        print(f"  WARNING: {w}", file=sys.stderr)

    if args.stems:
        cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs_6s", "-o", "stems", args.audio]
        print("running:", " ".join(cmd))
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
