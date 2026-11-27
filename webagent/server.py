"""MV Agent web server. Run:  .venv\\Scripts\\python -m webagent  (then open http://127.0.0.1:8700)"""
import json
import re
import shutil
import sys
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from . import brain, cast, design, engine, llm_local, studio, workflows

sys.path.insert(0, str(engine.SCRIPTS))
import spotify_genres  # noqa: E402
import suno_api  # noqa: E402

app = FastAPI(title="MV Agent")
ENGINE = engine.Engine()
STATIC = Path(__file__).parent / "static"


def proj(pid):
    p = engine.Project(pid)
    if not p.path.exists():
        raise HTTPException(404, "no such project")
    return p


TRASH = engine.ROOT / "trash"


def to_trash(kind, d, name):
    """Deleting a song / MV project moves its folder to trash/<kind>/<id>_<time>/ (recoverable by moving it back);
    nothing generated is erased."""
    dest = TRASH / kind / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(d), str(dest))
    except OSError as e:   # e.g. a file still open (audio playing in another program)
        raise HTTPException(409, f"could not move the folder (a file may be in use): {e}")
    return dest.relative_to(engine.ROOT).as_posix()


def jobs_for(target):
    jobs = ([ENGINE.current] if ENGINE.current else []) + ENGINE.queued()
    return [j for j in jobs if j[0] == target]


@app.get("/", response_class=HTMLResponse)
def index():   # no-cache: the browser revalidates, so an updated page never runs stale scripts
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@app.get("/static/{name}")
def static(name: str):
    f = (STATIC / name).resolve()
    if f.parent != STATIC.resolve() or not f.exists():
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


@app.get("/api/status")
def status():
    cfg = llm_local.load_cfg()
    return {"claude": brain.status(), "current": ENGINE.current, "queue": ENGINE.queued(),
            "llm": {"model": cfg["model"], "tasks": cfg["tasks"], "ready": {t: brain.ready(t) for t in llm_local.TASKS}}}


@app.post("/api/key")
def set_key(key: str = Body(..., embed=True)):
    brain.set_api_key(key.strip())   # kept in memory only, never written to disk
    return brain.status()


@app.post("/api/cancel")
def cancel():
    ENGINE.cancel()
    return {"ok": True}


@app.get("/api/projects")
def projects():
    return engine.list_projects()


@app.post("/api/projects")
def create(title: str = Body(...), brief: str = Body(""), mode: str = Body("review"),
           music_source: str = Body(None), song_id: str = Body(None), cast_ids: list[str] = Body(None),
           vmode: str = Body("stage"), style: str = Body(None), aspect: str = Body("16:9"), rng: str = Body("full", alias="range")):
    if mode not in ("review", "auto"):
        raise HTTPException(400, "mode must be review or auto")
    opts = _check_opts({"vmode": vmode, "style": style or None, "aspect": aspect, "range": rng})
    if vmode == "visualizer" and cast_ids:
        raise HTTPException(400, "a visualizer has no people: don't pick cast members")
    if song_id:
        if not song_obj(song_id).has_audio():
            raise HTTPException(400, "that song has no audio yet")
        music_source = "library"
    music_source = music_source or "yue2"
    if music_source not in engine.MUSIC_SOURCES or (music_source == "library" and not song_id):
        raise HTTPException(400, "unknown music source")
    if not song_id and not brief.strip():
        raise HTTPException(400, "a brief is required when no song is chosen")
    cast_ids = list(dict.fromkeys(cast_ids or []))
    if len(cast_ids) > 2:
        raise HTTPException(400, "an MV has at most 2 members")
    try:
        chosen = [cast.member(c) for c in cast_ids]
    except ValueError as e:
        raise HTTPException(400, str(e))
    if len({m["name"] for m in chosen}) != len(chosen):
        raise HTTPException(400, "two cast members have the same name")
    p = engine.create_project(title, brief, mode, music_source, song_id, cast_ids, opts)
    ENGINE.submit(p.id, "concept")
    return {"id": p.id}


