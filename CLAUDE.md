# AI 音乐 MV 本地流水线

用开源模型在本地把一首歌做成音乐 MV。Claude Code 负责：写/改脚本、生成 ComfyUI 工作流参数、批量提交生成任务、按节拍剪辑成片。

## 硬件与环境
- RTX 5080 Laptop GPU，16GB GDDR7（Blackwell）。笔记本功耗受限：生成时插电 + 性能模式。
- PyTorch 必须是 cu128 或更新的 wheel（Blackwell 要求）。不要安装 cu121/cu124 版本。
- ComfyUI Desktop 安装在 `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI`（v0.45.4，自带 Python 3.13 + torch cu130）。**模型目录是 `E:\models`**（配置在 `%APPDATA%\Comfy Desktop\instance-model-paths\inst-*.yaml`，不是 ComfyUI-Shared\models）；输入图片目录 `D:\Comfy-Desktop\ComfyUI-Shared\input`。
  - 已有：LTX-2.3（i2v 与 ia2v 对口型共用同一套文件）、MiniMax H3 i2v。官方模板及其模型清单在 ComfyUI `.venv\Lib\site-packages\comfyui_workflow_templates_json\templates\`。
- **由 Claude 自行启停 ComfyUI**（用户已授权）：`python scripts/comfy_server.py start|status|stop`，无界面 headless 启动 Desktop 安装的 ComfyUI，模型路径/输入输出目录/端口与 Desktop 相同。跑 YuE2 前先 `stop` 释放显存。日志 `logs/comfy_server.log`。
- 缺模型时：`python scripts/fetch_models.py <官方模板名> [--dry-run]` 按模板清单下载到 `E:\models`（跳过已有，断点续传）。
- Chrome 扩展访问不到本机 127.0.0.1:8188，无法用前端 Export (API)；API 工作流按模板连线 + `/object_info` 手工构建，提交时由 `/prompt` 校验。
- 现有 API 工作流：`qwen21_t2i_api.json`（提示词 900.value、种子 458.seed、分辨率 456）、`qwen21_edit_api.json` / `qwen21_edit2_api.json`（1/2 张参考图 470/476.image，468.switch=True 用 456 的尺寸，False 用参考图尺寸）；提示词增强 474.switch（默认关）。
- ComfyUI Desktop 在本机运行，API 地址默认 `http://127.0.0.1:8188`（若端口不同，改 `scripts/comfy_client.py` 的 `--host`）。
- Python 依赖见 `requirements.txt`；ffmpeg 需在 PATH 中。

## 目录约定
```
music/      YuE2 每次生成的完整产物（music/<id>_<时间戳>/），requests/ 存请求 JSON；不要删除
audio/      原始歌曲（song.wav / song.mp3）
stems/      Demucs 分轨输出
analysis/   beats.json（节拍、强拍、段落、能量）
workflows/  ComfyUI 工作流，必须是 API 格式（ComfyUI 菜单 Export (API)）
shots/      shots.json 镜头表（每个镜头的提示词、时长、所属段落）
clips/      ComfyUI 生成的片段
output/     最终成片
scripts/    analyze_audio.py, comfy_client.py, assemble.py
```

## 音乐生成（YuE2，在 WSL 里）
- 位置：WSL Ubuntu `~/AI-Music/YuE`（YuE2 v0.1.6，`.venv/bin/yue2`），模型已缓存在 `~/.cache/huggingface/hub`。
- 16GB 显卡必须用 `--low-vram --budget 8`；`--offline` 跳过联网解析（校验从 ~157s 降到 ~7s）。实测 65s 歌曲约 76s 生成。
- YuE2 和 ComfyUI 共用显卡，**不能同时运行**：生成音乐前关闭 ComfyUI。
- 请求格式：`style`（曲风、乐器、人声、语言、BPM）+ `lyrics`（带 `[Verse]`/`[Chorus]` 等段落标签的真实歌词），可选 `seed`、`cot`（full/melody/off）。
- `score.abc` 含速度 `Q:`、拍号 `M:`、段落标记 `% verse` 等，是 MV 分段的可靠依据。

