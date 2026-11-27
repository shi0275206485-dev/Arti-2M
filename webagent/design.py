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

# ---- continuity rules adapted from Toonflow's episode-director method (github.com/HBAI-Ltd/Toonflow-app):
# * every cut must change something visible (subject, shot size by >= 2 steps, or camera-angle family), otherwise
#   two independently generated clips meet like a glitchy jump cut;
# * fixed world positions: the first concept member always stands on the audience's left; the screen side is
#   derived from the camera (a back view mirrors it) instead of being left to the model;
# * first-frame lock (gaze, who is the only person in frame) and only targeted "avoid" phrases for real risks.
SIZES = ["close-up", "medium close-up", "medium", "wide"]
ANGLE_FAMILY = {"front": "front", "three-quarter": "front", "side": "side", "low": "low", "high": "high"}
ANGLE_TEXT = {"front": "frontal camera at eye level", "three-quarter": "three-quarter view at eye level",
              "side": "side profile view", "low": "low-angle shot looking up from the stage edge",
              "high": "high-angle shot looking down"}
LIPSYNC_ANGLES = {"front", "three-quarter", "low"}   # audio-driven lip-sync needs a readable mouth


def subject(r):
    return r["kind"], tuple(sorted(r["members"]))


def cut_ok(a, b):
    """True when the cut a -> b changes the subject, the size by >= 2 steps or the camera-angle family."""
    if subject(a) != subject(b):
        return True
    if abs(SIZES.index(a["size"]) - SIZES.index(b["size"])) >= 2:
        return True
    return ANGLE_FAMILY[a.get("angle", "front")] != ANGLE_FAMILY[b.get("angle", "front")]


def fix_cut(prev, r):
    """Make r contrast with prev by changing only HOW it is filmed, never what happens: solo shots switch between
    close-up and medium, otherwise the camera angle changes. Returns a note, or None if nothing fits."""
    if r["kind"] == "solo":
        alt = "medium" if SIZES.index(prev["size"]) <= 1 else "close-up"
        if abs(SIZES.index(alt) - SIZES.index(prev["size"])) >= 2:
            r["size"] = alt
            return f"size -> {alt}"
    fam = ANGLE_FAMILY[prev.get("angle", "front")]
    for ang in (["low", "front"] if r.get("lipsync") else ["side", "low", "front", "high"]):
        if ANGLE_FAMILY[ang] != fam and (r["kind"] in ("solo", "duo") or ang == "front"):
            r["angle"] = ang
            return f"angle -> {ang}"
    return None


def fix_cuts(rows):
    """Repair cuts that would read as jump cuts (see cut_ok). Changes rows in place, returns notes for the log."""
    notes = []
    for prev, r in zip(rows, rows[1:]):
        if not cut_ok(prev, r):
            what = fix_cut(prev, r)
            notes.append(f"bar {r['first_bar']}: same {r['kind']} {'/'.join(r['members'])} as the shot before at "
                         f"{prev['size']}: {what or 'could not fix'}")
    return notes


def state_chain(rows):
    """Toonflow-style state chain: for each row, the end_state of each member's latest earlier row (where the cut
    has to pick them up; one text when they were last seen together). Sets r["prev_state"] (None = first
    appearance / empty insert)."""
    last = {}   # member -> (row index, end_state)
    for i, r in enumerate(rows):
        seen = sorted({last[m] for m in r["members"] if m in last})
        r["prev_state"] = " / ".join(s for _, s in seen) or None
        if r.get("end_state"):
            for m in r["members"]:
                last[m] = (i, r["end_state"])
    return rows


def _layout(r, members_info, back=False):
    """Screen sides from the fixed stage layout (first concept member on the audience's left)."""
    order = [m for m in members_info if m in r["members"]]
    if len(order) < 2:
        return ""
    left, right = (order[1], order[0]) if back else (order[0], order[1])
    return f", {{{left}}} on the left of the frame and {{{right}}} on the right"


def _gaze(r):
    if re.search(r"\b(look|looking|gaz|glanc|eyes|stare|staring)", r["action"], re.I):
        return ""   # the action already says where they look
    g = r.get("gaze", "camera")
    if r["kind"] == "duo":
        return {"camera": ", both looking into the camera",
                "partner": ", glancing at each other with their faces still turned toward the camera",
                "crowd": ", both looking out at the crowd", "down": ", eyes lowered",
                "up": ", eyes raised to the lights"}[g]
    return {"camera": ", looking into the camera", "crowd": ", looking out at the crowd beyond the camera",
            "down": ", eyes lowered", "up": ", eyes raised toward the lights", "partner": ""}[g]


