"""Estimate how many distinct singers a song has and who sings which bars.

Uses the singer-identity embeddings of Torres et al. (ISMIR 2023,
github.com/SonyCSLParis/ssl-singer-identity; weights: HF BernardoTorres/singer-identity,
MIT), loaded as TorchScript so only torch + huggingface_hub are needed.

Usage:
    python scripts/singer_id.py [--vocals stems/htdemucs/song/vocals.wav]
        [--beats analysis/beats.json] [--bars-per-window 2] [--k N] [--out analysis/voices.json]

Run Demucs first (vocals stem). Windows follow the bar grid in beats.json and never
cross a section boundary. Output: per-window voice labels, per-section summary,
similarity stats. Treat the result as a proposal to confirm by ear: unison/harmony
choruses blend voices, and the model was trained on human singing, not AI vocals.
"""
import argparse
import json
from pathlib import Path

import librosa
import numpy as np
import torch

HF_REPO = "BernardoTorres/singer-identity"
SR = 44100


def load_models(names):
    from huggingface_hub import hf_hub_download
    models = {}
    for n in names:
        path = hf_hub_download(HF_REPO, f"{n}/model.ts")
        models[n] = torch.jit.load(path, map_location="cpu").eval()
    return models


def windows_from_beats(beats, per):
    """Group bars into windows of `per` bars, restarting at every section."""
    out = []
    for sec in beats["sections"]:
        sb = [b for b in beats["bars"] if b.get("section_index") == sec["index"]]
        for i in range(0, len(sb), per):
            grp = sb[i:i + per]
            if len(grp) < per and out and out[-1]["section_index"] == sec["index"] and len(grp) * 2 < per:
                out[-1]["end"] = grp[-1]["end"]           # fold a short tail into the previous window
                out[-1]["bars"] += [b["index"] for b in grp]
                continue
            out.append({"section_index": sec["index"], "section": sec["name"],
                        "delivery": sec.get("delivery", ""),
                        "bars": [b["index"] for b in grp], "start": grp[0]["start"], "end": grp[-1]["end"]})
    return out


def embed(models, y, wins, min_active):
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    thr = rms.max() * 0.08
    keep, embs = [], {n: [] for n in models}
    for w in wins:
        a, b = int(w["start"] * SR), int(w["end"] * SR)
        x = y[a:b]
        r = rms[a // 512:b // 512]
        w["vocal_activity"] = round(float((r > thr).mean()) if len(r) else 0.0, 2)
        if w["vocal_activity"] < min_active or len(x) < SR:
            continue
        x = x / (np.abs(x).max() + 1e-9) * 0.5           # loudness shouldn't drive identity
        with torch.no_grad():
            t = torch.from_numpy(x.astype(np.float32))[None]
            for n, m in models.items():
                e = m(t)[0].numpy()
                embs[n].append(e / (np.linalg.norm(e) + 1e-9))
        keep.append(w)
    return keep, {n: np.array(v) for n, v in embs.items()}


def cluster(E, k_max, k_force=None):
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import silhouette_score
    D = np.clip(1 - E @ E.T, 0, 2)
    np.fill_diagonal(D, 0)
    scores = {}
    for k in range(2, min(k_max, len(E) - 1) + 1):
        lab = AgglomerativeClustering(n_clusters=k, metric="precomputed", linkage="average").fit_predict(D)
        if len(set(lab)) > 1:
            scores[k] = float(silhouette_score(D, lab, metric="precomputed"))
    k = k_force or (max(scores, key=scores.get) if scores else 1)
    lab = (np.zeros(len(E), int) if k == 1 else
           AgglomerativeClustering(n_clusters=k, metric="precomputed", linkage="average").fit_predict(D))
    # relabel by first appearance: A, B, C...
    order = {}
    for l in lab:
        order.setdefault(l, len(order))
    return np.array([order[l] for l in lab]), scores, k


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vocals", default="stems/htdemucs/song/vocals.wav")
    ap.add_argument("--beats", default="analysis/beats.json")
    ap.add_argument("--out", default="analysis/voices.json")
    ap.add_argument("--bars-per-window", type=int, default=2)
    ap.add_argument("--min-activity", type=float, default=0.35)
    ap.add_argument("--models", default="byol,contrastive-vc")
    ap.add_argument("--k", type=int, help="force number of voices")
    ap.add_argument("--k-max", type=int, default=5)
    args = ap.parse_args()

    beats = json.loads(Path(args.beats).read_text(encoding="utf-8"))
    y, _ = librosa.load(args.vocals, sr=SR, mono=True)
    models = load_models(args.models.split(","))
    wins = windows_from_beats(beats, args.bars_per_window)
    wins, embs = embed(models, y, wins, args.min_activity)
    if len(wins) < 4:
        raise SystemExit("too few vocal windows to cluster")

    # combine models: average of per-model cosine-similarity structure via concatenation
    E = np.hstack([embs[n] for n in embs]) / np.sqrt(len(embs))
    labels, sil, k = cluster(E, args.k_max, args.k)

    per_model = {}
    for n, Em in embs.items():
        lm, sm, km = cluster(Em, args.k_max, args.k)
        S = Em @ Em.T
        iu = np.triu_indices(len(Em), 1)
        per_model[n] = {"best_k": km, "silhouette": {str(a): round(b, 3) for a, b in sm.items()},
                        "agreement_with_combined": round(float(np.mean(lm == labels)), 2),
                        "similarity_mean": round(float(S[iu].mean()), 3),
                        "similarity_p10": round(float(np.percentile(S[iu], 10)), 3)}

    S = E @ E.T
    for w, l in zip(wins, labels):
        w["voice"] = chr(65 + l)
        same = S[wins.index(w)][labels == l]
        w["cohesion"] = round(float(np.mean(same)), 3)

    sections = []
    for sec in beats["sections"]:
        ws = [w for w in wins if w["section_index"] == sec["index"]]
        seq = "".join(w["voice"] for w in ws)
        counts = {v: seq.count(v) for v in sorted(set(seq))}
        sections.append({"index": sec["index"], "name": sec["name"], "delivery": sec.get("delivery", ""),
                         "start": sec["start"], "end": sec["end"], "voices": seq, "counts": counts})

    centroid = {chr(65 + c): E[labels == c].mean(0) for c in range(k)}
    between = {f"{a}-{b}": round(float(centroid[a] @ centroid[b] /
                                       (np.linalg.norm(centroid[a]) * np.linalg.norm(centroid[b]))), 3)
               for i, a in enumerate(centroid) for b in list(centroid)[i + 1:]}
    result = {
        "vocals": args.vocals, "models": list(embs), "bars_per_window": args.bars_per_window,
        "n_windows": len(wins), "k": k, "k_forced": bool(args.k),
        "silhouette_combined": {str(a): round(b, 3) for a, b in sil.items()},
        "centroid_similarity": between, "per_model": per_model,
        "sections": sections, "windows": wins,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{len(wins)} vocal windows; silhouette by k: {result['silhouette_combined']} -> k={k}")
    print(f"centroid similarity: {between}")
    for n, pm in per_model.items():
        print(f"  {n:<15} best k={pm['best_k']} sil={pm['silhouette']} agree={pm['agreement_with_combined']} "
              f"sim mean={pm['similarity_mean']}")
    for s in sections:
        m, ss = divmod(int(s["start"]), 60)
        print(f"  {m}:{ss:02d} {s['name']:<12} {s['delivery']:<28} {s['voices']}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
