"""Workflow library for the web agent.

Library  : the built-in workflows (scripts/wf_bindings.DEFAULTS) + user uploads stored as
           workflows/user/<id>.json with their bindings in workflows/library.json.
Project  : projects/<id>/workflows/bindings.json maps a role to a library entry (a copy of its binding with
           "file" pointing at a copy of the workflow inside the project). No entry = built-in default.
"""
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import wf_bindings as wb  # noqa: E402

LIB = ROOT / "workflows" / "library.json"
USER_DIR = ROOT / "workflows" / "user"


def _lib():
    return json.loads(LIB.read_text(encoding="utf-8")) if LIB.exists() else {"entries": {}}


def _save_lib(lib):
    LIB.write_text(json.dumps(lib, indent=1, ensure_ascii=False), encoding="utf-8")


def roles():
    return {r: {"label": v["label"], "kind": v["kind"],
                "params": [{"key": k, "required": req, "label": lab} for k, req, lab in wb.params(r)]}
            for r, v in wb.ROLES.items()}


def library():
    out = [{"id": f"builtin:{r}", "role": r, "builtin": True, **b} for r, b in wb.DEFAULTS.items()]
    out += [{"id": i, "builtin": False, **e} for i, e in _lib()["entries"].items()]
    return out


def entry(lib_id):
    for e in library():
        if e["id"] == lib_id:
            return e
    raise KeyError(lib_id)


def workflow_of(e):
    return json.loads((ROOT / e["file"]).read_text(encoding="utf-8"))


def inspect(wf, role):
    """For the mapping UI: validity, suggested binding and every literal node input."""
    if not wb.is_api_workflow(wf):
        return {"ok": False, "errors": ["不是 API 格式的工作流。请在 ComfyUI 里用 Export (API) 导出（普通保存的 JSON 含 nodes/links，不能直接提交）。"]}
    return {"ok": True, "suggest": wb.suggest(wf, role), "inputs": wb.scalar_inputs(wf),
            "nodes": len(wf), "errors": []}


def save(name, role, wf, bind, fixed=None, fps=24, frame_multiple=1, lib_id=None):
    if role not in wb.ROLES:
        raise ValueError(f"unknown role {role}")
    b = {"name": name.strip() or role, "role": role, "bind": {k: list(v) for k, v in bind.items() if v},
         "fixed": fixed or {}, "fps": fps, "frame_multiple": frame_multiple}
    errs = wb.validate(wf, b, role)
    if errs:
        return {"ok": False, "errors": errs}
    lib = _lib()
    if not lib_id:
        slug = re.sub(r"[^a-z0-9]+", "_", b["name"].lower()).strip("_")[:24] or "wf"
        lib_id = f"{slug}_{time.strftime('%Y%m%d_%H%M%S')}"
    elif lib_id not in lib["entries"]:
        raise KeyError(lib_id)
    USER_DIR.mkdir(parents=True, exist_ok=True)
    f = USER_DIR / f"{lib_id}.json"
    f.write_text(json.dumps(wf, indent=1, ensure_ascii=False), encoding="utf-8")
    b["file"] = f.relative_to(ROOT).as_posix()
    b["t"] = time.time()
    lib["entries"][lib_id] = b
    _save_lib(lib)
    return {"ok": True, "id": lib_id}


def remove(lib_id):
    """Drop a user entry from the library (its JSON file is kept; projects keep their own copy)."""
    lib = _lib()
    lib["entries"].pop(lib_id, None)
    _save_lib(lib)


# ---------- per project

def _pfile(pdir):
    return Path(pdir) / wb.BINDINGS_FILE


def project_selection(pdir):
    data = json.loads(_pfile(pdir).read_text(encoding="utf-8")) if _pfile(pdir).exists() else {}
    return {r: (data[r].get("library_id") if r in data else f"builtin:{r}") for r in wb.ROLES}


def set_project_role(pdir, role, lib_id):
    pdir = Path(pdir)
    e = entry(lib_id)
    if e["role"] != role:
        raise ValueError(f"workflow {lib_id} is for role {e['role']}, not {role}")
    data = json.loads(_pfile(pdir).read_text(encoding="utf-8")) if _pfile(pdir).exists() else {}
    if e["builtin"]:
        data.pop(role, None)
        # projects created before a built-in workflow existed get a copy
        dest = pdir / e["file"]
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / e["file"], dest)
    else:
        dest = pdir / "workflows" / f"user_{lib_id}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / e["file"], dest)
        data[role] = {k: e[k] for k in ("name", "bind", "fixed", "fps", "frame_multiple")}
        # optional: est. seconds per clip and per-ComfyUI-session budget (engine batching)
        data[role].update({k: e[k] for k in ("est_seconds", "chunk_budget") if k in e})
        data[role].update(file=dest.relative_to(pdir).as_posix(), library_id=lib_id)
    _pfile(pdir).parent.mkdir(parents=True, exist_ok=True)
    _pfile(pdir).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