def _bar_lyrics():
    spec = importlib.util.spec_from_file_location("build_shots", ROOT / "scripts" / "build_shots.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.bar_lyrics


def bars_text(beats, rng=None):
    """The bar grid for the model; rng = (first_bar, last_bar) limits it to the part of the song being made."""
    lyr = _bar_lyrics()(beats)
    secs = beats["sections"]
    lines = []
    for b in beats["bars"]:
        if rng and not rng[0] <= b["index"] <= rng[1]:
            continue
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


def _short(text, r, members_info):
    """Names -> "the woman" / "the man" when that is unambiguous in this shot (the motion already described them
    in full), else the full video_desc."""
    nouns = [members_info[n].get("noun", "woman") for n in r["members"] if n in members_info]
    if len(set(nouns)) < len(nouns):
        return _motion(text, members_info)
    for n in sorted(r["members"], key=len, reverse=True):
        if n in members_info:
            text = re.sub(rf"\b{re.escape(n)}\b", f"the {members_info[n].get('noun', 'woman')}", text)
    return _motion(text, members_info)


def validate(rows, beats, members, rng=None, locations=None):
    """Return (fixed_rows, errors). Small problems are fixed, structural ones reported.
    rng = (first_bar, last_bar): the rows must cover exactly these bars (default: the whole song).
    locations: location keys (story mode); every row gets a valid one."""
    vocal = {b["index"]: b["vocal"] for b in beats["bars"]}
    first, last = rng or (0, len(beats["bars"]) - 1)
    errors, fixed = [], []
    rows = sorted(rows, key=lambda r: r["first_bar"])
    expect = first
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
        r.setdefault("angle", "front")   # rows designed before angle/gaze existed
        r.setdefault("gaze", "camera")
        r["end_state"] = (r.get("end_state") or "").strip() if r["members"] else ""
        if r["kind"] in ("stage_wide", "back_view"):
            r["angle"] = "front"
        if r["lipsync"] and r["angle"] not in LIPSYNC_ANGLES:
            r["angle"] = "three-quarter"
        if r["kind"] != "duo" and r["gaze"] == "partner":
            r["gaze"] = "camera"
        if locations:
            if r.get("location") not in locations:
                r["location"] = fixed[-1]["location"] if fixed else locations[0]
        else:
            r.pop("location", None)
        fixed.append(r)
    if expect != last + 1:
        errors.append(f"rows end at bar {expect - 1}, but they must cover bars {first}..{last}")
    return fixed, errors


_FILLER = re.compile(r"\b(still|both|and|the|a|an|at|to|with|is|are|on|in|each|other|together|while)\b")
_GENERIC = re.compile(r"^(looking|looks|facing|smiling|smiles|standing|stands|gazing|staring)\b")


def _norm_action(r, members):
    t = (r.get("action") or "").lower()
    for m in members:
        t = re.sub(rf"\b{re.escape(m.lower())}('s)?\b", " ", t)
    t = _FILLER.sub(" ", re.sub(r"[^a-z' ]", " ", t))
    return " ".join(t.split())


def variety(rows, members, plate=""):
    """Soft problems of a structurally valid design: generic or repeated actions, the stage never used.
    Returned as feedback for one redesign (the design is accepted if they persist)."""
    issues = []
    people = [r for r in rows if r["members"]]
    norm = {r["first_bar"]: _norm_action(r, members) for r in rows}
    generic = [r["first_bar"] for r in people if not r.get("lipsync")   # singing is the action of a lip-sync shot
               and (len(norm[r["first_bar"]].split()) < 5 or _GENERIC.match(norm[r["first_bar"]]))]
    if people and len(generic) > len(people) * 0.25:
        issues.append(f"{len(generic)} of {len(people)} people shots have no real action (rows starting at bars "
                      f"{', '.join(map(str, generic[:12]))}): give each a pose + place on the stage + expression, "
                      "not just 'looking at the camera' / 'smiling'")
    seen = {}
    for r in rows:
        seen.setdefault(norm[r["first_bar"]], []).append(r["first_bar"])
    rep = [bars for a, bars in seen.items() if a and len(bars) > 1]
    if rep:
        issues.append("repeated actions (same wording in rows starting at bars "
                      + "; ".join(", ".join(map(str, b)) for b in rep[:6]) + "): make each shot different")
    props = [w for w in ("car", "convertible", "stairs", "staircase", "railing", "platform", "bench", "piano",
                         "motorcycle", "sofa", "couch", "throne", "swing", "ladder", "booth", "table")
             if re.search(rf"\b{w}\b", plate.lower())]
    if props and people:
        used = [r for r in people if any(re.search(rf"\b{w}\b", (r.get("action") or "").lower()) for w in props)]
        if len(used) < max(2, len(people) // 5):
            issues.append(f"the stage has a {props[0]} but only {len(used)} of {len(people)} people shots use it: "
                          "let members lean on, sit on/in or stand beside it in about a third of the shots")
    return issues


def _angle(r, story=False):
    a = ANGLE_TEXT[r.get("angle", "front")]
    return a.replace(" from the stage edge", "") if story else a


STAGE_SOLO = "standing on the raised stage, the stage floor under {p} feet and the back wall close behind {p}"
STAGE_DUO = "both standing on the raised stage, the stage floor under their feet and the back wall close behind them"


def frame_prompt(r, lights, members_info, vmode="stage"):
    names = list(members_info)
    story = vmode == "story"
    light = lights.get(r["light"], r["light"])
    action = _placeholders(r["action"], r["members"])
    one = r["members"][0] if r["members"] else None
    pron = "his" if one and members_info[one].get("noun") == "man" else "her"
    k = r["kind"]
    if k == "solo":
        tail = CU if r["size"] in ("close-up", "medium close-up") else MED
        if "{" + one + "}" not in action:
            action = "{" + one + "} " + action
        where = "in the location" if story else STAGE_SOLO.format(p=pron)
        return (f"{action}{_gaze(r)}, {_angle(r, story)}, {where}, {light}{tail}, "
                f"{{{one}}} is the only person in the frame")
    if k == "duo":
        a, b = r["members"][:2]
        if "{" + a + "}" not in action:
            action = "{" + a + "} and {" + b + "} " + action
        where = "both in the location" if story else STAGE_DUO
        return (f"{action}{_layout(r, members_info)}{_gaze(r)}, {_angle(r, story)}, {where}, "
                f"{light}{MED2}, exactly two people in the frame, two separate bodies with clear space between them")
    if k == "stage_wide" and story:
        a, b = r["members"][:2]
        return (f"Wide establishing shot of {{{a}}} and {{{b}}} in the location{_layout(r, members_info)}, {action}, "
                f"{light}, the whole place visible around them")
    if k == "back_view" and story:
        a, b = r["members"][:2]
        return (f"{{{a}}} and {{{b}}} seen from behind{_layout(r, members_info, True)}, looking into the location, "
                f"their backs to the camera, {action}, {light}")
    if k == "stage_wide":
        a, b = r["members"][:2]
        return (f"Wide shot from the crowd of {{{a}}} and {{{b}}} standing side by side on the raised stage"
                f"{_layout(r, members_info)}, {action}, "
                f"{light}, the stage floor and the back wall around them, silhouettes of the audience's heads at the "
                f"bottom of the frame")
    if k == "back_view":
        a, b = r["members"][:2]
        return (f"{{{a}}} and {{{b}}} seen from behind them at the back of the stage{_layout(r, members_info, True)}, "
                f"both facing a huge crowd below the stage, their backs to the camera, {action}, {light}")
    # empty insert: names of members may appear as small figures; keep them as plain text
    return _esc(r["action"]) + f", {_angle(r, story)}, {light}"


def motion_prompt(r, members_info, vmode="stage"):
    m = _motion(r["motion"], members_info)
    if r.get("end_state"):   # where the next shot of these members picks them up
        m = m.rstrip(" .") + ", the shot ends with " + _short(r["end_state"], r, members_info).rstrip(" .")
    k = r["kind"]
    if k == "solo":
        return m + (HANDS_CU if r["size"] in ("close-up", "medium close-up") else HANDS_MED)
    if k == "duo":
        return m + HANDS_MED + ", both stay in their places, the two bodies stay separate"
    if k in ("stage_wide", "back_view"):
        return m + (", the two people stay in place, no dancing" if vmode == "story"
                    else ", the performers stand still on the stage, no dancing")
    return m + (", no people" if vmode != "stage" else ", no people on the stage")


def write_design(path, rows, locations, lights, members_info, vmode="stage"):
    """locations: {key: plate description}; a plain string = the single stage plate (key 'stage')."""
    if isinstance(locations, str):
        locations = {"stage": locations}
    first = next(iter(locations))
    lines = ['# Generated by the MV web agent (webagent/design.py). Same format as shots/shot_design.py.',
             f"LOCATIONS = {locations!r}", "DESIGN = {'all': ["]
    for r in rows:
        mem = tuple(r["members"])
        lines.append(f" ({r['first_bar']}, {r['last_bar']}, {mem!r}, {r['lipsync']!r}, {r['size']!r},")
        lines.append(f"  {frame_prompt(r, lights, members_info, vmode)!r},")
        lines.append(f"  {motion_prompt(r, members_info, vmode)!r}),")
    lines.append("]}")
    loc = {r["first_bar"]: r.get("location") if r.get("location") in locations else first for r in rows}
    lines.append(f"LOCATION_BY_BAR = {loc!r}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_rows(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- storyboard editor (board)
FRAME_FIELDS = ("first_bar", "last_bar", "kind", "members", "lipsync", "size", "angle", "gaze", "light", "action",
                "location")
CLIP_FIELDS = FRAME_FIELDS + ("motion", "end_state")


def frame_key(r):
    """Everything the first-frame prompt is made from: equal keys -> the old frame is still right."""
    return json.dumps([sorted(r.get(k) or []) if k == "members" else r.get(k) for k in FRAME_FIELDS],
                      ensure_ascii=False)


def clip_key(r):
    return json.dumps([frame_key(r)] + [r.get(k) for k in CLIP_FIELDS[len(FRAME_FIELDS):]], ensure_ascii=False)


def restore_locked(new_rows, old_rows):
    """Put locked rows back exactly as they were (a model revising the board may touch them): rows overlapping a
    locked row's bars are dropped, the locked row is inserted. Returns (rows, notes)."""
    notes = []
    out = [dict(r) for r in new_rows]
    for L in (r for r in old_rows if r.get("locked")):
        keep = [r for r in out if r["last_bar"] < L["first_bar"] or r["first_bar"] > L["last_bar"]]
        same = any(r for r in out if frame_key(r) == frame_key(L) and r.get("motion") == L.get("motion"))
        if not same:
            notes.append(f"bars {L['first_bar']}-{L['last_bar']} are locked: kept as they were")
        out = keep + [dict(L)]
    out.sort(key=lambda r: r["first_bar"])
    return out, notes


KINDS = ["solo", "duo", "stage_wide", "back_view", "empty"]
GAZES = ["camera", "partner", "crowd", "down", "up"]


def clean_board_row(r, lights, members, locations=None):
    """A row sent by the storyboard editor: coerce types, reject values the prompt templates don't know."""
    def s(k, n=600):
        return str(r.get(k) or "").strip()[:n]
    out = {"first_bar": int(r["first_bar"]), "last_bar": int(r["last_bar"]), "kind": s("kind"),
           "members": [str(m) for m in (r.get("members") or [])][:2], "lipsync": s("lipsync") or None,
           "size": s("size"), "angle": s("angle") or "front", "gaze": s("gaze") or "camera", "light": s("light"),
           "action": s("action"), "motion": s("motion"), "end_state": s("end_state")}
    if r.get("locked"):
        out["locked"] = True
    if locations:
        out["location"] = s("location") or locations[0]
        if out["location"] not in locations:
            raise ValueError(f"bar {out['first_bar']}: unknown location {out['location']!r}")
    bad = [f"{k}={out[k]!r}" for k, ok in (("kind", KINDS), ("size", SIZES), ("angle", list(ANGLE_TEXT)),
                                            ("gaze", GAZES), ("light", list(lights))) if out[k] not in ok]
    bad += [f"member {m!r}" for m in out["members"] if m not in members]
    if not out["action"]:
        bad.append("empty action")
    if out["kind"] != "empty" and not out["motion"]:
        bad.append("empty motion")
    if bad:
        raise ValueError(f"bar {out['first_bar']}: " + ", ".join(bad))
    if not out["motion"]:
        out["motion"] = "slow light changes"
    return out


def diff_rows(old, new):
    """Rows of `new` whose content differs from every row of `old` (by clip key): for the proposal view."""
    olds = {clip_key(r) for r in old}
    return [r["first_bar"] for r in new if clip_key(r) not in olds]
