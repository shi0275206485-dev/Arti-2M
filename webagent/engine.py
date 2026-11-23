"""Project state + a single GPU worker that runs pipeline stages one at a time.

A project is a self-contained copy of the pipeline layout under projects/<id>/ (audio/, analysis/, stems/,
shots/, clips/, output/, workflows/); the repo's scripts/ are run with that folder as the working directory.
Only one job runs at a time (YuE2 and ComfyUI share the GPU, and two gen processes clobber index.json).
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from . import brain, design, studio

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PROJECTS = ROOT / "projects"
PY = sys.executable

STAGES = ["concept", "music", "analysis", "refs", "design", "frames", "videos", "assemble"]
# stages after which a "review" project pauses for the user
CHECKPOINTS = {"concept", "music", "refs", "design", "frames", "videos"}
LABELS = {"concept": "Concept & lyrics", "music": "Song", "analysis": "Beat / section analysis",
          "refs": "Member reference portraits", "design": "Shot design", "frames": "First frames + QC",
          "videos": "Video clips + QC", "assemble": "Final cut"}
MAX_QC_RETRIES = 2
CHUNK_BUDGET = 400   # seconds of estimated LTX time per ComfyUI session (it leaks RAM per clip)


class Cancelled(Exception):
    pass


class NeedsUser(Exception):
    """The stage can't go on without the user (sign in, approve a download credit, upload a file)."""


MUSIC_SOURCES = ("library", "yue2", "suno", "upload")   # library = a song from the music studio


class Project:
    def __init__(self, pid):
        self.id = pid
        self.dir = PROJECTS / pid
        self.path = self.dir / "project.json"
        self.lock = threading.RLock()

    # -------- state
    def load(self):
        with self.lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, st):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)

    def update(self, fn):
        with self.lock:
            st = self.load()
            fn(st)
            self.save(st)
            return st

    def set_stage(self, stage, status, msg=""):
        def f(st):
            st["stages"][stage] = {"status": status, "msg": msg, "t": time.time()}
        self.update(f)

    def log(self, text):
        line = f"[{time.strftime('%H:%M:%S')}] {text}"
        with open(self.dir / "agent.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def rel(self, p):
        return Path(p).as_posix()

    def jload(self, rel, default=None):
        p = self.dir / rel
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def create_project(title, brief, mode, music_source="yue2", song_id=None):
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:24] or "mv"
    pid = f"{slug}_{time.strftime('%Y%m%d_%H%M%S')}"
    d = PROJECTS / pid
    for sub in ("audio", "analysis", "shots/refs", "shots/plates", "shots/frames", "clips", "output", "music"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "workflows", d / "workflows", ignore=shutil.ignore_patterns("video_*.json", "library.json", "user"))
    st = {"id": pid, "title": title, "brief": brief, "mode": mode, "created": time.time(),
          "stages": {s: {"status": "pending", "msg": ""} for s in STAGES},
          "concept": None, "music": {"seed": 42, "runs": [], "source": music_source, "song_id": song_id}, "overrides": {}, "qc": {"frames": {}, "clips": {}},
          "refs": {}, "error": None}
    p = Project(pid)
    p.dir.mkdir(parents=True, exist_ok=True)
    p.save(st)
    p.log(f"project created ({mode} mode)")
    return p


def list_projects():
    out = []
    for d in sorted(PROJECTS.glob("*/project.json"), reverse=True):
        try:
            st = json.loads(d.read_text(encoding="utf-8"))
            out.append({"id": st["id"], "title": st["title"], "mode": st["mode"],
                        "stages": {k: v["status"] for k, v in st["stages"].items()}})
        except Exception:
            pass
    return out


