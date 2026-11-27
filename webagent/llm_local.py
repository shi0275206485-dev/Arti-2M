"""Local LLM backend: Unsloth Studio (llama.cpp under the hood) via its OpenAI-compatible API.

brain._call() routes each task (song / cover / concept / design / pick / qc) either to Claude or here, as chosen
on the settings page. Studio runs on the same 16GB GPU as ComfyUI and YuE2, so the model is loaded only when a
local task needs it and unloaded again before ComfyUI / YuE2 start (engine calls release()); Studio's
/v1/load and /v1/unload routes do this without restarting Studio.

Config: .llm/unsloth.json (local only, git-ignored; holds the Studio API key created under Settings -> API).
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG_FILE = ROOT / ".llm" / "unsloth.json"
TASKS = ["song", "cover", "concept", "design", "pick", "qc"]
DEFAULT = {"base_url": "http://127.0.0.1:8888", "api_key": "", "model": "", "gguf_variant": "",
           "thinking": False, "unload_for_gpu": True, "context": 32768, "tasks": {t: "local" for t in TASKS}}   # local first (saves Claude tokens)

BEFORE_LOAD = None    # set by the engine: frees the GPU (stops ComfyUI) before a model is loaded
LOG = print           # set by the engine to the running job's log
_lock = threading.RLock()


class Unavailable(RuntimeError):
    """Studio not running / key rejected / model failed to load: brain falls back to Claude if it can."""


# ---------------------------------------------------------------- config
def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT))
    if CFG_FILE.exists():
        try:
            saved = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in saved.items() if k in DEFAULT and k != "tasks"})
            cfg["tasks"].update({k: v for k, v in (saved.get("tasks") or {}).items() if k in TASKS})
        except Exception:
            pass
    return cfg


def save_cfg(new):
    cfg = load_cfg()
    for k in ("base_url", "model", "gguf_variant"):
        if k in new:
            cfg[k] = str(new[k] or "").strip()
    cfg["base_url"] = cfg["base_url"].rstrip("/").removesuffix("/v1") or DEFAULT["base_url"]
    if new.get("api_key"):            # empty = keep the stored key
        cfg["api_key"] = new["api_key"].strip()
    for k in ("thinking", "unload_for_gpu"):
        if k in new:
            cfg[k] = bool(new[k])
    if new.get("context"):
        cfg["context"] = max(4096, min(262144, int(new["context"])))
    for t, v in (new.get("tasks") or {}).items():
        if t in TASKS and v in ("claude", "local"):
            cfg["tasks"][t] = v
    CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return public_cfg(cfg)


def public_cfg(cfg=None):
    cfg = dict(cfg or load_cfg())
    cfg["has_key"] = bool(cfg.pop("api_key"))
    return cfg


def uses_local(task):
    cfg = load_cfg()
    return cfg["tasks"].get(task) == "local" and bool(cfg["model"])


def any_local():
    cfg = load_cfg()
    return bool(cfg["model"]) and "local" in cfg["tasks"].values()


# ---------------------------------------------------------------- HTTP
def _req(path, body=None, timeout=30, method=None):
    cfg = load_cfg()
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(cfg["base_url"] + path, data=data, method=method or ("POST" if data else "GET"),
                               headers={"Content-Type": "application/json",
                                        **({"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {})})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        if e.code == 401:
            raise Unavailable("Unsloth Studio rejected the API key (create one under Settings -> API)") from None
        raise RuntimeError(f"Unsloth Studio {path}: HTTP {e.code} {detail}") from None
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise Unavailable(f"Unsloth Studio not reachable at {cfg['base_url']} ({getattr(e, 'reason', e)}); "
                           "start Unsloth Studio first") from None


def status():
    cfg = load_cfg()
    out = {"configured": bool(cfg["model"]), "model": cfg["model"], "reachable": False, "loaded": False,
           "has_key": bool(cfg["api_key"])}
    try:
        _req("/api/health", timeout=3)
        out["reachable"] = True
        st = _req("/v1/status", timeout=5)
        out["active"] = st.get("model_identifier") or st.get("active_model")
        out["loaded"] = _is_loaded(st, cfg["model"])
        out["ok"] = True
    except Exception as e:
        out["error"] = str(e)
        out["ok"] = False
    return out


def _ctx_ok(st, cfg):
    """A model loaded from Studio's own UI often has a small window (8192 shared by 4 slots); our prompts
    (beats + rules + images) need cfg['context'] in a single slot."""
    ctx = st.get("context_length") or 0
    slots = st.get("parallel_slots") or 1
    want = min(cfg["context"], st.get("native_context_length") or cfg["context"])
    return ctx // max(1, slots) >= want or ctx == 0


def _is_loaded(st, model):
    names = [st.get("model_identifier"), st.get("active_model")]
    for m in st.get("loaded") or []:
        names += [m.get(k) for k in ("model_identifier", "model", "id", "active_model")] if isinstance(m, dict) else [m]
    return bool(model) and any(n and (n == model or n.split(":")[0] == model.split(":")[0]) for n in names)


def models():
    """Model ids Studio knows (loaded and downloaded)."""
    r = _req("/v1/models", timeout=10)
    return [{"id": m.get("id"), "loaded": m.get("loaded")} for m in r.get("data", []) if m.get("id")]


# ---------------------------------------------------------------- load / unload (shares the GPU)
def ensure_loaded(log=None):
    cfg, log = load_cfg(), log or LOG
    with _lock:
        st = _req("/v1/status", timeout=10)
        loaded = _is_loaded(st, cfg["model"])
        if loaded and _ctx_ok(st, cfg):
            return
        if BEFORE_LOAD:
            BEFORE_LOAD()
        why = (f" (reloading: context {st.get('context_length')} / {st.get('parallel_slots') or 1} slots "
               f"< {cfg['context']})") if loaded else ""
        log(f"local LLM: loading {cfg['model']} in Unsloth Studio{why}...")
        t0 = time.time()
        body = {"model_path": cfg["model"], "max_seq_length": cfg["context"], "n_parallel": 1,
                "cache_type_kv": "q8_0", "force_reload": loaded, "force_cancel_active": True}
        if cfg["gguf_variant"]:
            body["gguf_variant"] = cfg["gguf_variant"]
        try:
            _req("/v1/load", body, timeout=1800)
        except Unavailable:
            raise
        except RuntimeError as e:
            raise Unavailable(f"Unsloth Studio could not load {cfg['model']}: {e}") from None
        for _ in range(600):   # the load call usually returns when ready; poll in case it returns early
            if _is_loaded(_req("/v1/status", timeout=10), cfg["model"]):
                break
            time.sleep(2)
        else:
            raise Unavailable(f"Unsloth Studio did not finish loading {cfg['model']}")
        st = _req("/v1/status", timeout=10)
        log(f"local LLM: {cfg['model']} ready ({time.time() - t0:.0f}s, context {st.get('context_length')}, "
            f"{st.get('offloaded_layers')}/{st.get('n_layers')} layers on GPU)")


def release(log=None):
    """Unload the local model so ComfyUI / YuE2 get the GPU. Cheap no-op when local models are not used."""
    cfg = load_cfg()
    if not (any_local() and cfg["unload_for_gpu"]):
        return
    log = log or LOG
    with _lock:
        try:
            st = _req("/v1/status", timeout=3)
        except Exception:
            return   # Studio not running: nothing to free
        if not _is_loaded(st, cfg["model"]):
            return
        try:
            _req("/v1/unload", {"model_path": st.get("model_identifier") or cfg["model"],
                                "force_cancel_active": True}, timeout=120)
            log(f"local LLM: unloaded {cfg['model']} (GPU needed by ComfyUI / YuE2)")
        except Exception as e:
            log(f"local LLM: unload failed ({e})")


# ---------------------------------------------------------------- chat
def _content(blocks):
    """Anthropic-style content blocks (text / base64 image) -> OpenAI chat content parts."""
    out = []
    for b in blocks:
        if b["type"] == "text":
            out.append({"type": "text", "text": b["text"]})
        elif b["type"] == "image":
            s = b["source"]
            out.append({"type": "image_url", "image_url": {"url": f"data:{s['media_type']};base64,{s['data']}"}})
    return out


def _parse(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start < 0:
            raise RuntimeError(f"the local model did not return JSON: {text[:300]!r}") from None
        return json.JSONDecoder().raw_decode(text[start:])[0]


def chat_json(system, content, schema, max_tokens=8000, log=None):
    cfg = load_cfg()
    ensure_loaded(log)
    body = {"model": cfg["model"], "stream": False, "max_tokens": max_tokens, "temperature": 0.7,
            "enable_thinking": cfg["thinking"], "enable_tools": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": _content(content)}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "schema": schema, "strict": True}}}
    with _lock:
        r = _req("/v1/chat/completions", body, timeout=3600)
    ch = (r.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    if ch.get("finish_reason") == "length":
        u = r.get("usage") or {}
        think = len(msg.get("reasoning_content") or "")
        raise RuntimeError(f"the local model's answer was cut off (prompt {u.get('prompt_tokens')} + output "
                           f"{u.get('completion_tokens')} tokens, max_tokens {max_tokens}, context {cfg['context']}"
                           + (f", {think} chars spent thinking" if think else "") + ")")
    return _parse(msg.get("content"))


def test():
    """Tiny structured request to check the whole path (load + JSON output)."""
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}},
              "required": ["ok", "word"], "additionalProperties": False}
    t0 = time.time()
    r = chat_json("Answer in JSON.", [{"type": "text", "text": "Return ok=true and one English word for 'music'."}],
                  schema, max_tokens=4000 if load_cfg()["thinking"] else 300)
    st = _req("/v1/status", timeout=10)
    return {"answer": r, "seconds": round(time.time() - t0, 1), "context": st.get("context_length"),
            "gpu_layers": f"{st.get('offloaded_layers')}/{st.get('n_layers')}"}
