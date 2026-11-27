"""Reusable cast library: members whose reference portrait was confirmed in one MV can star in later MVs.

cast/<id>/cast.json  {id, name, noun, look, signature_color, video_desc, created, from: {project, title}, used_in: [pid]}
cast/<id>/ref.png    the confirmed reference portrait (identity anchor for every Qwen edit)

A project that uses cast members keeps their name, look and portrait exactly (the concept is designed around them and
the refs stage copies the portrait instead of generating candidates), so the same faces appear in every video.
"""
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAST = ROOT / "cast"
FIELDS = ("name", "noun", "look", "signature_color", "video_desc")
ID_RE = re.compile(r"[\w-]{1,80}")


def _dir(cid):
    if not ID_RE.fullmatch(cid or ""):
        raise ValueError("bad cast id")
    return CAST / cid


def get(cid):
    f = _dir(cid) / "cast.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _write(c):
    d = _dir(c["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "cast.json").write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")


def ref_path(cid):
    return _dir(cid) / "ref.png"


def list_cast():
    out = []
    for f in sorted(CAST.glob("*/cast.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (f.parent / "ref.png").exists():
            c["t"] = int((f.parent / "ref.png").stat().st_mtime)
            out.append(c)
    return sorted(out, key=lambda c: -c.get("created", 0))


def save_from_project(pid, title, member, ref_png):
    """member: the concept's member dict. Saving the same member from the same project again updates that entry."""
    existing = next((c for c in list_cast() if c.get("from", {}).get("project") == pid
                     and c["name"] == member["name"]), None)
    if existing:
        c = existing
        c.pop("t", None)
    else:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", member["name"]).strip("_")[:24] or "member"
        c = {"id": f"{slug}_{time.strftime('%Y%m%d_%H%M%S')}", "created": time.time(),
             "from": {"project": pid, "title": title}, "used_in": []}
    c.update({k: member.get(k, "") for k in FIELDS})
    _write(c)
    shutil.copyfile(ref_png, ref_path(c["id"]))
    return c


def mark_used(cid, pid):
    c = get(cid)
    if c and pid not in c.setdefault("used_in", []):
        c["used_in"].append(pid)
        _write(c)


def member(cid):
    """The concept member dict for a cast entry (what brain.concept and the pipeline expect)."""
    c = get(cid)
    if not c:
        raise ValueError(f"cast member {cid} no longer exists")
    return dict({k: c.get(k, "") for k in FIELDS}, cast_id=cid)