## 歌曲来源：Suno / 上传文件（可选，替代 YuE2）
- `python scripts/suno_music.py [--root <项目>] login|status|generate|download <id> [--confirm]|import <文件>`。`generate` 一次出 2 首（扣 Suno 积分），存 `music/suno_<时间>/clips.json`，再尝试下载第一首；下载/导入的歌转成 `audio/song.wav`，并把旧的 `analysis/score.abc` 改名为 `score_old_*.abc`（Suno 没有乐谱，分析走纯音频路径）。退出码 3 = 需要用户（未登录 / 下载要消耗下载额度 / 套餐不能下载）。
- 认证：`scripts/suno_api.py` 自己做 OAuth（动态注册客户端 + PKCE，回调 `http://127.0.0.1:8700/api/suno/callback` 或 CLI 的 `:8701/callback`），令牌存 `.suno/`（本机，勿外传）；通过 `https://api.suno.com/mcp` 的 JSON-RPC `tools/call` 调用与 Claude Code Suno 连接器相同的工具。
- **Free 套餐限制（2026-11 实测）**：MP3 下载每首扣 1 个下载额度（用户当时 0 个），WAV 需付费套餐。不要用播放流/CDN 链接绕过下载规则；没额度时让用户在 suno.com 自己下载后用"上传"导入。扣下载额度前必须用户明确批准（网页上是单独的确认按钮）。
- 网页：新建项目时选"歌曲来源"，或在歌曲阶段切换（本地 YuE2 / Suno / 上传音频文件）。需要用户时阶段停在"等待确认"（即使全自动模式），音乐阶段在没有可用歌曲时不能确认。Suno 歌曲的逐词时间（lyrics alignment）随下载存为 `<clip>_alignment.json`，尚未用于分析。

## 流水线
0. `python scripts/gen_music.py --id <name> --style "..." --lyrics-file <txt>` → `music/<id>_<时间戳>/`，并复制为 `audio/song.wav` + `analysis/score.abc`（`--stage plan` 只出乐谱预览）
1. `python scripts/analyze_audio.py audio/song.wav` → `analysis/beats.json`
   - 有 `analysis/score.abc` 时：小节/段落/和弦/人声小节来自乐谱（`scripts/abc_score.py` 解析），以第一个发声音符为锚点、拟合 librosa 节拍对齐到音频；歌词按 `[Verse]` 等标签挂到对应段落。
   - 对齐用 onset 包络上的节拍网格搜索（乐谱速度 ±4%），不依赖 librosa beat tracker（它在 breakbeat/DnB 鼓上会测错速度；YuE2 实际渲染速度也可能与 `Q:` 略有出入）。matched_beats 只是参考，看 WARNING 和 end_check。
   - 可疑时用 Demucs 人声分轨核对：乐谱 vocal 小节与分轨人声能量应一致（YuE2 偶尔不完全遵循自己的乐谱）。
   - 乐谱段落标记有误时（如 pre-chorus 并进 verse、乐谱休止但音频有内容），写 `analysis/structure.json` 按小节重定义段落，可加 `delivery`（rap / dance break 等）供分镜使用；带 `score_sha256` 绑定乐谱，换歌后自动失效。
   - 无乐谱（外部歌曲）或 `--no-score` 时退回纯音频分段。`--stems` 另跑 Demucs 分轨。
1b. `python scripts/singer_id.py` → `analysis/voices.json`：用 Demucs 人声分轨 + Sony CSL singer-identity 嵌入（HF `BernardoTorres/singer-identity`，TorchScript，CPU 即可）估计有几个不同声音、谁唱哪段。规则：**一个声音 = 一个成员 = 一张固定的脸**。
   - 参考标定：单人歌曲内部相似度 ≈0.91–0.94，不同歌曲（不同歌手）≈0.69–0.80。段落间质心相似度 >0.9 视为同一声音。
   - 局限：音色会被唱法/效果处理影响（如 vocal chop），rap 与演唱可能被判为同一人；结论需用户用耳朵确认。
