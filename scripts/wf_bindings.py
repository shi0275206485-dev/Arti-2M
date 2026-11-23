"""Workflow bindings: which ComfyUI API workflow a pipeline role uses and which node inputs receive the
pipeline's values (prompt, seed, size, reference images, audio...).

Roles
    t2i            text to image (member reference portraits, location plates)
    edit1/2/3      first frames with 1/2/3 reference images (members first, then the location plate)
    i2v            first frame -> video
    lipsync        first frame + vocal clip -> lip-synced video

A project can override the defaults with workflows/bindings.json (relative to the working directory):
    {"i2v": {"file": "workflows/my_wan_api.json",
             "bind": {"image": ["12", "image"], "prompt": ["6", "text"], "seed": ["3", "seed"],
                      "frames": ["40", "length"], "width": ["40", "width"], "height": ["40", "height"]},
             "fixed": {"40": {"batch_size": 1}}, "fps": 16, "frame_multiple": 4}}
Without that file every script behaves exactly as before (the built-in Qwen 2.1 / LTX-2.3 workflows).
"""
import json
import math
from pathlib import Path

BINDINGS_FILE = "workflows/bindings.json"

_QWEN = {"prompt": ["900", "value"], "seed": ["458", "seed"], "width": ["456", "width"],
         "height": ["456", "height"], "output": ["461", "filename_prefix"]}
_LTX = {"image": ["269", "image"], "prompt": ["320:319", "value"], "seconds": ["320:301", "value"],
        "seed": ["320:277", "noise_seed"], "width": ["320:312", "value"], "height": ["320:299", "value"],
        "output": ["75", "filename_prefix"]}
_REFS = ["470", "476", "477"]

DEFAULTS = {
    "t2i": {"name": "Qwen Image 2.1 t2i（内置）", "file": "workflows/qwen21_t2i_api.json", "bind": dict(_QWEN)},
    "edit1": {"name": "Qwen Image 2.1 编辑·1 图（内置）", "file": "workflows/qwen21_edit_api.json",
              "bind": {**_QWEN, "image1": [_REFS[0], "image"]}, "fixed": {"468": {"switch": True}}},
    "edit2": {"name": "Qwen Image 2.1 编辑·2 图（内置）", "file": "workflows/qwen21_edit2_api.json",
              "bind": {**_QWEN, "image1": [_REFS[0], "image"], "image2": [_REFS[1], "image"]},
              "fixed": {"468": {"switch": True}}},
    "edit3": {"name": "Qwen Image 2.1 编辑·3 图（内置）", "file": "workflows/qwen21_edit3_api.json",
              "bind": {**_QWEN, "image1": [_REFS[0], "image"], "image2": [_REFS[1], "image"],
                       "image3": [_REFS[2], "image"]}, "fixed": {"468": {"switch": True}}},
    "i2v": {"name": "LTX-2.3 图生视频（内置）", "file": "workflows/ltx23_i2v_api.json", "bind": dict(_LTX)},
    "lipsync": {"name": "LTX-2.3 对口型 ia2v（内置）", "file": "workflows/ltx23_ia2v_api.json",
                "bind": {**_LTX, "audio": ["900", "audio"]}},
}

# role -> list of (param, required, label). "seconds|frames": one of the two must be bound.
ROLES = {
    "t2i": {"label": "文生图（成员参考图 / 舞台底图）", "kind": "image", "params": []},
    "edit1": {"label": "首帧 · 1 张参考图", "kind": "image", "params": [("image1", True, "参考图 1")]},
    "edit2": {"label": "首帧 · 2 张参考图", "kind": "image",
              "params": [("image1", True, "参考图 1"), ("image2", True, "参考图 2")]},
    "edit3": {"label": "首帧 · 3 张参考图", "kind": "image",
              "params": [("image1", True, "参考图 1"), ("image2", True, "参考图 2"), ("image3", True, "参考图 3")]},
    "i2v": {"label": "视频 · 图生视频", "kind": "video", "params": [("image", True, "首帧图")]},
    "lipsync": {"label": "视频 · 对口型（图 + 人声）", "kind": "video",
                "params": [("image", True, "首帧图"), ("audio", True, "人声片段")]},
}
COMMON = {"image": [("prompt", True, "提示词"), ("seed", True, "种子"), ("width", False, "宽"),
                    ("height", False, "高"), ("output", False, "输出文件名前缀")],
          "video": [("prompt", True, "提示词"), ("seed", True, "种子"), ("seconds", False, "时长（秒）"),
                    ("frames", False, "帧数（与时长二选一）"), ("width", False, "宽"), ("height", False, "高"),
                    ("output", False, "输出文件名前缀")]}


def params(role):
    r = ROLES[role]
    return r["params"] + COMMON[r["kind"]]


def is_api_workflow(wf):
    return isinstance(wf, dict) and wf and all(isinstance(n, dict) and "class_type" in n for n in wf.values())


def load_role(role, root="."):
    """Return (workflow dict, binding dict) for a role, honouring workflows/bindings.json."""
    root = Path(root)
    b = None
    f = root / BINDINGS_FILE
    if f.exists():
        b = json.loads(f.read_text(encoding="utf-8")).get(role)
    b = b or DEFAULTS[role]
    wf = json.loads((root / b["file"]).read_text(encoding="utf-8"))
    return wf, b