def _check_opts(o):
    if o.get("vmode", "stage") not in engine.VMODES:
        raise HTTPException(400, "unknown video mode")
    if o.get("aspect", "16:9") not in engine.ASPECTS:
        raise HTTPException(400, "unknown aspect ratio")
    if o.get("style") and o["style"] not in {s["id"] for s in engine.mv_styles()}:
        raise HTTPException(400, "unknown style preset")
    r = o.get("range", "full")
    if not (r in engine.RANGES or (isinstance(r, dict) and isinstance(r.get("bars"), list) and len(r["bars"]) == 2
                                   and all(isinstance(x, int) for x in r["bars"]))):
        raise HTTPException(400, "unknown song range")
    return o


@app.get("/api/mv_styles")
def mv_styles():
    return engine.mv_styles()


@app.post("/api/projects/{pid}/opts")
def set_opts(pid: str, rng: str | dict | None = Body(None, alias="range"), aspect: str = Body(None)):
    """Change the song range / aspect ratio of an existing MV; the page then redoes the shot design."""
    p = proj(pid)
    if jobs_for(pid):
        raise HTTPException(409, "this MV has a job running or queued: wait until it finishes")
    new = {k: v for k, v in {"range": rng, "aspect": aspect}.items() if v is not None}
    _check_opts(new)
    p.update(lambda s: s.__setitem__("opts", {**engine.DEFAULT_OPTS, **(s.get("opts") or {}), **new}))
    return {"opts": ENGINE.opts(p)}


@app.get("/api/projects/{pid}")
def project(pid: str, log_lines: int = 200):
    p = proj(pid)
    st = p.load()
    shots = p.jload("shots/shots.json", [])
    fidx = p.jload("shots/frames/index.json", {})
    cidx = p.jload("clips/index.json", {})
    for s in shots:
        s["frame_file"] = fidx.get(s["id"], {}).get("chosen")
        s["clip_file"] = cidx.get(s["id"], {}).get("chosen")
        s["frame_versions"] = [v["file"] for v in fidx.get(s["id"], {}).get("versions", [])]
        s["clip_versions"] = [v["file"] for v in cidx.get(s["id"], {}).get("versions", [])]
        s["edit"] = {k: v for k, v in st["overrides"].get(s["id"], {}).items() if k in engine.SHOT_EDIT_KEYS}
        s["qc_frame"] = st["qc"]["frames"].get(s["id"])
        s["qc_clip"] = st["qc"]["clips"].get(s["id"])
    refs = {}
    members = (p.jload("shots/members.json") or {}).get("members", {})
    in_cast = {(c.get("from", {}).get("project"), c["name"]): c["id"] for c in cast.list_cast()}
    for name, m in members.items():
        refs[name] = {"cands": sorted(f.name for f in (p.dir / "shots/refs").glob(f"{name}_cand*.png")),
                      "chosen": st["refs"].get(name),
                      "cast_id": m.get("cast_id") or in_cast.get((pid, name))}
    rows = {r["first_bar"]: r for r in p.jload("shots/design_rows.json", [])}
    for s in shots:   # start/end state chain from the shot design (older designs have none)
        r = rows.get(s["bars"][0]) or {}
        s["prev_state"], s["end_state"] = r.get("prev_state"), r.get("end_state")
    log = (p.dir / "agent.log")
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:] if log.exists() else []
    return {"state": st, "shots": shots, "refs": refs, "log": tail, "labels": engine.LABELS,
            "stages": engine.STAGES,
            "has_audio": (p.dir / "audio/song.wav").exists(),
            "plate": (p.dir / "shots/plates/stage.png").exists(),
            "plates": [f"shots/plates/{k}.png" for k in ENGINE.locations(p) if (p.dir / f"shots/plates/{k}.png").exists()]
            if st.get("concept") else [],
            "opts": ENGINE.opts(p), "post": ENGINE.post(p)}


@app.post("/api/projects/{pid}/delete")
def project_delete(pid: str):
    if not re.fullmatch(r"[\w-]{1,80}", pid):
        raise HTTPException(400, "bad project id")
    p = proj(pid)
    if jobs_for(pid):
        raise HTTPException(409, "this MV has a job running or queued: stop it first")
    return {"ok": True, "trash": to_trash("projects", p.dir, pid)}


@app.post("/api/projects/{pid}/approve/{stage}")
def approve(pid: str, stage: str):
    proj(pid)
    ENGINE.approve(pid, stage)
    return {"ok": True}


