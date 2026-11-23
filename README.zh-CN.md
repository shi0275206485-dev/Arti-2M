# Arti-2M

[English](README.md) | **简体中文**

在自己的电脑上，用开源模型把一个想法变成一首歌，再把这首歌变成音乐 MV。
本地网页应用（MV Agent）由 Claude 担任导演：写歌、设计分镜、检查每一张首帧和每一段视频；
真正的生成全部在本地完成（音乐用 YuE2，图像和视频用 ComfyUI）。

## 功能

**音乐**
- **音乐创作**：写一句描述，或者只选一个分类，Claude 就会写好歌名、曲风和歌词。
- **点选式设定**，不用写长提示词：曲风类型、人声、语言、情绪、乐器、速度、长度。
- **三种歌曲来源**：本地 **YuE2**（默认）、**Suno**（可选，走官方 API），或者导入自己的音频文件。
- **纯音乐**：不需要歌词，按 YuE2 官方流程完成：先写谱，再把旋律移到乐器声部，最后生成。
- **分类**：59 个内置分类（音乐类型 / 地区 / 情绪），另外可以选配 Spotify 分类。
- **YuE2 生成选项**都用白话写成：作曲方式、创意度、风格贴合度、加长乐谱上限、种子。

**MV**
- **概念**：Claude 围绕歌曲设计画面故事。
- **节拍与段落分析**：依据 YuE2 乐谱（没有乐谱时只用音频），并用 Demucs 分轨、识别歌手。
- **角色与分镜**：保持形象一致的成员参考图、按小节对齐的分镜表、舞台 / 场景底图。
- **首帧**：在 ComfyUI 里用 Qwen 图像模型生成。
- **视频**：LTX-2.3 图生视频和音频驱动的对口型，也可以用 MiniMax H3。
- **自动质检**：Claude 检查每一张首帧和每一段视频，不合格的会改好提示词再重做。
- **按节拍剪辑**成最终的 MP4。
- **两种运行模式**：每个关键节点等你确认，或者全自动。

**网页**
- **导航**：左侧菜单（音乐创作 · 音乐库 · MV 制作 · MV 库 · 设置），底部有播放器。
- **语言**：界面支持中文 / 英文。

## 流程

```
想法 / 分类 ──► Claude 写歌 ──► YuE2 / Suno / 上传 ──► audio/song.wav + score.abc
                                                              │
          ┌───────────────────────────────────────────────────┘
          ▼
   节拍/段落分析 ─► 成员参考图 ─► 分镜设计 ─► 首帧（Qwen）─► 视频片段（LTX-2.3 / H3）
                                                │ Claude 质检       │ Claude 质检
                                                ▼                   ▼
                                         按节拍剪辑 ─► output/*.mp4
```

## 环境要求

| | |
|---|---|
| 系统 | Windows 10/11 + **WSL 2**（Ubuntu） |
| 显卡 | NVIDIA，已在 **16GB 显存**上测试（RTX 5080 Laptop；Blackwell 需要 PyTorch cu128 及以上） |
| 音乐 | 在 WSL 中安装 [YuE2](https://github.com/multimodal-art-projection/YuE)（`~/AI-Music/YuE`），用 `--low-vram --budget 8` 运行 |
| 图像 / 视频 | [ComfyUI](https://www.comfy.org/)（Desktop），装好 Qwen 图像、LTX-2.3 模型（MiniMax H3 可选） |
| 工具 | Python 3.13，`ffmpeg` 在 PATH 中 |
| Claude | Anthropic API Key |
| 可选 | Suno 账号；Spotify 开发者应用（Client ID / Secret），用于 Spotify 分类 |

YuE2 和 ComfyUI 共用显卡，不能同时运行。生成音乐前，Agent 会自动关闭 ComfyUI。

## 快速开始

```bat
git clone https://github.com/shi0275206485-dev/Arti-2M.git
cd Arti-2M
python -m venv --system-site-packages .venv
.venv\Scripts\pip install -r requirements.txt
start_webagent.bat
```

1. 浏览器会打开 **http://127.0.0.1:8700**，服务只在本机监听。
2. 进入 **设置**，填入 Anthropic API Key。Key 只保存在服务器内存里，重启后要重新填。
3. **音乐创作**：选一个分类，或者写一句描述 → **Claude 写歌** → 调整设定 → 生成。
4. **MV 制作**：从音乐库选一首做好的歌，写上画面想法（可选）→ **开始**。

缺少 ComfyUI 模型时，可以按官方模板的模型清单下载：
`python scripts/fetch_models.py <模板名> [--dry-run]`。

## 命令行脚本

网页能做的事情都有对应的脚本（在项目根目录运行，或者用 `--root <目录>` 指定）：

```bash
python scripts/gen_music.py --id city --style "Mandopop ballad, piano, female vocal, 76 BPM" --lyrics-file lyrics.txt
python scripts/gen_music.py --id calm --style "warm solo piano, 72 BPM" --instrumental
python scripts/suno_music.py login | status | generate ... | download <id> [--confirm] | import <文件>
python scripts/analyze_audio.py audio/song.wav [--stems]
python scripts/singer_id.py
python scripts/build_shots.py
python scripts/gen_frames.py --range s001-s013
python scripts/gen_videos.py --range s001-s013
python scripts/assemble.py --shots shots/shots.json --audio audio/song.wav --out output/mv.mp4
python scripts/comfy_server.py start | status | stop
```

## 目录结构

```
scripts/      流水线脚本（音乐、分析、首帧、视频、剪辑，Suno / Spotify 客户端）
webagent/     网页应用：FastAPI 服务、Claude「大脑」、任务引擎、前端页面
workflows/    ComfyUI 工作流（API 格式）和工作流库
shots/        示例分镜设计（shot_design.py）、成员定义和参考图
data/         内置分类表（genres_builtin.json）
CLAUDE.md     详细的工作笔记：硬件、约定、踩过的坑
```

生成的媒体文件（`songs/`、`projects/`、`music/`、`audio/`、`clips/`、`output/` 等）和凭证
（`.suno/`、`.spotify/`）都由 `.gitignore` 排除，不会进仓库。

## 许可证

本仓库的代码以 [MIT 许可证](LICENSE) 发布。

## 说明

- **第三方许可**：MIT 许可证只适用于本仓库的代码。各模型权重（YuE2、Qwen、LTX-2.3、MiniMax、Demucs 等）和第三方服务（Claude、Suno、Spotify）有各自的许可与条款。商用生成内容前请先确认。
- **Suno**：只有在你逐首明确批准后才会消耗下载额度。应用遵守免费套餐的限制，不会绕过。
- **AI 生成内容**：生成的音乐可能有瑕疵，纯音乐也不保证完全没有人声。发布前请先试听。