2. 创意写在 `shots/shot_design.py`（每行：起止小节、成员、对口型成员、景别、首帧提示词、运动提示词；`{NOVA}`/`{ECHO}` 占位），`python scripts/build_shots.py` 按 beats.json 小节网格算时间、分配歌词 → `shots/shots.json`（校验小节全覆盖、对口型成员必须在画面里）。成员定义与参考图在 `shots/members.json`、`shots/refs/NOVA.png`/`ECHO.png`。
   根据 beats.json 的段落与能量写 `shots/shots.json`（Claude 负责起草，用户审核提示词）
3a. 首帧：`python scripts/gen_frames.py --range s001-s013 [--seed-offset N]` → `shots/frames/`（Qwen 2.1：无成员 t2i / 1 人 edit1 / 2 人 edit2，约 20–40s/张）；`shots/frames/index.json` 记录各版本与 chosen（可设 `"pinned": true` 锁定）。
3b. 视频：`python scripts/gen_videos.py --range s001-s013` → `clips/`（LTX-2.3：`workflows/ltx23_i2v_api.json`；对口型 `ltx23_ia2v_api.json`，自动切该镜头的人声分轨片段驱动口型）。1280×704@24fps，约 90–115s/镜头；生成时系统内存只剩 ~4GB，长跑前关掉大程序。ComfyUI 跑久了会占住 ~15GB 内存不释放，长跑前先 `comfy_server.py stop && start`（实测空闲可用内存 4.4GB→19.5GB）；内存过低时 Claude Code 会杀掉后台任务，clips/index.json 每个镜头即时写入，可用 `--range sNNN-s081` 续跑。`clips/index.json` 同上。
4. `python scripts/assemble.py --shots shots/shots.json --audio audio/song.wav [--start 0 --end 44.61] --out output/<name>.mp4`：每镜头按绝对时间轴取帧数填满自己的小节槽位（不漂移），无视频的镜头用首帧静帧占位。没有镜头覆盖的时间（第 1 小节前的前奏、空隙、尾奏）用舞台底图 `--filler shots/plates/stage.png` 补帧——以前不补，前奏 12.9s 的歌整片画面提前 12.9s，口型和节拍全错位（曾被误以为是混用 H3/LTX 导致）。
   - 提示词经验：别写 "signs"/招牌，模型会画乱码字母；要文字感用"屏幕上的波形/光"代替。
   - **连续性规则（用户反馈"有分裂感、故事不连续"后确立）**：每个镜头必须属于 `shot_design.py` 里的一个固定场景（`LOCATIONS` + `LOCATION_BY_BAR`）；场景底图 `shots/plates/<loc>.png`（`gen_frames.py --plates` 生成）作为最后一张参考图传给 Qwen 编辑（成员图在前，所以可能是 edit1/2/3）。同一段落内人物尽量留在同一场景；保持地理与方向一致（塔永远在 NOVA 街景画面右侧、NOVA 向右走）；交叉剪辑处用手势/方向做匹配剪辑。
   - **故事状态与因果（用户反馈"ECHO 已经出来了怎么又回去了 / NOVA 片段意义不明"后确立）**：角色状态要单调推进，不能倒退——ECHO 在 `ECHO_CAPTIVE_UNTIL`（舞蹈间奏胶囊破碎）之前的每个镜头都由 build_shots 自动加"被封在完好胶囊内、从玻璃外拍"；只写"手贴玻璃"模型会把她画到胶囊外面。每个 NOVA 镜头要有可读的因果（听见→逆人流走→看见 ECHO 被抹除→伸手→奔跑→声波传到塔→被挡在门外→爬邻楼），不要放纯装饰动作（燃烧广告牌、无关的广告牌下唱歌）。
   - **第三轮反馈（远景脸糊 / 麦克风漂浮 / 无理由跳舞 / 只有一人唱）后的规则**：有人物的镜头最远到 medium（腰部以上），LTX 1280×704 下远景人脸只有几十像素必糊；唱/rap 镜头写明 no microphone、手离开脸（模型会自己加麦克风然后漂走）；舞蹈动作必须有剧情动机（对抗警报激光、释放光波、庆祝人群），不要单独的 dance move；歌曲实际只有一个主声线（voices.json），用户选择按剧情分配口型：ECHO 唱前奏、bridge（她的歌声震裂玻璃）、间奏 86–87 小节（分析出的第二声线正好在这里）、最终副歌交替/齐唱（双人镜头 lipsync=ECHO，运动提示写 both sing together）。
   - **不要同时跑两个 gen_frames/gen_videos 进程**：它们各自读写 index.json，会互相覆盖 chosen（文件不丢，可按文件名重建 index）。
   - **表演版（用户在第三轮后决定改为固定场景唱跳）**：独立目录，不动故事版。设计 `shots/stage/shot_design.py`（单一霓虹街头舞台，靠灯光状态推进段落），产物 `shots/stage/{shots.json,plates,frames}`、`clips/stage/`，成片 `output/mv_stage_v*.mp4`。各脚本用 `--shots/--out/--frames/--clips-index/--frames-index/--plates` 指向这些路径。人群前景会把人物推远：双人舞蹈镜头写 "close to the camera, framed from the thighs up"。
   - **表演版 v2（`shots/stage2/`、`clips/stage2/`、`output/mv_stage_v2.mp4`）**：用户反馈后改为不跳舞（小模型跳舞肢体变形）、两人站在舞台上（底图从观众席台口拍，舞台地板和 LED 墙紧贴身后）、唱歌加互动（对视、靠肩、搭肩、背靠背）、手部规则（近景手出画，中景手臂自然下垂/插兜，不做伸手/指尖相触/手部特写）。LTX 经验：运动提示里写 "no faces" 反而会在 LED 屏上画人脸，改写"屏幕是纯色光"；双人中景容易自己拉远或走出画面，写 "static tripod shot, stay in place"；"push in" 会推得过近。
   - 前台分块跑视频：每块按预计耗时 ≤400s（1 小节镜头 ~70s，2 小节 ~85s），超过 600s 会被转后台、在内存紧张时被杀。
   - （旧）`comfy_client.py --workflow ... --shots ...` 通用提交器仍可用于一次性任务。

