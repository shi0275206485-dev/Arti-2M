"""Suno access for the MV pipeline: our own OAuth sign-in + a minimal client for Suno's MCP endpoint.

Suno's public API is reached through https://api.suno.com/mcp (JSON-RPC "tools/call"), the same tools Claude
Code's Suno connector uses. Sign-in: dynamic client registration + PKCE against Suno's OAuth server; the
registered client and tokens are stored in <repo>/.suno/ (local only, never sent anywhere but Suno).

    import suno_api as sa
    url = sa.login_url(redirect_uri)           # open in a browser
    sa.finish_login(code, state)               # from the redirect
    sa.call("account-usage")                   # -> dict
"""
import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".suno"
AUTH = "https://studio-api-prod.suno.com/api/v2/external/oauth"
MCP = "https://api.suno.com/mcp"
RESOURCE = "https://api.suno.com/mcp"
SCOPES = "api:v0 credits:spend download library:read offline_access profile:read"
REDIRECTS = ["http://127.0.0.1:8700/api/suno/callback", "http://127.0.0.1:8701/callback"]
_lock = threading.Lock()
_pending = {}       # state -> (verifier, redirect_uri)
_session = {}       # cached MCP session id


class SunoError(Exception):
    def __init__(self, msg, data=None):
        super().__init__(msg)
        self.data = data or {}