@app.post("/api/projects/{pid}/run/{stage}")
def run(pid: str, stage: str):
    proj(pid)
    if stage not in engine.STAGES:
        raise HTTPException(400, "unknown stage")
    ENGINE.submit(pid, stage)
    return {"ok": True}


@app.post("/api/projects/{pid}/mode")
def mode(pid: str, mode: str = Body(..., embed=True)):
    p = proj(pid)
    p.update(lambda s: s.__setitem__("mode", mode))
    return {"ok": True}


ACTIONS = {"regen_music", "regen_concept", "regen_refs", "regen_design", "regen_frame", "regen_clip", "assemble",
           "suno_download", "use_song", "animatic"}


# ---------- storyboard editor (board)
def _board_ctx(p):
    st = p.load()
    if not st.get("concept") or not (p.dir / "shots/design_rows.json").exists():
        raise HTTPException(409, "no storyboard yet: run the shot design step first")
    lights = {l["key"]: l["description"] for l in st["concept"]["lights"]}
    members = (p.jload("shots/members.json") or {}).get("members", {})
    return st, lights, members


@app.get("/api/projects/{pid}/board")
def board(pid: str):
    p = proj(pid)
    st, lights, members = _board_ctx(p)
    beats = p.jload("analysis/beats.json")
    lyr = design._bar_lyrics()(beats)
    shots = {tuple(s["bars"]): s for s in p.jload("shots/shots.json", [])}
    fidx, cidx = p.jload("shots/frames/index.json", {}), p.jload("clips/index.json", {})
    rows = p.jload("shots/design_rows.json", [])
    for r in rows:
        s = shots.get((r["first_bar"], r["last_bar"])) or {}
        r["sid"] = s.get("id")
        r["frame_file"] = fidx.get(s.get("id"), {}).get("chosen")
        r["clip_file"] = cidx.get(s.get("id"), {}).get("chosen")
    secs = beats["sections"]
    locs = ENGINE.locations(p)
    return {"rows": rows, "lights": lights, "members": list(members), "opts": ENGINE.opts(p),
            "locations": locs if len(locs) > 1 else {}, "range": ENGINE.bar_range(p, beats),
            "bars": [{"i": b["index"], "start": round(b["start"], 3), "end": round(b["end"], 3),
                      "section": secs[b["section_index"]]["name"], "vocal": b["vocal"],
                      "energy": round(b["energy"], 2), "lyric": lyr.get(b["index"], "")} for b in beats["bars"]],
            "proposal": st.get("board_proposal"), "animatic": st.get("animatic"),
            "busy": bool(jobs_for(pid))}


@app.post("/api/projects/{pid}/board")
def board_save(pid: str, rows: list[dict] = Body(..., embed=True)):
    p = proj(pid)
    st, lights, members = _board_ctx(p)
    locs = list(ENGINE.locations(p))
    locs = locs if len(locs) > 1 else None
    try:
        clean = [design.clean_board_row(r, lights, members, locs) for r in rows]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))
    beats = p.jload("analysis/beats.json")
    fixed, errors = design.validate(clean, beats, list(members), ENGINE.bar_range(p, beats), locs)
    if errors:
        raise HTTPException(400, "; ".join(errors[:8]))
    ENGINE.submit(pid, "apply_board", rows=clean)
    return {"ok": True, "changed": len(design.diff_rows(p.jload("shots/design_rows.json", []), fixed))}


@app.post("/api/projects/{pid}/board/chat")
def board_chat(pid: str, message: str = Body(..., embed=True)):
    p = proj(pid)
    _board_ctx(p)
    message = message.strip()[:2000]
    if not message:
        raise HTTPException(400, "empty request")
    if not brain.ready("design"):
        raise HTTPException(409, "no model for the shot design: set a Claude key or choose the local model")
    ENGINE.submit(pid, "board_chat", message=message)
    return {"ok": True}