## Web 端 Agent（`webagent/`）
- 启动：`start_webagent.bat`（或 `.venv\Scripts\python -m webagent`）→ http://127.0.0.1:8700，只监听本机。`.venv` 是本项目的虚拟环境（`--system-site-packages` + `anthropic` SDK），不要往全局装包。
- 大脑是 Claude API（`webagent/brain.py`，`claude-opus-5-5`，流式 + 结构化 JSON 输出 + server-side refusal fallback）：写概念/歌词/成员形象、按 beats.json 写分镜行、挑成员参考图、首帧与视频质检（视觉，失败自动加修正提示词换种子重做，最多 2 次）。凭证：环境变量 `ANTHROPIC_API_KEY`，或网页里填（只存内存）。
- 每个项目是 `projects/<id>/` 下一份独立的流水线目录（audio/analysis/stems/shots/clips/output/workflows），引擎（`webagent/engine.py`）以该目录为工作目录调用 `scripts/` 里的同一套脚本；单 worker 串行跑（GPU 独占、避免 index.json 冲突），视频按 ≤400s 分块并在块间重启 ComfyUI。
- **界面布局**：左侧只是导航，分两组：音乐（音乐创作 Music maker `#create` / 音乐库 Music Lib `#library`）和 MV（MV 制作 MV maker `#mv` / MV 库 MV Lib `#mvlib`），下面是设置 `#settings`，底部 Claude 状态、GPU 队列、语言。内容按 URL hash 路由（`webagent/static/nav.js`；另有 `#song/<id>`、`#mv/<项目>`，项目页属于 MV 库；浏览器后退可用）。音乐创作页是中间大输入框 + 分类卡片墙 + 最近的歌；MV 制作页是新建表单 + 最近 4 个 MV；音乐库/MV 库是卡片（封面是按 id 生成的渐变，无图片）；底部播放器 `playSong()`。轮询用的 `tab` 变量：歌曲页 = "music"，项目页 = "mv"。静态文件带 `Cache-Control: no-cache`，改 `static/` 不用重启服务器。
- **两部分**：
  - **音乐工作室**：曲库 `songs/<id>/`（`webagent/studio.py`，`song.json` 状态 + `song.log`），每首歌目录与流水线布局相同（audio/song.wav、analysis/score.abc + song_source.json、music/ 各次生成），`gen_music.py`/`suno_music.py` 以 `--root .` 在里面运行。新建：写描述让 Claude 写歌名/曲风/歌词（`brain.song_draft`），或自己写；引擎 YuE2 / Suno；也可导入音频文件。歌曲任务排在同一个 GPU worker（队列目标写作 `song:<id>`）。
  - **分类（只用内置）**：`data/genres_builtin.json`（59 个，id `b_*`，group genre/region/mood，自带曲风提示和「通常为纯音乐」标记）。新建歌曲可选分类：Claude 写歌时 `song_draft(..., genre)` 按分类写（描述可空）；「自己写歌词」时曲风预填分类提示；选「通常纯音乐」的分类会自动勾纯音乐；歌曲 `song.json` 存 `genre` 副本。**Spotify 分类已从界面去掉（2026-11）**：Spotify 2026 年 2 月起对开发模式应用移除了 `/browse/categories`、`/browse/new-releases`、`/markets`、音频特征/分析、推荐、相似歌手等（凭证有效也 403/404），剩下的 search/artist/track 也不再返回曲风、热度，对写歌没有用。`scripts/spotify_genres.py` 留作命令行工具（拿到 Extended Quota 才能用），`spotify_genres.all_categories()` 仍会合并它拉到的 `data/genres.json`（如果有）。
  - **点选式音乐设定**：YuE2 请求只认 `style/lyrics/cot/seed/abc/cfg_scale/id` + 每请求的 `abc_sampling`/`semantic_sampling`（temperature/top_p/top_k/repetition_penalty/max_tokens；默认 abc 0.7/0.9/30/1.005/4096，semantic 1.0/0.95/100/1.2/9000≈6 分钟）——没有 bpm/人声/负面提示字段，这些都写在 style 文本里。所以：歌曲 `settings`（曲风类型、人声、语言、情绪≤3、乐器≤6、BPM、长度；可选值在 `studio.OPTIONS`，页面和 Claude 结构化输出共用）由页面拼成英文 style（`composeStyle`，手改过的 style 标 `style_custom`，再改设定前先确认）；Claude 写歌时按已选设定写并回填 settings；长度只影响歌词长短。YuE2 选项 `yue`（`studio.YUE_CHOICES` → `gen_music.py` 参数）：作曲方式 cot full/melody/off（纯音乐强制 full）、创意度（abc temperature 0.55/默认/0.9）、风格贴合度（cfg 默认/1.2/1.5，cfg≠1 跑两路更慢更占显存）、加长乐谱（abc max_tokens 6144 + semantic 13000，防长歌截断）、种子（手填的种子原样用，否则重新生成自动 +1）。`gen_music.py` 对应参数 `--cot --cfg-scale --abc-temperature --abc-top-p --abc-max-tokens --max-tokens`；cot=off 没有乐谱时把旧 `analysis/score.abc` 改名，避免分析用到上一首的谱。
  - **纯音乐**：歌曲勾选"纯音乐"（`instrumental`）就不需要歌词；Claude 写歌时描述里说纯音乐也会自动判定。Suno 用 `instrumental: true`；YuE2 用 `gen_music.py --instrumental`，按 YuE2 官方纯音乐流程分三步：空歌词 `--stage plan` 写谱 → `skills/yue2-music/instrumental/scripts/instrumental.py run --abc ... --prepare-only`（CPU，把 Vocal 旋律移到 Ins）→ 用 prepared 请求（带 `abc` 字段）以 `--low-vram` 渲染。不直接跑 instrumental.py 的生成：它没有 low-vram 选项、按 24GB 显卡写的。用纯音乐做 MV 时 concept 告诉 Claude 没人唱，分镜强制不对口型。
  - **MV 制作**：新建项目时从曲库选一首有音频的歌（`music.source="library"` + `song_id`），描述变为可选（画面想法）。concept 阶段 `brain.concept(brief, song)` 保留歌的标题/曲风/歌词，只设计画面；music 阶段 `import_song` 把音频、乐谱（YuE2 才有）、song_source.json、歌词复制进项目。项目歌曲步骤可"换一首"（`use_song`：概念画面不变，换歌词，分析起重置）。不选歌 = 旧方式（项目内 YuE2）；旧项目照旧。
