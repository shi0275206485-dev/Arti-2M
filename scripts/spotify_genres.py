"""Pull Spotify's browse categories (genres + moods) as a menu for song generation.

    python scripts/spotify_genres.py login <client_id> <client_secret>   # saves .spotify/credentials.json
    python scripts/spotify_genres.py fetch                              # -> data/genres.json
    python scripts/spotify_genres.py list

NOTE (Feb 2026): Spotify removed GET /browse/categories (and /browse/new-releases) for Development Mode apps, so a
normal personal app gets 403 here even with valid credentials. Only Extended Quota apps can still fetch categories;
the built-in list (data/genres_builtin.json) is the default.

Uses the Client Credentials flow (no user sign-in): create an app at https://developer.spotify.com/dashboard
and copy its Client ID / Client Secret. Credentials can also come from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET.
Names are fetched in English and Chinese (locale en_US / zh_CN). Non-music categories (podcasts, audiobooks,
charts, "made for you" ...) are dropped. The web agent adds a Claude-written `style` hint per category.
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CRED = ROOT / ".spotify/credentials.json"
OUT = ROOT / "data/genres.json"
BUILTIN = ROOT / "data/genres_builtin.json"   # curated list shipped with the project, no Spotify needed
API = "https://api.spotify.com/v1"
SKIP = ("podcast", "audiobook", "made-for-you", "made for you", "new release", "chart", "live event", "discover",
        "comedy", "documentary", "educational", "news", "true crime", "storytelling", "book", "spoken",
        "radio", "top lists", "toplists", "fresh finds", "equal", "frequency", "tastemakers", "kids & family",
        "播客", "有声书", "排行榜", "为你打造", "新歌", "现场活动", "探索")


class SpotifyError(Exception):
    pass


def credentials():
    cid, sec = os.environ.get("SPOTIFY_CLIENT_ID"), os.environ.get("SPOTIFY_CLIENT_SECRET")
    if cid and sec:
        return cid, sec
    if CRED.exists():
        c = json.loads(CRED.read_text(encoding="utf-8"))
        return c.get("client_id"), c.get("client_secret")
    return None, None


def save_credentials(cid, sec):
    CRED.parent.mkdir(exist_ok=True)
    CRED.write_text(json.dumps({"client_id": cid.strip(), "client_secret": sec.strip()}), encoding="utf-8")


def has_credentials():
    return all(credentials())


def _token():
    cid, sec = credentials()
    if not (cid and sec):
        raise SpotifyError("no Spotify credentials (Client ID / Secret)")
    r = httpx.post("https://accounts.spotify.com/api/token", data={"grant_type": "client_credentials"},
                   headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()},
                   timeout=20)
    if r.status_code != 200:
        raise SpotifyError(f"Spotify token request failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


def _categories(token, locale):
    out, url = [], f"{API}/browse/categories"
    params = {"limit": 50, "locale": locale}
    while url:
        r = httpx.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "2")))
            continue
        if r.status_code == 403:
            # Feb 2026 Web API change: /browse/* was removed for Development Mode apps (new apps from 2026-02-11,
            # existing ones from 2026-03-09). Credentials are fine (the token works); only Extended Quota apps keep it.
            raise SpotifyError("Spotify refused the categories endpoint (403). Since February 2026 Spotify no longer "
                               "offers /browse/categories to Development Mode apps; your credentials work, but this "
                               "data is only available to apps with Extended Quota. Use the built-in categories.")
        if r.status_code != 200:
            raise SpotifyError(f"Spotify categories request failed ({r.status_code}): {r.text[:200]}")
        page = r.json()["categories"]
        out += page["items"]
        url, params = page.get("next"), None   # `next` already carries the query
    return out


def is_music(c):
    s = f"{c['id']} {c.get('name', '')} {c.get('name_zh', '')}".lower()
    return not any(k in s for k in SKIP)


def fetch():
    token = _token()
    en = _categories(token, "en_US")
    zh = {c["id"]: c["name"] for c in _categories(token, "zh_CN")}
    old = {c["id"]: c for c in load().get("categories", [])}
    cats = []
    for c in en:
        item = {"id": c["id"], "name": c["name"], "name_zh": zh.get(c["id"], c["name"]),
                "icon": (c.get("icons") or [{}])[0].get("url")}
        for k in ("style", "instrumental"):   # keep Claude's hints from an earlier fetch
            if k in old.get(c["id"], {}):
                item[k] = old[c["id"]][k]
        if is_music(item):
            cats.append(item)
    data = {"source": "spotify", "fetched": time.time(), "total_spotify": len(en), "categories": cats}
    save(data)
    return data


def load():
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def load_builtin():
    return json.loads(BUILTIN.read_text(encoding="utf-8")).get("categories", []) if BUILTIN.exists() else []


def all_categories():
    """Built-in categories (ids b_*) followed by pulled Spotify ones, each tagged with `source`."""
    return ([dict(c, source="builtin") for c in load_builtin()]
            + [dict(c, source="spotify", group="spotify") for c in load().get("categories", [])])


def save(data):
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    try:
        if cmd == "login" and len(sys.argv) == 4:
            save_credentials(sys.argv[2], sys.argv[3])
            _token()
            print("ok: credentials saved and accepted")
        elif cmd == "fetch":
            d = fetch()
            print(f"{len(d['categories'])} music categories (of {d['total_spotify']}) -> {OUT}")
        elif cmd == "list":
            for c in all_categories():
                print(f"{c['source']:<8} {c['id']:<24} {c['name']:<24} {c['name_zh']:<12} {c.get('style', '')[:60]}")
        else:
            print(__doc__)
            return 2
    except SpotifyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