@app.post("/api/projects/{pid}/choose")
def choose_version(pid: str, kind: str = Body(...), sid: str = Body(...), file: str = Body(...)):
    """Pick which generated version of a first frame / clip a shot uses (every version is kept)."""
    p = proj(pid)
    rel = {"frames": "shots/frames/index.json", "clips": "clips/index.json"}.get(kind)
    if not rel:
        raise HTTPException(400, "kind must be frames or clips")
    with p.lock:
        idx = p.jload(rel, {})
        if sid not in idx or file not in [v["file"] for v in idx[sid].get("versions", [])]:
            raise HTTPException(400, "unknown shot or version")
        idx[sid]["chosen"] = file
        (p.dir / rel).write_text(json.dumps(idx, indent=1, ensure_ascii=False), encoding="utf-8")
    p.update(lambda s: s["qc"][kind].pop(sid, None))   # the QC result was for the other version
    return {"ok": True}


@app.post("/api/projects/{pid}/shot_edit")
def shot_edit(pid: str, sid: str = Body(...), offset: float = Body(None), trans: str = Body(None)):
    """Per-shot editing for the cut: start offset into the clip (seconds) and the transition into the shot."""
    p = proj(pid)
    if trans is not None and trans not in ("cut", "flash", "dip", "fade"):
        raise HTTPException(400, "unknown transition")

    def f(s):
        e = s["overrides"].setdefault(sid, {})
        if offset is not None:
            e["offset"] = max(0.0, min(float(offset), 5.0))
        if trans is not None:
            e["trans"] = trans
    p.update(f)
    return {"ok": True}


@app.post("/api/projects/{pid}/post")
def set_post(pid: str, post: dict = Body(..., embed=True)):
    """Post-production settings used by the next cut (captions, music-driven effects, grade, upscale)."""
    p = proj(pid)
    cap, fx = post.get("captions") or {}, post.get("fx") or {}
    clean = {"captions": {"on": bool(cap.get("on")), "style": cap.get("style", "classic")},
             "fx": {"pulse": max(0.0, min(float(fx.get("pulse") or 0), 1.0)),
                    "punch": max(0.0, min(float(fx.get("punch") or 0), 1.0)), "where": fx.get("where", "all")},
             "grade": post.get("grade", "none"), "upscale": bool(post.get("upscale"))}
    if clean["captions"]["style"] not in ("classic", "bold", "minimal") or clean["fx"]["where"] not in \
            ("all", "chorus", "high") or clean["grade"] not in ("none", "warm", "cool", "tealorange", "bw",
                                                                 "vintage", "contrast"):
        raise HTTPException(400, "unknown post-production option")
    p.update(lambda s: s.__setitem__("post", clean))
    return {"post": clean}


@app.post("/api/projects/{pid}/board/discard")
def board_discard(pid: str):
    p = proj(pid)
    p.update(lambda s: s.pop("board_proposal", None))
    return {"ok": True}


@app.post("/api/projects/{pid}/action")
def action(pid: str, task: str = Body(...), sid: str = Body(None), prompt: str = Body(None),
           motion: str = Body(None), clip_id: str = Body(None), confirm: bool = Body(False),
           song_id: str = Body(None)):
    proj(pid)
    if task not in ACTIONS:
        raise HTTPException(400, "unknown action")
    if task == "use_song" and not song_obj(song_id).has_audio():
        raise HTTPException(400, "that song has no audio yet")
    if task == "suno_download" and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", clip_id or ""):
        raise HTTPException(400, "bad clip id")
    kw = {k: v for k, v in {"sid": sid, "prompt": prompt, "motion": motion, "clip_id": clip_id,
                            "confirm": confirm, "song_id": song_id}.items() if v}
    ENGINE.submit(pid, task, **kw)
    return {"ok": True}


@app.post("/api/projects/{pid}/concept")
def edit_concept(pid: str, concept: dict = Body(..., embed=True)):
    p = proj(pid)
    p.update(lambda s: s.__setitem__("concept", concept))
    ENGINE.write_concept_files(p)
    return {"ok": True}


@app.post("/api/projects/{pid}/pick_ref")
def pick_ref(pid: str, name: str = Body(...), k: int = Body(...)):
    p = proj(pid)
    ENGINE.pick_ref(p, name, k)
    return {"ok": True}


# ---------- local LLM (Unsloth Studio) instead of Claude, per task

@app.get("/api/llm")
def llm_get():
    return {"config": llm_local.public_cfg(), "status": llm_local.status(), "tasks": llm_local.TASKS}


