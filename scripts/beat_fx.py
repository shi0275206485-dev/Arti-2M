"""Drum hits for the music-driven effects in assemble.py (brightness pulse / punch-in zoom).

Usage:
    python scripts/beat_fx.py [--pulse 0.6] [--punch 0.5] [--where all|chorus|high] [--source kick|beats|downbeats]
        [--out analysis/fx.json]

Hits come from the Demucs drum stem (stems/htdemucs_6s/song/drums.wav, made by analyze_audio.py --stems):
strong low-frequency onsets ~ kick drums. Without the stem it falls back to the beat grid in beats.json.
--where limits the effects to chorus sections or high-energy sections (energy >= 0.6).
"""
import argparse
import json
from pathlib import Path


def kick_times(drums, min_gap=0.18):
    import librosa
    import numpy as np
    y, sr = librosa.load(str(drums), sr=22050, mono=True)
    # low band only (kick), onset envelope -> peaks above the 70th percentile of strength
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low = librosa.amplitude_to_db(S[freqs < 150], ref=np.max)
    env = librosa.onset.onset_strength(S=low, sr=sr, hop_length=512)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=512, backtrack=False)
    if not len(frames):
        return []
    strength = env[frames]
    keep = frames[strength >= np.percentile(strength, 70)]
    out = []
    for t in librosa.frames_to_time(keep, sr=sr, hop_length=512):
        if not out or t - out[-1] >= min_gap:
            out.append(round(float(t), 3))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beats", default="analysis/beats.json")
    ap.add_argument("--drums", default="stems/htdemucs_6s/song/drums.wav")
    ap.add_argument("--source", default="kick", choices=["kick", "beats", "downbeats"])
    ap.add_argument("--pulse", type=float, default=0.6)
    ap.add_argument("--punch", type=float, default=0.5)
    ap.add_argument("--where", default="all", choices=["all", "chorus", "high"])
    ap.add_argument("--out", default="analysis/fx.json")
    args = ap.parse_args()

    beats = json.loads(Path(args.beats).read_text(encoding="utf-8"))
    src = args.source
    times = []
    if src == "kick":
        if Path(args.drums).exists():
            times = kick_times(args.drums)
        if not times:
            print("no drum stem / no kicks found: using the beat grid")
            src = "beats"
    if src in ("beats", "downbeats"):
        times = [round(t, 3) for t in beats[src]]
    ranges = None
    if args.where == "chorus":
        ranges = [[s["start"], s["end"]] for s in beats["sections"]
                  if "chorus" in s["name"].lower().replace("-", "") and "pre" not in s["name"].lower()]
    elif args.where == "high":
        ranges = [[s["start"], s["end"]] for s in beats["sections"] if s.get("mean_energy", 0) >= 0.6]
    fx = {"times": times, "pulse": args.pulse, "punch": args.punch, "ranges": ranges, "source": src}
    Path(args.out).write_text(json.dumps(fx), encoding="utf-8")
    n = sum(1 for t in times if not ranges or any(a <= t < b for a, b in ranges))
    print(f"fx: {len(times)} {src} hits ({n} inside the chosen sections), pulse {args.pulse}, punch {args.punch} "
          f"-> {args.out}")


if __name__ == "__main__":
    main()