# ====================================================================== worker
class Engine:
    def __init__(self):
        self.q = queue.Queue()
        self.current = None          # (pid, task name)
        self.proc = None
        self.cancel_flag = False
        threading.Thread(target=self._loop, daemon=True).start()

    # -------- public
    def submit(self, pid, task, **kw):
        self.q.put((pid, task, kw))

    def queued(self):
        return [(p, t) for p, t, _ in list(self.q.queue)]

    def cancel(self):
        self.cancel_flag = True
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)

    # -------- loop
    def _loop(self):
        while True:
            pid, task, kw = self.q.get()
            self.current = (pid, task)
            self.cancel_flag = False
            if pid.startswith("song:"):
                self._song_job(pid[5:], task, kw)
                continue
            p = Project(pid)
            try:
                if task in STAGES:
                    self._run_stage(p, task)
                else:
                    getattr(self, "task_" + task)(p, **kw)
            except NeedsUser as e:
                p.log(f"{task}: waiting for you - {e}")
                if task in STAGES:
                    p.set_stage(task, "waiting", str(e))
            except Cancelled:
                p.log(f"{task}: cancelled")
                if task in STAGES:
                    p.set_stage(task, "error", "cancelled")
            except Exception as e:
                p.log(f"{task}: ERROR {e}\n{traceback.format_exc()}")
                if task in STAGES:
                    p.set_stage(task, "error", str(e)[:500])
            finally:
                self.current = None
                self.proc = None

    def _song_job(self, sid, task, kw):
        s = studio.Song(sid)
        try:
            getattr(self, "song_" + task)(s, **kw)
        except NeedsUser as e:
            s.log(f"{task}: waiting for you - {e}")
            s.set(status="needs", msg=str(e))
        except Cancelled:
            s.log(f"{task}: cancelled")
            s.set(status="error", msg="cancelled")
        except Exception as e:
            s.log(f"{task}: ERROR {e}\n{traceback.format_exc()}")
            s.set(status="error", msg=str(e)[:500])
        finally:
            self.current = None
            self.proc = None

    def _run_stage(self, p, stage):
        p.set_stage(stage, "running")
        p.log(f"=== {LABELS[stage]} ===")
        getattr(self, "stage_" + stage)(p)
        self._complete(p, stage)

    def _complete(self, p, stage):
        st = p.load()
        if st["mode"] == "review" and stage in CHECKPOINTS:
            p.set_stage(stage, "waiting", "waiting for your review")
            p.log(f"{stage}: ready for review")
        else:
            self._finish(p, stage)

    def _finish(self, p, stage):
        p.set_stage(stage, "done")
        i = STAGES.index(stage)
        if i + 1 < len(STAGES):
            self.submit(p.id, STAGES[i + 1])

    def approve(self, pid, stage):
        p = Project(pid)
        st = p.load()
        if st["stages"][stage]["status"] != "waiting":
            return
        if stage == "music" and (st["music"].get("needs") or not (p.dir / "audio/song.wav").exists()):
            return    # nothing usable yet (Suno download not approved / no upload)
        self._finish(p, stage)

    # -------- helpers
    def sh(self, p, args, env=None, check=True, capture=None):
        if self.cancel_flag:
            raise Cancelled()
        cmd = [PY, "-u"] + [str(a) for a in args]
        p.log("$ " + Path(str(args[0])).name + " " + " ".join(str(a) for a in args[1:]))
        e = dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {}))
        self.proc = subprocess.Popen(cmd, cwd=p.dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     env=e, text=True, encoding="utf-8", errors="replace")
        for line in self.proc.stdout:
            line = line.rstrip()
            if capture is not None:
                capture.append(line)
            if line and not line.startswith(("Exception ignored", "Traceback (most recent call last)", "  File ",
                                             "OSError: [WinError 6]", "    ")):
                p.log("  " + line)
        rc = self.proc.wait()
        self.proc = None
        if self.cancel_flag:
            raise Cancelled()
        if check and rc != 0:
            raise RuntimeError(f"{Path(str(args[0])).name} exited with {rc}")
        return rc

    def comfy(self, p, action):
        args = [SCRIPTS / "comfy_server.py", action] + (["--cache-none"] if action == "start" else [])
        self.sh(p, args, check=(action == "start"))

    def ensure_comfy(self, p):
        r = subprocess.run([PY, SCRIPTS / "comfy_server.py", "status"], capture_output=True, text=True)
        if not r.stdout.startswith("running"):   # "not running" also contains "running"
            self.comfy(p, "start")

    def style_env(self, p):
        c = p.load()["concept"] or {}
        env = {}
        if c.get("frame_style"):
            env["MV_FRAME_STYLE"] = c["frame_style"]
        if c.get("video_style"):
            env["MV_VIDEO_STYLE"] = c["video_style"]
        if any(m.get("noun") == "man" for m in c.get("members", [])):
            env["MV_KEEP_NEUTRAL"] = "1"
        return env

    def members_info(self, p):
        return p.jload("shots/members.json")["members"]

    def ref_paths(self, p, names):
        return {n: p.dir / f"shots/refs/{n}.png" for n in names if (p.dir / f"shots/refs/{n}.png").exists()}

    # ================================================================ stages
    def stage_concept(self, p):
        st = p.load()
        if not st["concept"]:
            song = self.library_song(p)
            p.log("asking Claude for a concept" + (f" for the song '{song['title']}'..." if song else "..."))
            c = brain.concept(st["brief"], song)
            p.update(lambda s: s.__setitem__("concept", c))
        self.write_concept_files(p)

    def write_concept_files(self, p):
        c = p.load()["concept"]
        (p.dir / "lyrics.txt").write_text(c["lyrics"], encoding="utf-8")
        members = {m["name"]: {"look": m["look"], "signature_color": m["signature_color"], "noun": m["noun"],
                               "video_desc": m["video_desc"], "reference_image": f"shots/refs/{m['name']}.png"}
                   for m in c["members"]}
        (p.dir / "shots/members.json").write_text(json.dumps(
            {"song": c["title"], "members": members}, indent=1, ensure_ascii=False), encoding="utf-8")
        p.log(f"concept: {c['title']} | {c['style']} | members {', '.join(members)}")

    def stage_music(self, p):
        st = p.load()
        src = st["music"].get("source", "yue2")
        cur = st["music"].get("current") or {}
        if (src != "yue2" and cur.get("source") == src and not st["music"].get("force")
                and (p.dir / "audio/song.wav").exists()):
            p.log(f"music: keeping the {src} song you already have (use regenerate for a new one)")
            return
        p.update(lambda s: s["music"].pop("force", None))
        if src == "library":
            return self.import_song(p)
        if src == "suno":
            return self.music_suno(p)
        if src == "upload":
            p.update(lambda s: s["music"].__setitem__("needs", {"reason": "upload"}))
            raise NeedsUser("upload an audio file (mp3 / wav / flac ...)")
        self.comfy(p, "stop")   # YuE2 needs the whole GPU
        seed = st["music"]["seed"]
        # YuE2 wants a filename-safe id that starts/ends with an alphanumeric (titles are often CJK)
        slug = re.sub(r"[^A-Za-z0-9]+", "_", st["concept"]["title"]).strip("_")[:20].strip("_") or "song"
        t0 = time.time() - 2
        rc = self.sh(p, [SCRIPTS / "gen_music.py", "--root", ".", "--id", slug, "--style", st["concept"]["style"],
                         "--lyrics-file", "lyrics.txt", "--seed", seed], check=False)
        # gen_music exits 1 both on failure and on truncation; only a song.wav written by THIS run counts
        # (otherwise an old song from a previous concept would silently be reused)
        song = p.dir / "audio/song.wav"
        if not song.exists() or song.stat().st_mtime < t0:
            raise RuntimeError("YuE2 produced no new audio (see the log above)")
        if rc == 1:
            p.log("WARNING: YuE2 truncated the song; consider a new seed or shorter lyrics")
        self._song_info(p, {"source": "yue2", "seed": seed, "truncated": rc == 1})

    # -------- Suno / uploaded song
    @staticmethod
    def _tagged(lines, tag):
        for line in reversed(lines):
            if line.startswith(tag + " "):
                return json.loads(line[len(tag) + 1:])
        return None

    def _suno_needs(self, p, lines):
        needs = self._tagged(lines, "SUNO_NEEDS") or {"reason": "unknown"}
        p.update(lambda s: s["music"].__setitem__("needs", needs))
        msg = {"not_signed_in": "sign in to Suno first",
               "requires_credit": "downloading this song uses 1 Suno download credit - approve it, "
                                  "or download it on suno.com and upload the file",
               }.get(needs["reason"], f"Suno download not possible ({needs['reason']}): download the song on "
                                      "suno.com yourself and upload the file")
        raise NeedsUser(msg)

    def music_suno(self, p):
        c = p.load()["concept"]
        lines = []
        rc = self.sh(p, [SCRIPTS / "suno_music.py", "--root", ".", "generate", "--style", c["style"],
                         "--lyrics-file", "lyrics.txt", "--title", c["title"]], check=False, capture=lines)
        run = self._tagged(lines, "SUNO_RUN")
        if run:
            p.update(lambda s: s["music"].__setitem__("suno", dict(run, chosen=None)))
        if rc == 3:
            self._suno_needs(p, lines)
        if rc != 0:
            raise RuntimeError("Suno generation failed (see the log above)")
        ok = [c for c in run["clips"] if c["status"] == "complete"] if run else []
        self._song_info(p, {"source": "suno", "clip_id": ok[0]["id"] if ok else None})

    def _song_info(self, p, info):
        info["t"] = time.time()

        def f(s):
            s["music"]["runs"].append(info)
            s["music"]["current"] = info
            s["music"]["needs"] = None
            if info.get("clip_id") and s["music"].get("suno"):
                s["music"]["suno"]["chosen"] = info["clip_id"]
        p.update(f)

    def _new_song(self, p, info):
        """A song arrived outside the music stage (Suno download, upload): everything after it starts over."""
        self._song_info(p, info)
        self._after_new_song(p)

    def _after_new_song(self, p):
        self._reset_from(p, "analysis")
        st = p.load()
        if all(st["stages"][s]["status"] == "done" for s in STAGES[:STAGES.index("music")]):
            self._complete(p, "music")
        else:   # concept not approved yet: the music stage will keep this song when it runs
            p.set_stage("music", "pending")

    def task_suno_download(self, p, clip_id, confirm=False):
        lines = []
        args = [SCRIPTS / "suno_music.py", "--root", ".", "download", clip_id] + (["--confirm"] if confirm else [])
        rc = self.sh(p, args, check=False, capture=lines)
        if rc == 3:
            try:
                self._suno_needs(p, lines)
            except NeedsUser as e:
                p.set_stage("music", "waiting", str(e))
                p.log(f"music: waiting for you - {e}")
            return
        if rc != 0:
            raise RuntimeError("Suno download failed (see the log above)")
        p.update(lambda s: s["music"].__setitem__("source", "suno"))
        self._new_song(p, {"source": "suno", "clip_id": clip_id})

    def task_import_audio(self, p, path):
        self.sh(p, [SCRIPTS / "suno_music.py", "--root", ".", "import", path])
        p.update(lambda s: s["music"].__setitem__("source", "upload"))
        self._new_song(p, {"source": "upload", "file": path})

    def stage_analysis(self, p):
        self.sh(p, [SCRIPTS / "analyze_audio.py", "audio/song.wav", "--stems"])
        b = p.jload("analysis/beats.json")
        p.log(f"analysis: {len(b['bars'])} bars, {len(b['sections'])} sections, {b['tempo_bpm']:.1f} BPM, "
              f"{b['duration']:.1f}s")
        for w in b.get("warnings", []):
            p.log(f"  analysis warning: {w}")

    def stage_refs(self, p):
        self.ensure_comfy(p)
        self.sh(p, [SCRIPTS / "gen_refs.py", "--n", "4"])
        self.auto_pick_refs(p)

    def auto_pick_refs(self, p):
        info = self.members_info(p)
        for name, m in info.items():
            cands = sorted((p.dir / "shots/refs").glob(f"{name}_cand*.png"))
            best, reason = 0, "first candidate"
            try:
                r = brain.pick_reference(m["look"], cands)
                best, reason = max(0, min(r["best"], len(cands) - 1)), r["reason"]
            except Exception as e:
                p.log(f"refs: Claude pick failed ({e}); using candidate 0")
            self.pick_ref(p, name, best, reason)

    def pick_ref(self, p, name, k, reason="chosen by you"):
        shutil.copyfile(p.dir / f"shots/refs/{name}_cand{k}.png", p.dir / f"shots/refs/{name}.png")
        p.update(lambda s: s["refs"].__setitem__(name, {"cand": k, "reason": reason}))
        p.log(f"refs: {name} -> candidate {k} ({reason})")

    def stage_design(self, p):
        st = p.load()
        c = st["concept"]
        beats = p.jload("analysis/beats.json")
        info = self.members_info(p)
        lights = {l["key"]: l["description"] for l in c["lights"]}
        text = design.bars_text(beats)
        feedback, rows = None, None
        for attempt in range(3):
            p.log(f"asking Claude for the shot design (attempt {attempt + 1})...")
            raw = brain.design(text, list(info), list(lights), feedback)
            rows, errors = design.validate(raw, beats, list(info))
            if not errors:
                break
            feedback = "\n".join(errors[:30])
            p.log(f"design problems: {feedback}")
        else:
            raise RuntimeError("Claude could not produce a design that covers every bar exactly once")
        song = self.library_song(p)
        if song and song.get("instrumental"):   # no vocals: never drive a mouth (audio-only "vocal" bars can be noise)
            for r in rows:
                r["lipsync"] = None
        (p.dir / "shots/design_rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        design.write_design(p.dir / "shots/shot_design.py", rows, c["stage_plate"], lights, info)
        p.update(lambda s: s.__setitem__("overrides", {}))
        self.build(p)
        # gen_frames.py --plates skips an existing stage.png; after a new concept the old plate would be reused.
        # Remember the prompt each plate was made from and set the old image aside (never deleted) on change.
        plate, made_from = p.dir / "shots/plates/stage.png", p.dir / "shots/plates/stage.prompt.txt"
        prompt_used = made_from.read_text(encoding="utf-8") if made_from.exists() else None
        if plate.exists() and prompt_used != c["stage_plate"]:
            plate.rename(plate.with_name(f"stage_old_{time.strftime('%Y%m%d_%H%M%S')}.png"))
            p.log("design: stage description changed -> generating a new stage plate (old one kept)")
        self.ensure_comfy(p)
        self.sh(p, [SCRIPTS / "gen_frames.py", "--plates"], env=self.style_env(p))
        made_from.write_text(c["stage_plate"], encoding="utf-8")

    def build(self, p):
        self.sh(p, [SCRIPTS / "build_shots.py"])
        self.apply_overrides(p)

    def apply_overrides(self, p):
        ov = p.load()["overrides"]
        if not ov:
            return
        path = p.dir / "shots/shots.json"
        shots = json.loads(path.read_text(encoding="utf-8"))
        for s in shots:
            o = ov.get(s["id"], {})
            if o.get("frame"):
                s["frame"]["prompt"] = o["frame"]
            if o.get("motion"):
                s["video"]["prompt"] = o["motion"]
        path.write_text(json.dumps(shots, indent=1, ensure_ascii=False), encoding="utf-8")

    def shots(self, p):
        return p.jload("shots/shots.json", [])

    # -------- frames
    def stage_frames(self, p):
        self.ensure_comfy(p)
        idx = p.jload("shots/frames/index.json", {})
        todo = [s["id"] for s in self.shots(p) if s["id"] not in idx]
        for i in range(0, len(todo), 8):
            self.sh(p, [SCRIPTS / "gen_frames.py", "--only", ",".join(todo[i:i + 8])], env=self.style_env(p))
        self.qc_loop(p, "frames")

    def gen_frames(self, p, ids, offset):
        self.ensure_comfy(p)
        self.sh(p, [SCRIPTS / "gen_frames.py", "--only", ",".join(ids), "--seed-offset", offset],
                env=self.style_env(p))

    # -------- videos
    def stage_videos(self, p):
        cidx = p.jload("clips/index.json", {})
        todo = [s for s in self.shots(p) if s["id"] not in cidx]
        self.render_clips(p, [s["id"] for s in todo], 0)
        self.qc_loop(p, "clips")

    def render_clips(self, p, ids, offset):
        """Render in chunks, restarting ComfyUI between chunks (it holds RAM per clip).
        Shots are grouped by role (i2v / lipsync) so a chunk never mixes two video models: when the roles use
        different workflows (e.g. MiniMax H3 + LTX) each model is loaded once per chunk instead of per shot."""
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import wf_bindings as wb
        sh = {s["id"]: s for s in self.shots(p)}
        chunks = []
        for role in ("i2v", "lipsync"):
            bf = p.dir / wb.BINDINGS_FILE
            b = (json.loads(bf.read_text(encoding="utf-8")).get(role) if bf.exists() else None) or wb.DEFAULTS[role]
            budget = b.get("chunk_budget", CHUNK_BUDGET)
            chunk, tot = [], 0
            for i in ids:
                if sh[i]["video"]["mode"] != role:
                    continue
                g = sh[i]["gen_seconds"]
                e = b.get("est_seconds") or (75 if g < 3 else (95 if g < 4.5 else 115))
                if chunk and tot + e > budget:
                    chunks.append(chunk)
                    chunk, tot = [], 0
                chunk.append(i)
                tot += e
            if chunk:
                chunks.append(chunk)
        for n, c in enumerate(chunks, 1):
            p.log(f"videos: chunk {n}/{len(chunks)} ({len(c)} clips)")
            self.comfy(p, "stop")
            self.comfy(p, "start")
            self.sh(p, [SCRIPTS / "gen_videos.py", "--only", ",".join(c), "--seed-offset", offset],
                    env=self.style_env(p))

    # -------- QC
    def sample_clip(self, clip, seconds):
        tmp = Path(tempfile.mkdtemp(prefix="mvqc_"))
        out = []
        for label, f in (("15%", 0.15), ("50%", 0.5), ("90%", 0.9)):
            dest = tmp / f"{label[:-1]}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds * f:.2f}", "-i", str(clip),
                            "-frames:v", "1", "-vf", "scale=640:-2", str(dest)], check=False)
            if dest.exists():
                out.append((label, dest))
        return out

    def qc_one(self, p, kind, s):
        refs = self.ref_paths(p, s["members"])
        if kind == "frames":
            f = p.jload("shots/frames/index.json")[s["id"]]["chosen"]
            return brain.qc_frame(s, p.dir / f, refs)
        c = p.jload("clips/index.json")[s["id"]]["chosen"]
        return brain.qc_clip(s, self.sample_clip(p.dir / c, s["seconds"]), refs)

    def qc_loop(self, p, kind):
        if not brain.status()["ok"]:
            p.log("QC skipped: no Claude API credentials")
            return
        shots = {s["id"]: s for s in self.shots(p)}
        pending = list(shots)
        for attempt in range(MAX_QC_RETRIES + 1):
            failed = []
            for sid in pending:
                if self.cancel_flag:
                    raise Cancelled()
                try:
                    r = self.qc_one(p, kind, shots[sid])
                except Exception as e:
                    p.log(f"QC {sid}: error {e}")
                    continue
                p.update(lambda st: st["qc"][kind].__setitem__(sid, dict(r, attempt=attempt)))
                if not r["ok"]:
                    p.log(f"QC {kind} {sid} FAIL: {'; '.join(r['issues'])} | fix: {r['fix']}")
                    failed.append((sid, r))
            p.log(f"QC {kind} round {attempt + 1}: {len(pending) - len(failed)}/{len(pending)} passed")
            if not failed or attempt == MAX_QC_RETRIES:
                break
            # add the suggested fix to the prompt and re-render with a new seed
            for sid, r in failed:
                if r["fix"]:
                    key = "frame" if kind == "frames" else "motion"
                    base = shots[sid]["frame"]["prompt"] if kind == "frames" else shots[sid]["video"]["prompt"]
                    p.update(lambda st: st["overrides"].setdefault(sid, {}).__setitem__(key, f"{base}, {r['fix']}"))
            self.apply_overrides(p)
            shots = {s["id"]: s for s in self.shots(p)}
            ids = [sid for sid, _ in failed]
            if kind == "frames":
                self.gen_frames(p, ids, 10 * (attempt + 1))
            else:
                self.render_clips(p, ids, 10 * (attempt + 1))
            pending = ids

    def stage_assemble(self, p):
        self.comfy(p, "stop")
        out = f"output/mv_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        self.sh(p, [SCRIPTS / "assemble.py", "--shots", "shots/shots.json", "--audio", "audio/song.wav",
                    "--out", out])
        p.update(lambda s: s.__setitem__("final", out))
        p.log(f"final cut: {out}")

    # ================================================================ song library (music studio)
    def library_song(self, p):
        """The project's music-studio song state, or None for projects that make their own song."""
        m = p.load()["music"]
        if m.get("source") != "library" or not m.get("song_id"):
            return None
        return studio.Song(m["song_id"]).load()

    def import_song(self, p):
        """Copy the chosen library song into the project: audio, score (if YuE2 made one), source info, lyrics."""
        sid = p.load()["music"]["song_id"]
        s = studio.Song(sid)
        if not s.exists():
            raise RuntimeError(f"song {sid} is not in the library any more")
        ss = s.load()
        if not s.has_audio():
            raise NeedsUser(f"the song '{ss['title']}' has no audio yet - finish it in the music studio first")
        (p.dir / "audio").mkdir(exist_ok=True)
        shutil.copyfile(s.dir / "audio/song.wav", p.dir / "audio/song.wav")
        an = p.dir / "analysis"
        an.mkdir(exist_ok=True)
        old = an / "score.abc"
        if old.exists():
            old.rename(an / f"score_old_{time.strftime('%Y%m%d_%H%M%S')}.abc")
        for name in ("score.abc", "song_source.json"):
            if (s.dir / "analysis" / name).exists():
                shutil.copyfile(s.dir / "analysis" / name, an / name)
        (p.dir / "lyrics.txt").write_text(ss.get("lyrics") or "", encoding="utf-8")
        has_score = (an / "score.abc").exists()
        p.log(f"music: using library song '{ss['title']}' ({ss['engine']}, {ss.get('duration') or 0:.0f}s"
              f"{', with score' if has_score else ', no score: audio-only analysis'})")
        self._song_info(p, {"source": "library", "song_id": sid, "title": ss["title"], "engine": ss["engine"],
                            "instrumental": bool(ss.get("instrumental"))})

    def task_use_song(self, p, song_id):
        """Switch an MV project to another library song; the concept keeps its visuals, takes the new words."""
        ss = studio.Song(song_id).load()

        def f(st):
            st["music"]["source"] = "library"
            st["music"]["song_id"] = song_id
            if st.get("concept"):
                st["concept"].update(title=ss["title"] or st["concept"]["title"],
                                     style=ss["style"] or st["concept"]["style"], lyrics=ss.get("lyrics") or "")
        p.update(f)
        if p.load().get("concept"):
            self.write_concept_files(p)
        self.import_song(p)
        self._after_new_song(p)

    # song jobs (run on the same single worker: YuE2 needs the GPU)
    def song_draft(self, s):
        st = s.load()
        s.set(status="drafting", msg="")
        s.log("asking Claude to write the song...")
        r = brain.song_draft(st["brief"], "Suno" if st["engine"] == "suno" else "YuE2", st.get("instrumental"),
                             st.get("genre"), st.get("settings"))
        s.set(title=r["title"], style=r["style"], lyrics="" if r["instrumental"] else r["lyrics"],
              instrumental=r["instrumental"], settings=studio.clean_settings(r["settings"]), style_custom=False,
              status="draft")
        s.log(f"draft: {r['title']} | {r['style']}")

    def song_generate(self, s, new_seed=False):
        st = s.load()
        inst = bool(st.get("instrumental"))
        if not st["style"].strip() or not (inst or st["lyrics"].strip()):
            raise NeedsUser("write a style" + ("" if inst else " and lyrics") + " first (or let Claude draft them)")
        if new_seed:
            st = s.set(seed=st["seed"] + 1)
        s.set(status="generating", msg="", needs=None)
        (s.dir / "lyrics.txt").write_text(st["lyrics"], encoding="utf-8")
        if st["engine"] == "suno":
            lines = []
            rc = self.sh(s, [SCRIPTS / "suno_music.py", "--root", ".", "generate", "--style", st["style"],
                             "--title", st["title"] or "Untitled"]
                         + (["--instrumental"] if inst else ["--lyrics-file", "lyrics.txt"]),
                         check=False, capture=lines)
            run = self._tagged(lines, "SUNO_RUN")
            if run:
                s.set(suno=run)
            if rc == 3:
                return self._song_needs(s, lines)
            if rc != 0:
                raise RuntimeError("Suno generation failed (see the log)")
            ok = [c for c in run["clips"] if c["status"] == "complete"]
            return self._song_ready(s, {"source": "suno", "clip_id": ok[0]["id"] if ok else None})
        self.comfy(s, "stop")   # YuE2 needs the whole GPU
        slug = re.sub(r"[^A-Za-z0-9]+", "_", st["title"]).strip("_")[:20].strip("_") or "song"
        t0 = time.time() - 2
        rc = self.sh(s, [SCRIPTS / "gen_music.py", "--root", ".", "--id", slug, "--style", st["style"],
                         "--seed", st["seed"]] + (["--instrumental"] if inst else ["--lyrics-file", "lyrics.txt"])
                     + studio.yue_flags(st.get("yue"), inst),
                     check=False)
        song = s.dir / "audio/song.wav"
        if not song.exists() or song.stat().st_mtime < t0:
            raise RuntimeError("YuE2 produced no new audio (see the log)")
        if rc == 1:
            s.log("WARNING: YuE2 truncated the song; consider a new seed or shorter lyrics")
        self._song_ready(s, {"source": "yue2", "seed": st["seed"], "truncated": rc == 1})

    def _song_needs(self, s, lines):
        needs = self._tagged(lines, "SUNO_NEEDS") or {"reason": "unknown"}
        s.set(status="needs", needs=needs, msg=needs["reason"])
        s.log(f"waiting for you: {needs}")

    def _song_ready(self, s, info):
        info["t"] = time.time()
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(s.dir / "audio/song.wav")], capture_output=True, text=True).stdout.strip()

        def f(st):
            st.update(status="ready", msg="", needs=None, current=info, duration=float(dur or 0))
            st["runs"].append(info)
            if info.get("clip_id") and st.get("suno"):
                st["suno"]["chosen"] = info["clip_id"]
        s.update(f)
        s.log(f"song ready ({info['source']}, {float(dur or 0):.1f}s)")

    def song_suno_download(self, s, clip_id, confirm=False):
        lines = []
        rc = self.sh(s, [SCRIPTS / "suno_music.py", "--root", ".", "download", clip_id]
                     + (["--confirm"] if confirm else []), check=False, capture=lines)
        if rc == 3:
            return self._song_needs(s, lines)
        if rc != 0:
            raise RuntimeError("Suno download failed (see the log)")
        self._song_ready(s, {"source": "suno", "clip_id": clip_id})

    def song_import(self, s, path):
        self.sh(s, [SCRIPTS / "suno_music.py", "--root", ".", "import", path])
        self._song_ready(s, {"source": "upload", "file": path})

    # ================================================================ user actions
    def task_regen_music(self, p):
        def f(s):
            s["music"]["seed"] += 1
            s["music"]["force"] = True
        p.update(f)
        self._rerun_from(p, "music")

    def task_regen_concept(self, p):
        p.update(lambda s: s.__setitem__("concept", None))
        self._rerun_from(p, "concept")

    def task_regen_refs(self, p):
        self._rerun_from(p, "refs")

    def task_regen_design(self, p):
        self._rerun_from(p, "design")

    def _rerun_from(self, p, stage):
        self._reset_from(p, stage)
        self._run_stage(p, stage)

    def _reset_from(self, p, stage):
        # anything up to the shot design changes the shots: start fresh indexes (files are kept)
        if STAGES.index(stage) <= STAGES.index("design"):
            ts = time.strftime("%Y%m%d_%H%M%S")
            for rel in ("shots/frames/index.json", "clips/index.json"):
                f0 = p.dir / rel
                if f0.exists():
                    f0.rename(f0.with_name(f"index_old_{ts}.json"))
            p.update(lambda st: st.__setitem__("qc", {"frames": {}, "clips": {}}))

        def f(st):
            for s in STAGES[STAGES.index(stage):]:
                st["stages"][s] = {"status": "pending", "msg": ""}
        p.update(f)

    def task_regen_frame(self, p, sid, prompt=None):
        if prompt:
            p.update(lambda st: st["overrides"].setdefault(sid, {}).__setitem__("frame", prompt))
            self.apply_overrides(p)
        n = len(p.jload("shots/frames/index.json", {}).get(sid, {}).get("versions", []))
        self.gen_frames(p, [sid], 100 + n)
        p.update(lambda st: st["qc"]["frames"].pop(sid, None))

    def task_regen_clip(self, p, sid, motion=None):
        if motion:
            p.update(lambda st: st["overrides"].setdefault(sid, {}).__setitem__("motion", motion))
            self.apply_overrides(p)
        n = len(p.jload("clips/index.json", {}).get(sid, {}).get("versions", []))
        self.render_clips(p, [sid], 100 + n)
        p.update(lambda st: st["qc"]["clips"].pop(sid, None))

    def task_assemble(self, p):
        self._rerun_from(p, "assemble")