@app.post("/api/llm")
def llm_save(config: dict = Body(..., embed=True)):
    return {"config": llm_local.save_cfg(config)}


@app.get("/api/llm/models")
def llm_models():
    try:
        return llm_local.models()
    except RuntimeError as e:
        raise HTTPException(502, str(e))


def _gpu_free():
    if ENGINE.current:
        raise HTTPException(409, "a GPU job is running: try again when the queue is idle")


@app.post("/api/llm/test")
def llm_test():
    _gpu_free()   # loading the model stops ComfyUI
    try:
        return llm_local.test()
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.post("/api/llm/unload")
def llm_unload():
    _gpu_free()
    cfg = llm_local.load_cfg()
    try:
        return llm_local._req("/v1/unload", {"model_path": cfg["model"], "force_cancel_active": True}, timeout=120)
    except RuntimeError as e:
        raise HTTPException(502, str(e))


# ---------- cast library (members reused across MVs)

@app.get("/api/cast")
def cast_list():
    return cast.list_cast()


@app.post("/api/cast/save")
def cast_save(pid: str = Body(...), name: str = Body(...)):
    """Save a project member with a chosen reference portrait to the cast library."""
    p = proj(pid)
    st = p.load()
    m = next((m for m in (st.get("concept") or {}).get("members", []) if m["name"] == name), None)
    ref = p.dir / f"shots/refs/{name}.png"
    if not m or not st["refs"].get(name) or not ref.exists():
        raise HTTPException(400, "choose a reference portrait for this member first")
    m = dict(m)
    m.update({k: v for k, v in ((p.jload("shots/members.json") or {}).get("members", {}).get(name) or {}).items()
              if k in cast.FIELDS})   # the edited look in members.json wins
    m["name"] = name
    return cast.save_from_project(pid, st["title"], m, ref)


@app.post("/api/cast/{cid}/delete")
def cast_delete(cid: str):
    try:
        d = cast.ref_path(cid).parent
    except ValueError:
        raise HTTPException(400, "bad cast id")
    if not (d / "cast.json").exists():
        raise HTTPException(404, "no such cast member")
    return {"ok": True, "trash": to_trash("cast", d, cid)}


@app.get("/castfiles/{cid}/ref.png")
def cast_ref(cid: str):
    try:
        f = cast.ref_path(cid)
    except ValueError:
        raise HTTPException(400, "bad cast id")
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


# ---------- ComfyUI workflows (library + per-project choice)

@app.get("/api/workflows")
def wf_library():
    return {"roles": workflows.roles(), "library": workflows.library()}


@app.post("/api/workflows/inspect")
def wf_inspect(role: str = Body(...), workflow: dict = Body(...)):
    if role not in workflows.wb.ROLES:
        raise HTTPException(400, "unknown role")
    return workflows.inspect(workflow, role)


@app.get("/api/workflows/{lib_id}")
def wf_get(lib_id: str):
    try:
        e = workflows.entry(lib_id)
    except KeyError:
        raise HTTPException(404, "no such workflow")
    return {"entry": e, **workflows.inspect(workflows.workflow_of(e), e["role"])}


@app.post("/api/workflows/save")
def wf_save(name: str = Body(...), role: str = Body(...), bind: dict = Body(...), workflow: dict = Body(None),
            fixed: dict = Body(None), fps: float = Body(24), frame_multiple: int = Body(1), id: str = Body(None)):
    if workflow is None:
        if not id or id.startswith("builtin:"):
            raise HTTPException(400, "workflow JSON required")
        workflow = workflows.workflow_of(workflows.entry(id))
    try:
        return workflows.save(name, role, workflow, bind, fixed, fps, frame_multiple,
                              None if (id or "").startswith("builtin:") else id)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/workflows/remove")
def wf_remove(id: str = Body(..., embed=True)):
    if id.startswith("builtin:"):
        raise HTTPException(400, "built-in workflows cannot be removed")
    workflows.remove(id)
    return {"ok": True}


@app.get("/api/projects/{pid}/workflows")
def wf_project(pid: str):
    return workflows.project_selection(proj(pid).dir)


@app.post("/api/projects/{pid}/workflows")
def wf_project_set(pid: str, role: str = Body(...), id: str = Body(...)):
    p = proj(pid)
    try:
        workflows.set_project_role(p.dir, role, id)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    p.log(f"workflow: {role} -> {workflows.entry(id)['name']}")
    return workflows.project_selection(p.dir)