- 阶段：concept → music(YuE2) → analysis(--stems) → refs(`scripts/gen_refs.py`) → design(`webagent/design.py` 把 Claude 的分镜行套上表演版 v2 规则模板写成 shot_design.py → build_shots → 舞台底图) → frames(+QC) → videos(+QC) → assemble。模式：review（每个关键节点等用户确认，可改提示词、单镜头重做）/ auto（一路跑完）。
- 为支持任意项目，脚本加了可选覆盖：`gen_music.py --root`，`gen_frames.py` 读 `MV_FRAME_STYLE`/`MV_KEEP_NEUTRAL`，`gen_videos.py` 读 `MV_VIDEO_STYLE` 和 members.json 的 `video_desc`，`build_shots.py` 用 members.json 的 `noun`。不设这些时行为与原来一致。
- 重跑 music/refs/design 会把旧的 frames/clips index.json 改名为 `index_old_<时间>.json`（文件都保留）。
- **可选 ComfyUI 工作流**：角色 t2i / edit1 / edit2 / edit3 / i2v / lipsync。`scripts/wf_bindings.py` 定义内置默认（原来写死的节点号）和“参数 → [节点, 输入]”映射；脚本从项目的 `workflows/bindings.json` 读取覆盖，没有该文件时行为与原来完全一致。网页“工作流”按钮：每个角色选库里的工作流，或导入 API 格式 JSON（自动猜节点，用户在下拉框核对；视频可映射秒数或帧数+帧率+N×k+1 规则）。用户工作流库在 `workflows/user/` + `workflows/library.json`，项目里存一份副本。
- **MiniMax H3（库里两条，只用于 i2v，无对口型）**：20 步版 ~15 分钟/镜头，内存紧张时会崩；“8 步加速”版（105:126=True）实测 284s/镜头（含冷加载），运镜比 LTX 稳（LTX 常自己推近）、人群更有动感，需 ~20GB 空闲内存。库条目可带 `est_seconds`（每镜头预计秒数）和 `chunk_budget`（每次 ComfyUI 会话的秒数预算），引擎据此分块；视频阶段按角色分组（先全部 i2v 再全部 lipsync），一个块里不混两个模型。
- 服务器不会热加载代码：改了 `webagent/` 必须重启服务器（`scripts/` 是子进程，立即生效）。端口 8700 被旧进程占着时 `python -m webagent` 会提示并退出。

