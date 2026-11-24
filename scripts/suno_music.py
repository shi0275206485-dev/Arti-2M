"""Get the MV's song from Suno (or from any audio file) instead of local YuE2.

    python scripts/suno_music.py login                       # browser sign-in (once; token in <repo>/.suno/)
    python scripts/suno_music.py status                      # plan, credits, download credits
    python scripts/suno_music.py generate --style "..." --lyrics-file lyrics.txt [--title T] [--model v6-mini]
    python scripts/suno_music.py generate --style "..." --instrumental        # no vocals, no lyrics
    python scripts/suno_music.py download <clip_id> [--confirm]   # --confirm = allow spending a download credit
    python scripts/suno_music.py import path/to/song.mp3     # any audio file, e.g. downloaded from suno.com

All commands take --root <project dir> (default: this repo). generate makes 2 songs (one Suno call, charged to
your Suno credits), waits for them, saves music/suno_<timestamp>/clips.json and then tries to download the first
one. A song that is downloaded or imported becomes audio/song.wav; an old YuE2 analysis/score.abc is renamed to
score_old_<time>.abc so analyze_audio.py does an audio-only analysis (Suno gives no score).

Exit codes: 0 ok, 1 error, 3 needs you (sign in / approve a download credit / plan has no downloads).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suno_api as sa  # noqa: E402

ROOT = Path(".").resolve()
NEEDS_USER = 3


def log(msg):
    print(f"[suno] {msg}", flush=True)


def promote_file(src, source):
    """Make an audio file the project's current song (audio/song.wav), audio-only analysis from now on."""
    src = Path(src).resolve()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found in PATH")
    out = ROOT / "audio/song.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("song.tmp.wav")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-c:a", "pcm_s24le", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        raise SystemExit(f"ffmpeg could not read {src.name}: {r.stderr.strip()[:300]}")
    tmp.replace(out)
    analysis = ROOT / "analysis"
    analysis.mkdir(exist_ok=True)
    score = analysis / "score.abc"
    if score.exists():
        aside = score.with_name(f"score_old_{time.strftime('%Y%m%d_%H%M%S')}.abc")
        score.rename(aside)
        log(f"set the old YuE2 score aside -> {aside.name} (audio-only analysis for this song)")
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout.strip()
    (analysis / "song_source.json").write_text(json.dumps(
        dict(source, file=str(src.relative_to(ROOT)) if ROOT in src.parents else str(src),
             audio_seconds=float(dur or 0)), ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"promoted {src.name} -> audio/song.wav ({float(dur or 0):.1f}s)")


# ------------------------------------------------------------------ commands
def cmd_login(args):
    import http.server
    import urllib.parse
    import webbrowser
    redirect = sa.REDIRECTS[1]
    url = sa.login_url(redirect)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>Suno sign-in received. You can close this tab.</p>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8701), H)
    log("open this URL to sign in to Suno:\n" + url)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    if "error" in got:
        raise SystemExit(f"sign-in refused: {got}")
    sa.finish_login(got["code"], got["state"])
    log("signed in")
    return cmd_status(args)


def cmd_status(args):
    u = sa.call("account-usage")
    a = u.get("suno_account", {})
    print(json.dumps({"plan": a.get("plan", {}).get("name"), "credits": a.get("credits_remaining"),
                      "download_credits": a.get("download_credits_remaining"), "models": u.get("allowed_models"),
                      "features": u.get("features")}, ensure_ascii=False))
    return 0


def wait_complete(ids, timeout=900):
    t0, clips = time.time(), {}
    while time.time() - t0 < timeout:
        r = sa.call("audio-wait", {"ids": ids, "until": "complete"})
        for c in r.get("clips") or [r]:
            clips[c.get("id")] = c
        states = [clips.get(i, {}).get("status") for i in ids]
        log("status: " + ", ".join(f"{i[:8]} {s}" for i, s in zip(ids, states)))
        if all(s in ("complete", "error") for s in states):
            return [clips[i] for i in ids]
    raise SystemExit("Suno did not finish within 15 minutes; run `download <id>` later")