@app.get("/files/{pid}/{path:path}")
def files(pid: str, path: str):
    p = proj(pid)
    f = (p.dir / path).resolve()
    if p.dir.resolve() not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ---------- song source: local YuE2 / Suno / uploaded file

@app.post("/api/projects/{pid}/music_source")
def music_source(pid: str, source: str = Body(..., embed=True)):
    p = proj(pid)
    if source not in engine.MUSIC_SOURCES:
        raise HTTPException(400, "unknown music source")
    p.update(lambda s: s["music"].__setitem__("source", source))
    p.log(f"music: source -> {source}")
    return {"ok": True}


AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}


@app.post("/api/projects/{pid}/upload_audio")
async def upload_audio(pid: str, request: Request, name: str = "song.mp3"):
    p = proj(pid)
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, f"unsupported audio type {ext or '(none)'}")
    safe = (re.sub(r"[^\w.-]+", "_", stem).strip("._") or "song")[:60] + ext
    d = p.dir / "music" / f"upload_{time.strftime('%Y%m%d_%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(d / safe, "wb") as fh:
        async for chunk in request.stream():
            size += len(chunk)
            if size > 300 * 1024 * 1024:
                raise HTTPException(413, "file too large (300 MB max)")
            fh.write(chunk)
    rel = (d / safe).relative_to(p.dir).as_posix()
    p.log(f"music: uploaded {name} ({size // 1024} KB)")
    ENGINE.submit(pid, "import_audio", path=rel)
    return {"ok": True, "path": rel}


_suno_cache = {"t": 0, "data": None}


@app.get("/api/suno")
def suno_status(refresh: bool = False):
    if not suno_api.signed_in():
        return {"signed_in": False}
    if refresh or time.time() - _suno_cache["t"] > 30 or not _suno_cache["data"]:
        try:
            u = suno_api.call("account-usage")
            a = u.get("suno_account", {})
            _suno_cache["data"] = {"plan": (a.get("plan") or {}).get("name"), "credits": a.get("credits_remaining"),
                                   "download_credits": a.get("download_credits_remaining"),
                                   "models": u.get("allowed_models")}
            _suno_cache["t"] = time.time()
        except suno_api.SunoError as e:
            if e.data.get("reason") == "not_signed_in":
                return {"signed_in": False, "error": str(e)}
            return {"signed_in": True, "error": str(e)}
    return dict(_suno_cache["data"], signed_in=True)


@app.get("/api/suno/login")
def suno_login():
    try:
        return {"url": suno_api.login_url(suno_api.REDIRECTS[0])}
    except suno_api.SunoError as e:
        raise HTTPException(502, str(e))


@app.get("/api/suno/callback", response_class=HTMLResponse)
def suno_callback(code: str = None, state: str = None, error: str = None):
    page = ("<!doctype html><meta charset=utf-8><body style='font:16px sans-serif;background:#0e0f14;color:#e6e7ee;"
            "padding:40px'><p>{}</p><script>setTimeout(()=>window.close(),1500)</script>")
    if error or not code:
        return page.format(f"Suno 登录未完成 / Suno sign-in not completed: {error or 'no code'}")
    try:
        suno_api.finish_login(code, state)
    except suno_api.SunoError as e:
        return page.format(f"Suno 登录失败 / Suno sign-in failed: {e}")
    _suno_cache["t"] = 0
    return page.format("已登录 Suno，可以关闭此页 / Signed in to Suno - you can close this tab.")


@app.post("/api/suno/logout")
def suno_logout():
    suno_api.logout()
    _suno_cache["data"] = None
    return {"ok": True}


# ---------- music studio (song library, independent of MV projects)

def song_obj(sid):
    try:
        so = studio.Song(sid)
    except ValueError:
        raise HTTPException(400, "bad song id")
    if not so.exists():
        raise HTTPException(404, "no such song")
    return so


def song_busy(sid):
    jobs = ([ENGINE.current] if ENGINE.current else []) + ENGINE.queued()
    return any(j[0] == f"song:{sid}" for j in jobs)