## 模型选择（按镜头类型）
| 镜头 | 模型/工作流 | 备注 |
|---|---|---|
| 抽象、音频反应 | LTX 2.3 + Audio-Reactive LoRA；或 AnimateDiff + Yvann-Nodes | 16GB 轻松 |
| 一般场景空镜 | Wan 2.2 5B（720p）或 14B fp8/GGUF（480p 起步） | 14B 需内存卸载，较慢 |
| 人物唱歌 | Wan2.2-S2V 或 InfiniteTalk（fp8） | 先用 480p、短段落测试 |
| 修口型 | LatentSync | 后处理 |
| 跳舞 | Wan Dancer | |

## Git / GitHub
- 公开仓库 https://github.com/shi0275206485-dev/Arti-2M（分支 `main`）。只提交代码和设计源文件；`.gitignore` 排除所有生成的媒体（projects/ songs/ music/ audio/ stems/ clips/ output/ analysis/ shots 下的 frames/plates/stage*）、`.venv/`、`logs/`，以及凭证 `.suno/`、`.spotify/`。公开仓库：提交前确认没有密钥、令牌或个人信息。
- 本仓库提交身份是 GitHub noreply 邮箱（仓库级 `git config user.email`），不要改回个人邮箱。只在用户要求时提交/推送。

## 工作规则
- 先低分辨率、短时长测试构图和节奏，用户确认后再出高清。
- 镜头时长对齐到节拍：切点优先落在 downbeat（小节第一拍），副歌加快切换频率。
- 提交大批量生成前，先告知用户镜头数和预计耗时，并确认。
- 不要删除 `clips/` 中已生成的片段；重新生成时用新文件名。
- 修改工作流时只改 API JSON 里的参数节点（提示词、种子、帧数、分辨率），不要重排节点 ID。