def cmd_generate(args):
    if args.run:   # resume an earlier run: same request + idempotency key = Suno returns the same songs, no charge
        run = ROOT / args.run
        req = json.loads((run / "request.json").read_text(encoding="utf-8"))
        log(f"resuming {run.name} (same idempotency key: no new songs, no new charge)")
    else:
        if not args.style:
            raise SystemExit("--style is required")
        if args.instrumental:
            req = {"style": args.style, "instrumental": True}
        else:
            if not args.lyrics_file:
                raise SystemExit("--lyrics-file is required unless --instrumental")
            req = {"style": args.style, "lyrics": Path(args.lyrics_file).read_text(encoding="utf-8")}
        if args.title:
            req["title"] = args.title[:256]
        if args.model:
            req["model"] = args.model
        run = ROOT / "music" / f"suno_{time.strftime('%Y%m%d_%H%M%S')}"
        run.mkdir(parents=True, exist_ok=True)
        (run / "request.json").write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"creating songs ({args.model or 'plan default model'}): {args.style[:120]}")
    r = sa.call("audio-create", dict(req, idempotency_key=run.name))
    ids = r.get("clip_ids") or ([r["id"]] if r.get("id") else [])
    if not ids:   # never lose a paid generation silently: show what Suno answered
        raise SystemExit(f"Suno's reply had no song ids: {json.dumps(r, ensure_ascii=False)[:400]}\n"
                         f"(the songs may still be in your Suno library; resume with: generate --run {run.relative_to(ROOT).as_posix()})")
    log(f"Suno clips: {', '.join(ids)}")
    clips = wait_complete(ids)
    info = [{"id": c.get("id"), "title": c.get("title"), "status": c.get("status"), "error": c.get("error"),
             "duration": (c.get("metadata") or {}).get("duration"), "song_url": c.get("song_url"),
             "cover": c.get("cover_image_url")} for c in clips]
    (run / "clips.json").write_text(json.dumps({"request": req, "clips": info}, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    for c in info:
        log(f"  {c['id']}  {c['status']}  {c['duration'] or 0:.0f}s  {c['song_url']}")
    print("SUNO_RUN " + json.dumps({"run": run.relative_to(ROOT).as_posix(), "clips": info}, ensure_ascii=False))
    ok = [c for c in info if c["status"] == "complete"]
    if not ok:
        raise SystemExit("Suno produced no finished song")
    if args.no_download:
        return 0
    return download(ok[0]["id"], False, run, {"request": req})


def download(cid, confirm, run=None, extra=None):
    run = run or ROOT / "music" / f"suno_{cid[:8]}"
    run.mkdir(parents=True, exist_ok=True)
    for _ in range(8):
        try:
            r = sa.call("audio-download", {"id": cid, "format": "mp3", "confirm": bool(confirm)})
        except sa.SunoError as e:
            reason = e.data.get("reason") or e.data.get("code")
            if reason in ("plan_required", "quota_exhausted", "no_permission", "daily_limit_exceeded",
                          "feature_not_on_plan", "insufficient_credits"):
                log(f"download blocked: {e} ({reason})")
                print("SUNO_NEEDS " + json.dumps({"id": cid, "reason": reason, "message": str(e)}))
                return NEEDS_USER
            raise
        status = r.get("status")
        if r.get("url") and status not in ("requires_credit", "processing"):
            break
        if status == "requires_credit":
            log(f"downloading {cid[:8]} needs 1 Suno download credit (you have {r.get('credits_remaining')}); "
                "approve it with --confirm or download it yourself on suno.com and import it")
            print("SUNO_NEEDS " + json.dumps({"id": cid, "reason": "requires_credit",
                                              "credits_remaining": r.get("credits_remaining")}))
            return NEEDS_USER
        log(f"download: {status or r} ...")
        time.sleep(2)
    else:
        raise SystemExit(f"Suno never produced a download for {cid}")
    dest = run / f"{cid}.mp3"
    with httpx.stream("GET", r["url"], follow_redirects=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    log(f"downloaded {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")
    try:   # word timings for later use; free, but may still be processing
        al = sa.call("audio-lyrics-alignment", {"id": cid})
        (run / f"{cid}_alignment.json").write_text(json.dumps(al, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        log(f"(lyrics alignment not saved: {e})")
    promote_file(dest, dict(extra or {}, source="suno", clip_id=cid, run_dir=run.relative_to(ROOT).as_posix()))
    return 0


def cmd_download(args):
    return download(args.id, args.confirm)


def cmd_import(args):
    src = Path(args.file).resolve()
    if not src.exists():
        raise SystemExit(f"no such file: {src}")
    run = ROOT / "music" / f"upload_{time.strftime('%Y%m%d_%H%M%S')}"
    if not (src.parent.name.startswith("upload_") and src.parent.parent == ROOT / "music"):
        # keep a copy of what was used next to the other runs (the web upload already saved it there)
        run.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, run / src.name)
        src = run / src.name
    promote_file(src, {"source": "upload", "original": args.file})
    return 0


def main():
    global ROOT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="project root (default: this repo)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    sub.add_parser("status")
    g = sub.add_parser("generate")
    g.add_argument("--style")
    g.add_argument("--run", metavar="music/suno_<ts>",
                   help="resume that earlier run (same request + idempotency key: no new songs, no charge)")
    g.add_argument("--lyrics-file")
    g.add_argument("--instrumental", action="store_true", help="no vocals; no lyrics needed")
    g.add_argument("--title")
    g.add_argument("--model", help="e.g. v6-mini; default: your plan's default")
    g.add_argument("--no-download", action="store_true")
    d = sub.add_parser("download")
    d.add_argument("id")
    d.add_argument("--confirm", action="store_true", help="allow spending one Suno download credit")
    i = sub.add_parser("import")
    i.add_argument("file")
    args = ap.parse_args()
    ROOT = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        return {"login": cmd_login, "status": cmd_status, "generate": cmd_generate, "download": cmd_download,
                "import": cmd_import}[args.cmd](args)
    except sa.SunoError as e:
        if e.data.get("reason") == "not_signed_in":
            log(f"{e}. Sign in from the web page (Suno button) or run: python scripts/suno_music.py login")
            print("SUNO_NEEDS " + json.dumps({"reason": "not_signed_in"}))
            return NEEDS_USER
        raise SystemExit(f"[suno] {e}")


if __name__ == "__main__":
    raise SystemExit(main())
