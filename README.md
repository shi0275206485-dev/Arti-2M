# Arti-2M

**English** | [简体中文](README.zh-CN.md)

Turn an idea into a song, and the song into a music video, on your own PC with open-source models.
A local web app (the "MV Agent") uses Claude as the director: it writes songs, plans shots and checks
every generated frame and clip, while the heavy lifting runs locally (YuE2 for music, ComfyUI for images and video).

## What it does

**Music**
- **Music maker**: describe a song, or just pick a category, and Claude writes the title, style and lyrics.
- **Click-to-choose settings** instead of long prompts: sub-genre, vocals, language, moods, instruments, tempo, length.
- **Three song sources**: local **YuE2** (default), **Suno** (optional, through its official API), or import your own audio file.
- **Instrumental songs**, no lyrics needed (YuE2's plan → move melody to instrument → render workflow).
- **Categories**: 59 built-in genres / regions / moods, each with a style hint written for the generators.
- **YuE2 options** with plain-language labels: composition mode, creativity, style adherence, a longer score limit, seed.

**Music video**
- **Concept**: Claude designs the visual story around the song.
- **Beat and section analysis** from YuE2's score (or from audio alone), plus Demucs stems and singer identification.
- **Characters and shots**: consistent member reference images, a bar-aligned shot list, stage/location plates.
- **Frames**: Qwen image models in ComfyUI.
- **Video**: LTX-2.3 image-to-video and audio-driven lip-sync, or MiniMax H3.
- **Automatic quality checks**: Claude reviews every frame and clip and retries failures with corrected prompts.
- **Beat-synced assembly** into the final MP4.
- **Two run modes**: review at each key step, or fully automatic.

**Web app**
- **Navigation**: left-side menu (Music maker · Music Lib · MV maker · MV Lib · Settings), with a bottom player.
- **Language**: English / Chinese interface.

## Pipeline

```
idea / category ──► Claude writes song ──► YuE2 / Suno / upload ──► audio/song.wav + score.abc
                                                                         │
            ┌────────────────────────────────────────────────────────────┘
            ▼
   beat & section analysis ─► member refs ─► shot design ─► first frames (Qwen) ─► video clips (LTX-2.3 / H3)
                                                                │ Claude QC          │ Claude QC
                                                                ▼                    ▼
                                                        beat-synced assembly ─► output/*.mp4
```

## Requirements

| | |
|---|---|
| OS | Windows 10/11 with **WSL 2** (Ubuntu) |
| GPU | NVIDIA, **16 GB VRAM** tested (RTX 5080 Laptop; Blackwell needs PyTorch cu128+) |
| Music | [YuE2](https://github.com/multimodal-art-projection/YuE) installed in WSL (`~/AI-Music/YuE`), run with `--low-vram --budget 8` |
| Images / video | [ComfyUI](https://www.comfy.org/) (Desktop) with Qwen image, LTX-2.3 (and optionally MiniMax H3) models |
| Tools | Python 3.13, `ffmpeg` on PATH |
| Claude | An Anthropic API key |
| Optional | A Suno account |

YuE2 and ComfyUI share the GPU and must not run at the same time. The agent stops ComfyUI before generating music.

## Quick start

```bat
git clone https://github.com/shi0275206485-dev/Arti-2M.git
cd Arti-2M
python -m venv --system-site-packages .venv
.venv\Scripts\pip install -r requirements.txt
start_webagent.bat
```

1. Your browser opens **http://127.0.0.1:8700**. The server listens on this machine only.
2. Go to **Settings** and paste your Anthropic API key. It is kept in server memory only, so enter it again after a restart.
3. **Music maker**: pick a category or describe a song → **Claude writes it** → adjust settings → generate.
4. **MV maker**: pick a finished song from the library, add visual ideas (optional) → **Start**.

Missing ComfyUI models can be downloaded from a template's model list:
`python scripts/fetch_models.py <template-name> [--dry-run]`.

## Command-line scripts

Everything the web app does is also available as a script (run from the project root, or pass `--root <folder>`):

```bash
python scripts/gen_music.py --id city --style "Mandopop ballad, piano, female vocal, 76 BPM" --lyrics-file lyrics.txt
python scripts/gen_music.py --id calm --style "warm solo piano, 72 BPM" --instrumental
python scripts/suno_music.py login | status | generate ... | download <id> [--confirm] | import <file>
python scripts/analyze_audio.py audio/song.wav [--stems]
python scripts/singer_id.py
python scripts/build_shots.py
python scripts/gen_frames.py --range s001-s013
python scripts/gen_videos.py --range s001-s013
python scripts/assemble.py --shots shots/shots.json --audio audio/song.wav --out output/mv.mp4
python scripts/comfy_server.py start | status | stop
```

## Project layout

```
scripts/      pipeline scripts (music, analysis, frames, videos, assembly, Suno client)
webagent/     the web app: FastAPI server, Claude "brain", job engine, static UI
workflows/    ComfyUI workflows in API format + workflow library
shots/        example shot design (shot_design.py), members and reference images
data/         built-in category list (genres_builtin.json)
CLAUDE.md     detailed working notes (Chinese): hardware, conventions, lessons learned
```

Generated media (`songs/`, `projects/`, `music/`, `audio/`, `clips/`, `output/` …) and credentials
(`.suno/`, `.spotify/`) are kept out of the repository by `.gitignore`.

## License

The code in this repository is released under the [MIT License](LICENSE).

## Notes

- **Third-party licenses**: the MIT license covers this repository's code only. Model weights (YuE2, Qwen, LTX-2.3, MiniMax, Demucs …) and third-party services (Claude, Suno) have their own licenses and terms. Check them before using generated content commercially.
- **Suno**: download credits are only spent after you explicitly approve each download. Free-plan limits are respected; the app never works around them.
- **AI output**: generated music can contain artifacts, and instrumental tracks are not guaranteed to be vocal-free. Listen before you publish.