# ---------------------------------------------------------------- music categories
# Built-in list (data/genres_builtin.json). Spotify's own categories were dropped from the UI: since Feb 2026 Spotify
# returns 403 on /browse/categories for Development Mode apps. scripts/spotify_genres.py still works from the CLI.


def genre_obj(gid):
    if not gid:
        return None
    g = next((c for c in spotify_genres.all_categories() if c["id"] == gid), None)
    if not g:
        raise HTTPException(400, "unknown category")
    return {k: g.get(k) for k in ("id", "name", "name_zh", "style", "source")}


@app.get("/api/genres")
def genres():
    return {"categories": spotify_genres.all_categories()}


@app.get("/api/song_options")
def song_options():
    return {"options": studio.OPTIONS, "yue": {k: list(v) for k, v in studio.YUE_CHOICES.items()},
            "yue_defaults": studio.YUE_DEFAULTS}


@app.get("/api/songs")
def songs():
    return studio.list_songs()


@app.post("/api/songs")
def song_create(brief: str = Body(""), engine_: str = Body("yue2", alias="engine"), title: str = Body(""),
                style: str = Body(""), lyrics: str = Body(""), instrumental: bool = Body(False),
                genre: str = Body(""), draft: bool = Body(None)):
    if engine_ not in ("yue2", "suno"):
        raise HTTPException(400, "engine must be yue2 or suno")
    g = genre_obj(genre)
    if draft is None:
        draft = bool(brief.strip()) and not lyrics.strip()
    if g and not draft and not style.strip():   # blank song: start from the category's style tags
        style = g.get("style") or ""
    so = studio.create_song(title, brief, engine_, style, lyrics, instrumental, g)
    if draft:   # otherwise a blank song for the user's own lyrics
        so.set(status="drafting")
        ENGINE.submit(f"song:{so.id}", "draft")
    return {"id": so.id}


@app.get("/api/songs/{sid}")
def song_get(sid: str, log_lines: int = 120):
    so = song_obj(sid)
    log = so.dir / "song.log"
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:] if log.exists() else []
    used_by = [p["id"] for p in engine.list_projects()
               if (engine.Project(p["id"]).load()["music"].get("song_id") == sid)]
    jobs = ([ENGINE.current] if ENGINE.current else []) + ENGINE.queued()
    return {"state": so.load(), "has_audio": so.has_audio(), "log": tail, "busy": song_busy(sid),
            "cover_busy": (f"song:{sid}", "cover") in jobs, "has_cover": (so.dir / "cover.png").exists(),
            "used_by": used_by}


@app.post("/api/songs/{sid}")
def song_edit(sid: str, title: str = Body(None), style: str = Body(None), lyrics: str = Body(None),
              engine_: str = Body(None, alias="engine"), brief: str = Body(None), instrumental: bool = Body(None),
              genre: str = Body(None), settings: dict = Body(None), yue: dict = Body(None),
              style_custom: bool = Body(None), seed: int = Body(None), suno_pick: str = Body(None)):
    so = song_obj(sid)
    if suno_pick is not None:   # the Suno take the user chose (to download on suno.com and import)
        if suno_pick and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", suno_pick):
            raise HTTPException(400, "bad clip id")
        so.update(lambda st: (st.get("suno") or {}).__setitem__("pick", suno_pick or None))
    if genre is not None:
        so.set(genre=genre_obj(genre))
    if settings is not None:
        so.set(settings=studio.clean_settings(settings))
    if yue is not None:
        so.set(yue=studio.clean_yue(yue))
    if style_custom is not None:
        so.set(style_custom=style_custom)
    if seed is not None:
        if not 0 <= seed < 2**31:
            raise HTTPException(400, "seed must be 0 .. 2147483647")
        so.set(seed=seed)
    if engine_ is not None and engine_ not in ("yue2", "suno"):
        raise HTTPException(400, "engine must be yue2 or suno")
    kw = {k: v for k, v in {"title": title, "style": style, "lyrics": lyrics, "engine": engine_,
                            "brief": brief, "instrumental": instrumental}.items() if v is not None}
    so.set(**kw)
    return {"ok": True}


