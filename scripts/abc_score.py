"""Minimal ABC parser for YuE2 score.abc: meter, tempo, sections, bars, note timing.

Only what the MV pipeline needs: where each bar/section starts (in beats), which bars
have vocals, the chord at each bar, and where the first/last sounding notes are
(used to anchor the score grid onto the rendered audio).

    from abc_score import parse_score
    score = parse_score(Path("analysis/score.abc").read_text(encoding="utf-8"))
"""
import re
from fractions import Fraction

NOTE_RE = re.compile(r"(\^{1,2}|_{1,2}|=)?([A-Ga-gzx])([,']*)(\d*)(/*)(\d*)")
BAR_RE = re.compile(r":*\|+[\]:]*|\[\||::")
INSTRUMENTAL = {"intro", "outro", "interlude", "instrumental", "inst", "solo", "break", "ending",
                "dancebreak", "buildup", "drop"}


def _length(num, slashes, den):
    n = Fraction(int(num)) if num else Fraction(1)
    if slashes:
        d = int(den) if den else 2 ** len(slashes)
        n /= d
    return n


def _frac(s, default):
    try:
        return Fraction(s.strip())
    except (ValueError, ZeroDivisionError):
        return default


def norm_section(name):
    """'Verse 2' -> 'verse', 'Pre-Chorus' -> 'prechorus'."""
    return re.sub(r"[^a-z]", "", name.lower())


class _Voice:
    def __init__(self):
        self.bars = []      # list of dict(section, notes=[(onset, dur, rest)], chord, length)
        self.cur = None

    def open_bar(self, section):
        if self.cur is None:
            self.cur = {"section": section, "notes": [], "chord": None, "pos": Fraction(0)}
        return self.cur

    def close_bar(self):
        if self.cur is not None and (self.cur["notes"] or self.cur["pos"] > 0):
            self.bars.append(self.cur)
        self.cur = None


def _parse_music(line, voice, section, warnings):
    i, n = 0, len(line)
    tuplet = None          # [remaining notes, factor]
    broken = None          # factor for the next note from > or <
    while i < n:
        c = line[i]
        if c == '"':                                  # chord symbol / annotation
            j = line.find('"', i + 1)
            j = n - 1 if j < 0 else j
            sym = line[i + 1:j]
            bar = voice.open_bar(section)
            if bar["chord"] is None and sym and sym[0] in "ABCDEFG":
                bar["chord"] = sym
            i = j + 1
            continue
        if c in "!+":                                  # decorations
            j = line.find(c, i + 1)
            i = (j + 1) if j > 0 else i + 1
            continue
        if c == "{":                                   # grace notes take no time
            j = line.find("}", i + 1)
            i = (j + 1) if j > 0 else n
            continue
        m = BAR_RE.match(line, i)
        if m:
            if ":" in m.group(0):
                warnings.add("score uses repeat signs; playback order may differ from bar order")
            voice.close_bar()
            i = m.end()
            continue
        if c == "[" and i + 2 < n and line[i + 1].isalpha() and line[i + 2] == ":":
            j = line.find("]", i)                      # inline field [M:3/4]
            field = line[i + 1:j]
            if field[0] in "MQL":
                warnings.add(f"inline field [{field}] ignored (tempo/meter changes not supported)")
            i = j + 1 if j > 0 else n
            continue
        if c == "(" and i + 1 < n and line[i + 1].isdigit():
            p = int(line[i + 1])
            q = {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}.get(p, 2)
            tuplet = [p, Fraction(q, p)]
            i += 2
            continue
        if c in "<>":
            k = 1
            while i + k < n and line[i + k] == c:
                k += 1
            frac = Fraction(1, 2 ** k)
            bar = voice.cur
            if bar and bar["notes"]:                   # adjust previous note, set next
                on, d, rest = bar["notes"][-1]
                prev_new = d * (2 - frac) if c == ">" else d * frac
                bar["notes"][-1] = (on, prev_new, rest)
                bar["pos"] += prev_new - d
                broken = frac if c == ">" else (2 - frac)
            i += k
            continue
        if c == "Z":                                   # multi-measure rest Z4
            m = re.match(r"Z(\d*)", line[i:])
            count = int(m.group(1) or 1)
            voice.close_bar()
            for _ in range(count):
                voice.bars.append({"section": section, "notes": [], "chord": None,
                                   "pos": None, "multirest": True})
            i += m.end()
            # the Z token is normally followed by its own barline; swallow it
            m2 = BAR_RE.match(line, i)
            if m2:
                i = m2.end()
            continue
        if c == "[":                                   # chord of notes: duration = first note
            j = line.find("]", i)
            j = n - 1 if j < 0 else j
            inner = NOTE_RE.search(line, i + 1, j)
            m_after = re.match(r"(\d*)(/*)(\d*)", line[j + 1:])
            d = _length(*inner.groups()[3:]) if inner else Fraction(1)
            d *= _length(*m_after.groups())
            i = j + 1 + m_after.end()
            d = _apply(d, tuplet, broken)
            broken = None
            tuplet = _tick(tuplet)
            _add(voice, section, d, rest=False)
            continue
        m = NOTE_RE.match(line, i)
        if m:
            d = _length(m.group(4), m.group(5), m.group(6))
            d = _apply(d, tuplet, broken)
            broken = None
            tuplet = _tick(tuplet)
            _add(voice, section, d, rest=m.group(2) in "zx")
            i = m.end()
            continue
        i += 1                                         # ties, spaces, y, etc.