def _read(name):
    f = STORE / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _write(name, data):
    STORE.mkdir(exist_ok=True)
    tmp = STORE / (name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(STORE / name)


# ------------------------------------------------------------------ OAuth
def _client_valid(cid):
    """Suno drops dynamically registered clients after a while (seen: a 2-day-old client got 400 "Invalid client
    ID" at /authorize). Probe /authorize without following the redirect: a live client gets 302 to suno.com."""
    q = {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECTS[0], "state": "probe",
         "code_challenge": "x" * 43, "code_challenge_method": "S256", "scope": SCOPES, "resource": RESOURCE}
    try:
        r = httpx.get(f"{AUTH}/authorize/?" + urllib.parse.urlencode(q), follow_redirects=False, timeout=20)
    except httpx.HTTPError:
        return True   # network trouble: keep the cached client, the real request will report the error
    return not (r.status_code == 400 and "client" in r.text.lower())


def _client_id(check=False):
    c = _read("client.json")
    if c and set(REDIRECTS) <= set(c.get("redirect_uris", [])) and (not check or _client_valid(c["client_id"])):
        return c["client_id"]
    r = httpx.post(f"{AUTH}/register/", json={
        "client_name": "MV Agent (local)", "redirect_uris": REDIRECTS,
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none", "scope": SCOPES}, timeout=30)
    if r.status_code >= 300:
        raise SunoError(f"client registration failed: {r.status_code} {r.text[:300]}")
    c = r.json()
    c.setdefault("redirect_uris", REDIRECTS)
    _write("client.json", c)
    return c["client_id"]


def login_url(redirect_uri=REDIRECTS[0]):
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _pending[state] = (verifier, redirect_uri)
    q = {"response_type": "code", "client_id": _client_id(check=True), "code_challenge": challenge,
         "code_challenge_method": "S256", "redirect_uri": redirect_uri, "state": state, "scope": SCOPES,
         "prompt": "consent", "resource": RESOURCE}
    return f"{AUTH}/authorize/?" + urllib.parse.urlencode(q)


def _save_tokens(tok):
    tok["expires_at"] = time.time() + float(tok.get("expires_in", 3600)) - 60
    old = _read("token.json") or {}
    if "refresh_token" not in tok and "refresh_token" in old:
        tok["refresh_token"] = old["refresh_token"]
    _write("token.json", tok)
    _session.clear()


def finish_login(code, state):
    if state not in _pending:
        raise SunoError("unknown or expired login attempt; start the sign-in again")
    verifier, redirect_uri = _pending.pop(state)
    r = httpx.post(f"{AUTH}/token/", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": _client_id(), "code_verifier": verifier, "resource": RESOURCE}, timeout=30)
    if r.status_code >= 300:
        raise SunoError(f"token exchange failed: {r.status_code} {r.text[:300]}")
    _save_tokens(r.json())


def logout():
    for n in ("token.json",):
        f = STORE / n
        if f.exists():
            f.unlink()
    _session.clear()


def signed_in():
    return bool(_read("token.json"))


def _access_token():
    with _lock:
        tok = _read("token.json")
        if not tok:
            raise SunoError("not signed in to Suno", {"reason": "not_signed_in"})
        if time.time() < tok.get("expires_at", 0):
            return tok["access_token"]
        if not tok.get("refresh_token"):
            raise SunoError("Suno sign-in expired; sign in again", {"reason": "not_signed_in"})
        r = httpx.post(f"{AUTH}/token/", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": _client_id(),
            "resource": RESOURCE}, timeout=30)
        if r.status_code >= 300:
            raise SunoError(f"Suno sign-in expired ({r.status_code}); sign in again", {"reason": "not_signed_in"})
        _save_tokens(r.json())
        return _read("token.json")["access_token"]


# ------------------------------------------------------------------ MCP (streamable HTTP, JSON-RPC)
def _rpc(method, params, rid):
    headers = {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
    if _session.get("id"):
        headers["Mcp-Session-Id"] = _session["id"]
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if rid is not None:
        body["id"] = rid
    r = httpx.post(MCP, json=body, headers=headers, timeout=120)
    if r.status_code == 401:
        raise SunoError("Suno rejected the sign-in (401); sign in again", {"reason": "not_signed_in"})
    if r.status_code == 404 and _session.get("id"):
        _session.clear()
        raise SunoError("session expired", {"reason": "session"})
    if r.headers.get("mcp-session-id"):
        _session["id"] = r.headers["mcp-session-id"]
    if rid is None:
        return None
    if r.status_code >= 300:
        raise SunoError(f"Suno MCP HTTP {r.status_code}: {r.text[:300]}")
    if "text/event-stream" in r.headers.get("content-type", ""):
        for line in r.text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if msg.get("id") == rid:
                    return msg
        raise SunoError("no response in Suno event stream")
    return r.json()


def _ensure_session():
    if _session.get("ready"):
        return
    _session.clear()
    msg = _rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "mv-agent", "version": "1.0"}}, 1)
    if "error" in msg:
        raise SunoError(f"Suno MCP initialize failed: {msg['error']}")
    _rpc("notifications/initialized", {}, None)
    _session["ready"] = True


def _parse_text(text):
    """Tool text is JSON, sometimes followed by a plain-language hint for the model, e.g. audio-create returns
    '{"clip_ids": [...], ...}This made 2 songs, one per id: ...'. Parse the leading JSON value and keep the hint
    as "_note"; text that doesn't start with JSON comes back as {"text": ...}."""
    s = text.lstrip()
    try:
        data, end = json.JSONDecoder().raw_decode(s)
    except ValueError:
        return {"text": text}
    note = s[end:].strip()
    if isinstance(data, dict) and note:
        data["_note"] = note
    return data


def call(tool, args=None):
    """Call a Suno MCP tool, return its JSON result. Tool errors raise SunoError with the parsed payload."""
    for attempt in range(2):
        _ensure_session()
        try:
            msg = _rpc("tools/call", {"name": tool, "arguments": args or {}}, secrets.randbelow(10**9) + 2)
            break
        except SunoError as e:
            if e.data.get("reason") == "session" and attempt == 0:
                continue
            raise
    if "error" in msg:
        raise SunoError(f"{tool}: {msg['error'].get('message', msg['error'])}", msg["error"])
    res = msg["result"]
    text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
    data = res.get("structuredContent")
    if data is None:
        data = _parse_text(text)
    if res.get("isError"):
        raise SunoError(f"{tool}: {data.get('error') or text[:300]}", data if isinstance(data, dict) else {})
    return data