@app.post("/api/songs/{sid}/delete")
def song_delete(sid: str):
    so = song_obj(sid)
    if song_busy(sid):
        raise HTTPException(409, "this song has a job running or queued: stop it first")
    # MV projects keep their own copy of the audio/score, so they still work without the library song
    return {"ok": True, "trash": to_trash("songs", so.dir, sid)}


@app.post("/api/songs/{sid}/run")
def song_run(sid: str, task: str = Body(...), clip_id: str = Body(None), confirm: bool = Body(False),
             new_seed: bool = Body(False), prompt: str = Body(None)):
    so = song_obj(sid)
    if song_busy(sid):
        raise HTTPException(409, "this song already has a job running or queued")
    if task == "draft":
        st = so.load()
        if not st["brief"].strip() and not st.get("genre"):
            raise HTTPException(400, "the song has no brief or category")
        so.set(status="drafting", msg="")
        ENGINE.submit(f"song:{sid}", "draft")
    elif task == "generate":
        if so.load()["engine"] not in ("yue2", "suno"):
            raise HTTPException(400, "choose YuE2 or Suno first")
        ENGINE.submit(f"song:{sid}", "generate", new_seed=new_seed)
    elif task == "cover":   # (re)make the cover art; prompt = the user's own image prompt (else Claude writes one)
        if prompt is not None and len(prompt) > 2000:
            raise HTTPException(400, "prompt too long")
        so.set(cover_error=None)
        ENGINE.submit(f"song:{sid}", "cover", prompt=(prompt or "").strip() or None)
    elif task == "suno_download":
        if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", clip_id or ""):
            raise HTTPException(400, "bad clip id")
        ENGINE.submit(f"song:{sid}", "suno_download", clip_id=clip_id, confirm=confirm)
    else:
        raise HTTPException(400, "unknown task")
    so.log(f"queued: {task}")
    return {"ok": True}


async def _save_upload(request, so, name):
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    safe = (re.sub(r"[^\w.-]+", "_", stem).strip("._") or "song")[:60] + ext
    d = so.dir / "music" / f"upload_{time.strftime('%Y%m%d_%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(d / safe, "wb") as fh:
        async for chunk in request.stream():
            size += len(chunk)
            if size > 300 * 1024 * 1024:
                raise HTTPException(413, "file too large (300 MB max)")
            fh.write(chunk)
    so.log(f"uploaded {name} ({size // 1024} KB)")
    return (d / safe).relative_to(so.dir).as_posix()


@app.post("/api/songs/{sid}/import")
async def song_import_into(sid: str, request: Request, name: str = "song.mp3", clip_id: str = None):
    """Audio for an existing song, e.g. the Suno take the user picked and downloaded on suno.com themselves."""
    so = song_obj(sid)
    if Path(name).suffix.lower() not in AUDIO_EXT:
        raise HTTPException(400, f"unsupported audio type {Path(name).suffix or '(none)'}")
    if clip_id and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", clip_id):
        raise HTTPException(400, "bad clip id")
    if song_busy(sid):
        raise HTTPException(409, "this song already has a job running or queued")
    path = await _save_upload(request, so, name)
    so.set(status="generating", msg="", needs=None)
    ENGINE.submit(f"song:{sid}", "import", path=path, clip_id=clip_id)
    return {"ok": True}


@app.post("/api/song_import")
async def song_import(request: Request, name: str = "song.mp3", title: str = ""):
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, f"unsupported audio type {ext or '(none)'}")
    so = studio.create_song(title or stem, "", "upload")
    safe = (re.sub(r"[^\w.-]+", "_", stem).strip("._") or "song")[:60] + ext
    d = so.dir / "music" / f"upload_{time.strftime('%Y%m%d_%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(d / safe, "wb") as fh:
        async for chunk in request.stream():
            size += len(chunk)
            if size > 300 * 1024 * 1024:
                raise HTTPException(413, "file too large (300 MB max)")
            fh.write(chunk)
    so.set(status="generating", msg="")
    so.log(f"uploaded {name} ({size // 1024} KB)")
    ENGINE.submit(f"song:{so.id}", "import", path=(d / safe).relative_to(so.dir).as_posix())
    return {"id": so.id}


@app.get("/songfiles/{sid}/{path:path}")
def song_files(sid: str, path: str):
    so = song_obj(sid)
    f = (so.dir / path).resolve()
    if so.dir.resolve() not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)
