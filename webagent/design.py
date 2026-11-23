"""Turn Claude's shot rows into a shots/shot_design.py that scripts/build_shots.py understands.

The prompt templates carry the rules learned on the RESCUE production (stage v2): members stand ON
the stage, close-ups keep hands out of frame, mediums keep arms relaxed, no microphones, no dancing.
"""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CU = ", framed from the chest up, hands out of frame, no microphone, mouth clearly visible"
MED = ", framed from the waist up, arms relaxed, empty hands, no microphone, mouth clearly visible"
MED2 = ", framed from the waist up, arms relaxed, empty hands, no microphones, faces clearly visible and sharp"
HANDS_CU = ", hands stay out of frame"
HANDS_MED = ", arms stay relaxed with very little hand movement, no dancing"


def _bar_lyrics():
    spec = importlib.util.spec_from_file_location("build_shots", ROOT / "scripts" / "build_shots.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.bar_lyrics


def bars_text(beats):
    lyr = _bar_lyrics()(beats)
    secs = beats["sections"]
    lines = []
    for b in beats["bars"]:
        s = secs[b["section_index"]]
        name = s["name"] + (f" ({s['delivery']})" if s.get("delivery") else "")
        lines.append(f"{b['index']}\t{name}\t{'vocal' if b['vocal'] else '-'}\t{b['energy']:.2f}\t{lyr.get(b['index'], '')}")
    return "\n".join(lines)


def _esc(text):
    return text.replace("{", "(").replace("}", ")")


def _placeholders(text, names):
    text = _esc(text)
    for n in sorted(names, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(n)}\b", "{" + n + "}", text)
    return text


def _motion(text, members_info):
    for n, m in sorted(members_info.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{re.escape(n)}\b", m.get("video_desc") or f"the {m.get('noun', 'woman')}", text)
    return text


def validate(rows, beats, members):
    """Return (fixed_rows, errors). Small problems are fixed, structural ones reported."""
    vocal = {b["index"]: b["vocal"] for b in beats["bars"]}
    n_bars = len(beats["bars"])
    errors, fixed = [], []
    rows = sorted(rows, key=lambda r: r["first_bar"])
    expect = 0
    for r in rows:
        if r["first_bar"] != expect:
            errors.append(f"row starting at bar {r['first_bar']}: expected it to start at bar {expect} "
                          f"(gap or overlap)")
        if r["last_bar"] < r["first_bar"]:
            errors.append(f"row {r['first_bar']}: last_bar < first_bar")
        expect = r["last_bar"] + 1
        unknown = [m for m in r["members"] if m not in members]
        if unknown:
            errors.append(f"row {r['first_bar']}: unknown members {unknown}")
        need = {"solo": 1, "duo": 2, "stage_wide": 2, "back_view": 2, "empty": 0}[r["kind"]]
        if len(members) >= need and len(r["members"]) != need:
            errors.append(f"row {r['first_bar']}: kind {r['kind']} needs {need} members, got {r['members']}")
        r = dict(r)
        if r["kind"] in ("stage_wide", "back_view"):
            r["size"] = "wide"
        if r["lipsync"] and (r["lipsync"] not in r["members"] or r["kind"] in ("stage_wide", "back_view", "empty")):
            r["lipsync"] = None
        if r["lipsync"] and not any(vocal.get(i) for i in range(r["first_bar"], r["last_bar"] + 1)):
            r["lipsync"] = None
        fixed.append(r)
    if expect != n_bars:
        errors.append(f"rows end at bar {expect - 1}, but the song has bars 0..{n_bars - 1}")
    return fixed, errors


def frame_prompt(r, lights, members_info):
    names = list(members_info)
    light = lights.get(r["light"], r["light"])
    action = _placeholders(r["action"], r["members"])
    one = r["members"][0] if r["members"] else None
    pron = "his" if one and members_info[one].get("noun") == "man" else "her"
    k = r["kind"]
    if k == "solo":
        tail = CU if r["size"] in ("close-up", "medium close-up") else MED
        if "{" + one + "}" not in action:
            action = "{" + one + "} " + action
        return f"{action}, standing on the raised stage, the stage floor under {pron} feet and the back wall close behind {pron}, {light}{tail}"
    if k == "duo":
        a, b = r["members"][:2]
        if "{" + a + "}" not in action:
            action = "{" + a + "} and {" + b + "} " + action
        return f"{action}, both standing on the raised stage, the stage floor under their feet and the back wall close behind them, {light}{MED2}"
    if k == "stage_wide":
        a, b = r["members"][:2]
        return (f"Wide shot from the crowd of {{{a}}} and {{{b}}} standing side by side on the raised stage, {action}, "
                f"{light}, the stage floor and the back wall around them, silhouettes of the audience's heads at the "
                f"bottom of the frame")
    if k == "back_view":
        a, b = r["members"][:2]
        return (f"{{{a}}} and {{{b}}} seen from behind them at the back of the stage, both facing a huge crowd below "
                f"the stage, their backs to the camera, {action}, {light}")
    # empty insert: names of members may appear as small figures; keep them as plain text
    return _esc(r["action"]) + f", {light}"


def motion_prompt(r, members_info):
    m = _motion(r["motion"], members_info)
    k = r["kind"]
    if k == "solo":
        return m + (HANDS_CU if r["size"] in ("close-up", "medium close-up") else HANDS_MED)
    if k == "duo":
        return m + HANDS_MED
    if k in ("stage_wide", "back_view"):
        return m + ", the performers stand still on the stage, no dancing"
    return m + ", no people on the stage"


def write_design(path, rows, plate, lights, members_info):
    lines = ['# Generated by the MV web agent (webagent/design.py). Same format as shots/shot_design.py.',
             f"LOCATIONS = {{'stage': {plate!r}}}", "DESIGN = {'all': ["]
    for r in rows:
        mem = tuple(r["members"])
        lines.append(f" ({r['first_bar']}, {r['last_bar']}, {mem!r}, {r['lipsync']!r}, {r['size']!r},")
        lines.append(f"  {frame_prompt(r, lights, members_info)!r},")
        lines.append(f"  {motion_prompt(r, members_info)!r}),")
    lines.append("]}")
    lines.append("LOCATION_BY_BAR = {r[0]: 'stage' for r in DESIGN['all']}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_rows(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