def validate(wf, b, role):
    """List of problems (empty = ok)."""
    errs = []
    if not is_api_workflow(wf):
        return ["不是 API 格式的工作流（ComfyUI 菜单 Export (API) 导出的 JSON）"]
    bind = b.get("bind", {})
    for key, (node, inp) in bind.items():
        if node not in wf:
            errs.append(f"{key}: 节点 {node} 不存在")
        elif inp not in wf[node].get("inputs", {}):
            errs.append(f"{key}: 节点 {node} 没有输入 {inp}")
    for key, req, label in params(role):
        if req and key not in bind:
            errs.append(f"缺少必填映射：{label}（{key}）")
    if ROLES[role]["kind"] == "video" and "seconds" not in bind and "frames" not in bind:
        errs.append("视频工作流需要映射 时长（秒）或 帧数 之一")
    for node, kv in (b.get("fixed") or {}).items():
        if node not in wf:
            errs.append(f"固定值：节点 {node} 不存在")
    return errs


def fill(wf, b, values):
    """Write values into the workflow. values: {param: value}. Unbound optional params are skipped;
    'seconds' is converted to frames when only 'frames' is bound."""
    bind = b.get("bind", {})
    vals = dict(values)
    if "seconds" in vals and "seconds" not in bind and "frames" in bind:
        fps = b.get("fps", 24)
        m = b.get("frame_multiple", 1) or 1
        n = math.ceil(float(vals.pop("seconds")) * fps)
        vals["frames"] = (math.ceil((n - 1) / m) * m + 1) if m > 1 else n
    for key, v in vals.items():
        if key not in bind:
            continue
        node, inp = bind[key]
        if node not in wf:
            raise KeyError(f"binding {key}: node {node} not in workflow {b.get('file')}")
        wf[node]["inputs"][inp] = v
    for node, kv in (b.get("fixed") or {}).items():
        wf[node]["inputs"].update(kv)
    return wf


# ---------- auto-detection for uploaded workflows

def scalar_inputs(wf):
    """Every literal (non-link) input: [{node, input, class, title, value}] for mapping dropdowns."""
    out = []
    for nid, n in wf.items():
        for k, v in n.get("inputs", {}).items():
            if isinstance(v, list):
                continue
            out.append({"node": nid, "input": k, "class": n["class_type"],
                        "title": (n.get("_meta") or {}).get("title", ""), "value": v})
    return out


def _title(n):
    return ((n.get("_meta") or {}).get("title") or "").lower()


def _order(nid):
    return [int(x) if x.isdigit() else x for x in nid.replace(":", " ").split()]


def suggest(wf, role):
    """Best-guess binding for a workflow. The user confirms it in the UI."""
    items = sorted(wf.items(), key=lambda kv: _order(kv[0]))
    bind = {}

    def first(pred, inp):
        for nid, n in items:
            ins = n.get("inputs", {})
            if inp in ins and not isinstance(ins[inp], list) and pred(nid, n):
                return [nid, inp]

    # prompt: a Primitive string titled prompt > positive CLIPTextEncode-like text > any string text/prompt
    def short(n, inp):   # long literals are system prompts / templates, not the slot for our prompt
        return len(str(n["inputs"].get(inp, ""))) < 400

    bind["prompt"] = (first(lambda i, n: n["class_type"].startswith("PrimitiveString") and "prompt" in _title(n)
                            and "neg" not in _title(n), "value")
                      or first(lambda i, n: n["class_type"].startswith("PrimitiveString") and "neg" not in _title(n)
                               and short(n, "value"), "value")
                      or first(lambda i, n: "neg" not in _title(n) and "TextEncode" in n["class_type"], "text")
                      or first(lambda i, n: "neg" not in _title(n), "text")
                      or first(lambda i, n: "neg" not in _title(n), "prompt"))
    bind["seed"] = first(lambda i, n: True, "noise_seed") or first(lambda i, n: True, "seed")
    for dim in ("width", "height"):
        bind[dim] = (first(lambda i, n: n["class_type"].startswith("PrimitiveInt") and dim in _title(n), "value")
                     or first(lambda i, n: "Latent" in n["class_type"], dim)
                     or first(lambda i, n: True, dim))
    bind["output"] = first(lambda i, n: n["class_type"].startswith("Save"), "filename_prefix")
    images = [nid for nid, n in items if n["class_type"].startswith("LoadImage")
              and not isinstance(n.get("inputs", {}).get("image"), list)]
    kind = ROLES[role]["kind"]
    if kind == "video":
        bind["seconds"] = first(lambda i, n: n["class_type"].startswith("PrimitiveFloat")
                                and any(w in _title(n) for w in ("second", "duration", "时长", "秒")), "value")
        if not bind["seconds"]:
            for name in ("length", "num_frames", "frames", "video_length", "frame_count"):
                bind["frames"] = first(lambda i, n: True, name)
                if bind["frames"]:
                    break
        if images:
            bind["image"] = [images[0], "image"]
        if role == "lipsync":
            bind["audio"] = first(lambda i, n: n["class_type"].startswith("LoadAudio"), "audio")
    else:
        for k, nid in enumerate(images[:3], 1):
            if f"image{k}" in [p for p, _, _ in params(role)]:
                bind[f"image{k}"] = [nid, "image"]
    return {k: v for k, v in bind.items() if v}
