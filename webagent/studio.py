"""Music studio: a song library under songs/<id>/, independent of MV projects.

Each song folder has the same layout the music scripts expect (audio/song.wav, analysis/score.abc +
song_source.json, music/<runs>), so scripts/gen_music.py and scripts/suno_music.py run there with --root .
An MV project takes a finished song from here (engine.import_song copies audio, score and lyrics).

song.json: id, title, brief, engine (yue2|suno|upload), style, lyrics, seed, status, msg, needs, suno, current,
runs, duration, created.   status: drafting | draft | generating | needs | ready | error
"""
import json
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "songs"
ENGINES = ("yue2", "suno", "upload")
_locks = defaultdict(threading.RLock)

# Click-to-choose song settings. Values are the English tags the generators understand (YuE2's style field
# and Suno's tags are plain text); the page shows translated labels. The page composes `style` from these;
# Claude's draft fills them in. Only style, lyrics, cot, seed, abc and cfg_scale (+ sampling) reach YuE2.
OPTIONS = {
    "vocal": ["female vocal", "male vocal", "male and female duet vocals", "female group vocals",
              "male group vocals", "child vocal", "choir vocals", "male rap", "female rap"],
    "language": ["Mandarin Chinese", "Cantonese", "English", "Japanese", "Korean", "Spanish",
                 "Mandarin and English"],
    "moods": ["happy", "sad", "romantic", "energetic", "relaxed", "dark", "dreamy", "nostalgic", "epic",
              "melancholic", "uplifting", "aggressive", "mysterious", "playful", "warm", "emotional"],
    "instruments": ["piano", "acoustic guitar", "electric guitar", "bass", "drums", "strings", "synthesizer",
                    "808 bass", "electric piano", "saxophone", "trumpet", "violin", "cello", "flute", "organ",
                    "harp", "music box", "guzheng", "erhu", "dizi", "pipa"],
    "length": ["short", "standard", "long"],
}
# YuE2 knobs shown as friendly choices -> gen_music.py flags (defaults are YuE2's own: no flag)
YUE_CHOICES = {
    "cot": {"full": [], "melody": ["--cot", "melody"], "off": ["--cot", "off"]},
    "creativity": {"stable": ["--abc-temperature", "0.55", "--abc-top-p", "0.85"], "normal": [],
                   "bold": ["--abc-temperature", "0.9", "--abc-top-p", "0.95"]},
    "guidance": {"default": [], "strong": ["--cfg-scale", "1.2"], "stronger": ["--cfg-scale", "1.5"]},
    "long_score": {False: [], True: ["--abc-max-tokens", "6144", "--max-tokens", "13000"]},
}
YUE_DEFAULTS = {"cot": "full", "creativity": "normal", "guidance": "default", "long_score": False}


def yue_flags(yue, instrumental=False):
    y = {**YUE_DEFAULTS, **(yue or {})}
    if instrumental and y["cot"] == "off":   # the instrumental workflow needs a planned score
        y["cot"] = "full"
    return [str(a) for k in YUE_CHOICES for a in YUE_CHOICES[k].get(y[k], [])]


def clean_settings(s):
    """Keep only known values (the page and Claude both write settings)."""
    s = s or {}
    out = {"genre_text": str(s.get("genre_text") or "")[:80]}
    for k in ("vocal", "language", "length"):
        out[k] = s.get(k) if s.get(k) in OPTIONS[k] else ""
    for k, cap in (("moods", 3), ("instruments", 6)):
        out[k] = [v for v in (s.get(k) or []) if v in OPTIONS[k]][:cap]
    bpm = s.get("bpm")
    out["bpm"] = int(bpm) if isinstance(bpm, (int, float)) and 40 <= bpm <= 220 else None
    return out


def clean_yue(y):
    y = y or {}
    return {k: (y.get(k) if y.get(k) in YUE_CHOICES[k] else YUE_DEFAULTS[k]) for k in YUE_DEFAULTS}


class Song:
    def __init__(self, sid):
        if not re.fullmatch(r"[\w-]{1,80}", sid or ""):
            raise ValueError("bad song id")
        self.id = sid
        self.dir = SONGS / sid
        self.path = self.dir / "song.json"
        self.lock = _locks[sid]

    def exists(self):
        return self.path.exists()

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

    def set(self, **kw):
        return self.update(lambda st: st.update(kw))

    def log(self, text):
        with open(self.dir / "song.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")

    def has_audio(self):
        return (self.dir / "audio/song.wav").exists()


def create_song(title, brief, engine, style="", lyrics="", instrumental=False, genre=None):
    if engine not in ENGINES:
        raise ValueError("unknown engine")
    slug = re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")[:24] or "song"
    sid = f"{slug}_{time.strftime('%Y%m%d_%H%M%S')}"
    s = Song(sid)
    for sub in ("audio", "analysis", "music"):
        (s.dir / sub).mkdir(parents=True, exist_ok=True)
    s.save({"id": sid, "title": title or "", "brief": brief or "", "engine": engine, "style": style or "",
            "lyrics": lyrics or "", "instrumental": bool(instrumental), "genre": genre,
            "settings": clean_settings({}), "yue": clean_yue({}), "style_custom": bool(style), "seed": 42, "status": "draft", "msg": "", "needs": None, "suno": None,
            "current": None, "runs": [], "duration": None, "created": time.time()})
    s.log(f"song created ({engine})")
    return s


def list_songs():
    out = []
    for f in sorted(SONGS.glob("*/song.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
            out.append({k: st.get(k) for k in ("id", "title", "engine", "status", "duration", "created",
                                               "instrumental", "genre")}
                       | {"has_audio": (f.parent / "audio/song.wav").exists(),
                          "cover": (st.get("cover") or {}).get("t") if (f.parent / "cover.png").exists() else None})
        except Exception:
            pass
    return out