def _apply(d, tuplet, broken):
    if tuplet:
        d *= tuplet[1]
    if broken:
        d *= broken
    return d


def _tick(tuplet):
    if not tuplet:
        return None
    tuplet[0] -= 1
    return tuplet if tuplet[0] > 0 else None


def _add(voice, section, d, rest):
    bar = voice.open_bar(section)
    bar["notes"].append((bar["pos"], d, rest))
    bar["pos"] += d


def parse_score(text):
    header = {}
    voices = {}
    order = []
    section = None
    current = None
    in_body = False
    warnings = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%%"):
            continue
        if line.startswith("%"):
            if in_body:
                section = line[1:].strip() or section
            continue
        fm = re.match(r"^([A-Za-z]):\s*(.*)$", line)
        if fm and not NOTE_RE.fullmatch(line.split("|")[0] or "-"):
            key, val = fm.group(1), fm.group(2)
            if key == "V":
                name = val.split()[0] if val.split() else "default"
                if name not in voices:
                    voices[name] = _Voice()
                    order.append(name)
                current = name
            elif key == "K":
                header["K"] = val
                in_body = True
            elif not in_body:
                header[key] = val
            elif key in "MQL":
                warnings.add(f"mid-score {key}:{val} ignored")
            continue
        if not in_body:
            continue
        if current is None:
            current = "default"
            voices[current] = _Voice()
            order.append(current)
        _parse_music(line, voices[current], section, warnings)

    for v in voices.values():
        v.close_bar()

    meter_str = header.get("M", "4/4").strip()
    meter_str = {"C": "4/4", "C|": "2/2"}.get(meter_str, meter_str)
    meter = _frac(meter_str, Fraction(4, 4))
    unit = _frac(header.get("L", "1/8"), Fraction(1, 8))
    qm = re.match(r"(?:(\d+/\d+)\s*=\s*)?(\d+(?:\.\d+)?)", header.get("Q", "1/4=120"))
    beat_len = _frac(qm.group(1), Fraction(1, 4)) if qm and qm.group(1) else Fraction(1, 4)
    tempo = float(qm.group(2)) if qm else 120.0
    bar_units = meter / unit                 # length of one bar in L units
    units_per_beat = beat_len / unit
    beats_per_bar = float(meter / beat_len)

    n_bars = max((len(v.bars) for v in voices.values()), default=0)
    counts = {k: len(v.bars) for k, v in voices.items()}
    if len(set(counts.values())) > 1:
        warnings.add(f"voices have different bar counts {counts}; using {n_bars}")
    vocal_names = [k for k in order if "vocal" in k.lower() or "voice" in k.lower()] or order[:1]

    bars = []
    first = last = None                      # (beat position) of first onset / last note end
    for b in range(n_bars):
        sec, chord, vocal = None, None, False
        for name in order:
            vb = voices[name].bars
            if b >= len(vb):
                continue
            bar = vb[b]
            sec = sec or bar["section"]
            chord = chord or bar.get("chord")
            sounding = [(on, d) for on, d, rest in bar["notes"] if not rest]
            if name in vocal_names and sounding:
                vocal = True
            for on, d in sounding:
                start = b * float(bar_units / units_per_beat) + float(on / units_per_beat)
                end = start + float(d / units_per_beat)
                first = start if first is None else min(first, start)
                last = end if last is None else max(last, end)
        bars.append({"index": b, "section": sec or "unknown", "chord": chord, "vocal": vocal})

    # carry chords forward so every bar names the harmony in effect
    prev = None
    for bar in bars:
        bar["chord"] = bar["chord"] or prev
        prev = bar["chord"]

    sections = []
    for bar in bars:
        if sections and sections[-1]["name"] == bar["section"] and sections[-1]["_open"]:
            sections[-1]["n_bars"] += 1
        else:
            if sections:
                sections[-1]["_open"] = False
            sections.append({"name": bar["section"], "start_bar": bar["index"], "n_bars": 1, "_open": True})
    for s in sections:
        s.pop("_open")

    return {
        "meter": meter_str,
        "tempo_bpm": tempo,
        "beats_per_bar": beats_per_bar,
        "n_bars": n_bars,
        "bars": bars,
        "sections": sections,
        "first_onset_beat": first,
        "last_end_beat": last,
        "voices": order,
        "warnings": sorted(warnings),
    }


def lyric_blocks(lyrics):
    """'[Verse]\\nline\\n[Chorus]...' -> [(tag, [lines])]"""
    blocks = []
    for line in lyrics.splitlines():
        line = line.strip()
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            blocks.append((m.group(1), []))
        elif line and blocks:
            blocks[-1][1].append(line)
    return blocks


def attach_lyrics(sections, lyrics):
    """Assign lyric blocks to score sections in order, matching by section name."""
    blocks = lyric_blocks(lyrics)
    used = 0
    for s in sections:
        s["lyrics"] = []
        key = norm_section(s["name"])
        if key in INSTRUMENTAL:
            continue
        for j in range(used, len(blocks)):
            if norm_section(blocks[j][0]) == key:
                s["lyrics"] = blocks[j][1]
                used = j + 1
                break
    return sections


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sc = parse_score(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps({k: v for k, v in sc.items() if k != "bars"}, indent=2, ensure_ascii=False))
    for b in sc["bars"]:
        print(b)
