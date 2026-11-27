// UI language (zh / en). Strings in the code are written in Chinese and wrapped in t(); EN maps them to English.
// Placeholders {0}, {1}... are filled from t()'s extra arguments in both languages.
let LANG = "zh";
try { LANG = localStorage.getItem("mv_lang") === "en" ? "en" : "zh"; } catch (e) { /* storage blocked */ }

const EN = {
  // status / sidebar
  "未开始": "Pending", "进行中": "Running", "等待确认": "Awaiting review", "完成": "Done", "出错": "Error",
  "Claude 已连接": "Claude connected", "Claude 未配置": "Claude not set up", "Claude …": "Claude …",
  "运行中：{0}": "Running: {0}", "（队列 {0}）": " (queue {0})", "空闲": "Idle",
  "{0}/{1} 步": "{0}/{1} steps", "全自动": "Fully automatic", "确认模式": "Review mode", "关键节点确认": "Review at checkpoints",
  "ANTHROPIC_API_KEY（仅保存在内存）": "ANTHROPIC_API_KEY (kept in memory only)", "设置": "Settings", "保存 Key": "Save key",
  "新建 MV": "New MV", "名称，例如 RESCUE": "Name, e.g. RESCUE",
  "主题、曲风、语言、人数与形象、BPM、氛围……\n例：K-pop 女团双人，英语+韩语，130 BPM drum&bass，主题救赎，赛博朋克霓虹街头舞台":
    "Theme, genre, language, number of members and their looks, BPM, mood…\nE.g. K-pop girl duo, English + Korean, 130 BPM drum & bass, theme: redemption, cyberpunk neon street stage",
  "开始": "Start", "项目": "Projects", "新建或选择一个项目": "Create or select a project",
  "工作流": "Workflows", "为每个生成环节选择 ComfyUI 工作流，或导入自己的 API 工作流":
    "Choose the ComfyUI workflow for each generation step, or import your own API workflow",
  "停止当前任务": "Stop current task", "日志": "Log",
  // stage actions
  "确认，进入下一步": "Approve, next step", "重试此步": "Retry this step", "运行此步": "Run this step",
  // concept
  "Claude 正在根据你的描述写概念、歌词和成员形象…": "Claude is writing the concept, lyrics and member looks from your brief…",
  "标题": "Title", "曲风": "Style", "舞台底图": "Stage plate", "画面风格": "Visual style", "成员": "Members",
  "灯光状态": "Lighting states", "歌词": "Lyrics", "保存修改": "Save changes", "已保存": "Saved",
  "重新让 Claude 写概念？当前修改会丢失。": "Have Claude rewrite the concept? Your current edits will be lost.",
  "重新生成概念": "Regenerate concept",
  // music / analysis / refs
  "种子 {0} · 已生成 {1} 版": "Seed {0} · {1} version(s) generated", "上一版被截断": "previous version was truncated",
  "YuE2 生成中（约 2–4 分钟，会先关闭 ComfyUI）…": "YuE2 is generating (about 2–4 min; ComfyUI is stopped first)…",
  "换种子重新生成": "Regenerate with a new seed",
  "纯音乐": "Instrumental", "纯音乐（无歌词）": "Instrumental (no lyrics)", "纯音乐（无人声，不需要歌词）": "Instrumental (no vocals, no lyrics needed)",
  "YuE2 纯音乐：先写谱，再把旋律移到乐器声部，然后生成（比有歌词的多一步规划）。不保证完全没有人声，请试听。":
    "YuE2 instrumental: it plans a score, moves the melody to an instrument voice, then renders (one extra planning step). Vocal-free audio is not guaranteed; listen to it.",
  "先写曲风（或让 Claude 写）": "Write a style first (or let Claude write it)",
  "分类": "Category", "不选分类": "No category", "参考曲风": "Typical style",
  "（Claude 还没写这个分类的曲风提示）": "(Claude hasn't written a style hint for this category yet)",
  "Spotify 分类": "Spotify categories",
  "音乐类型": "Genre", "地区 / 语言": "Region / language", "情绪 / 场景": "Mood / activity",
  "选一个分类或写一段描述，Claude 据此写歌": "Pick a category or write a description for Claude to write the song from",
  "曲风提示词": "Style prompt",
  "（由上面的设定自动生成，也可以直接改）": "(built from the settings above; you can also edit it directly)",
  "曲风是手动写的；再改上面的设定会重新生成并覆盖它。": "The style was written by hand; changing the settings above will rebuild and replace it.",
  "曲风是手动写的。按设定重新生成会覆盖它，继续？": "The style was written by hand. Rebuilding it from the settings will replace it. Continue?",
  "正在读取选项…": "Loading options…",
  "（自动）": "(auto)",
  "音乐设定": "Music settings",
  "点选即可；Claude 写歌时也会按这些来": "Just click; Claude follows these when it writes the song",
  "清空设定": "Clear settings",
  "曲风类型": "Sub-genre",
  "例如 Mandopop ballad、melodic techno（英文更好）": "e.g. Mandopop ballad, melodic techno (English works best)",
  "人声": "Vocals",
  "语言": "Language",
  "情绪": "Mood",
  "乐器": "Instruments",
  "速度": "Tempo",
  "自动": "Auto",
  "长度": "Length",
  "（决定 Claude 写多长的歌词）": "(sets how long Claude makes the lyrics)",
  "完整规划（推荐）": "Full plan (recommended)",
  "先写旋律+和弦乐谱再生成；MV 分析的小节/段落最准": "Writes a melody + chord score first; gives the most accurate bars/sections for MV analysis",
  "只规划旋律": "Melody plan only",
  "和弦与伴奏交给模型自由发挥": "Leaves chords and accompaniment to the model",
  "不规划": "No plan",
  "直接生成，最自由；没有乐谱，MV 只能按音频分析（纯音乐不可用）": "Generates directly, the freest; no score, so MV analysis uses audio only (not for instrumentals)",
  "稳定": "Steady",
  "旋律更规整、重复更多": "More regular melodies, more repetition",
  "标准": "Standard",
  "YuE2 默认": "YuE2 default",
  "大胆": "Bold",
  "旋律更多变化，也更容易跑偏": "More varied melodies, but more likely to wander",
  "加强": "Stronger",
  "更贴近曲风描述（较慢，更占显存）": "Follows the style prompt more closely (slower, more VRAM)",
  "很强": "Strongest",
  "实验性；可能牺牲音质": "Experimental; may cost sound quality",
  "YuE2 生成选项": "YuE2 options",
  "（默认就好；想要不同效果再调）": "(defaults are fine; adjust for a different result)",
  "作曲方式": "Composition",
  "创意度": "Creativity",
  "风格贴合度": "Style adherence",
  "长歌": "Long songs",
  "加长乐谱上限": "Raise the score length limit",
  "长歌或密集的编曲不会在结尾被截断（更慢，更占显存）": "Long songs or dense arrangements won't get cut off at the end (slower, more VRAM)",
  "随机": "Random",
  "同样的设定 + 同一个种子 = 同一首歌；「换种子重新生成」会自动换": "Same settings + same seed = same song; \"Regenerate with a new seed\" changes it for you",
  "清空音乐设定？（曲风提示词保留，之后 Claude 写歌会重新选）": "Clear the music settings? (The style prompt stays; Claude will choose again next time it writes.)",
  "提交中…": "Submitting…", "没有开始生成：{0}": "Generation did not start: {0}",
  "没有开始：{0}": "Did not start: {0}", "保存失败：{0}": "Save failed: {0}",
  "已连接。可以在下面换一个 Key。": "Connected. You can replace the key below.",
  "还没有 Key：Claude 写歌、写分镜和质检都需要它。": "No key yet: Claude needs it to write songs, design shots and check quality.",
  "还没有 MV 项目：在上面新建一个。": "No MV projects yet: create one above.",
  "曲库是空的：在「创作」里写第一首歌，或导入音频文件。": "The library is empty: write your first song under Create, or import an audio file.",
  "还没有歌。": "No songs yet.",
  "创作": "Create",
  "想要一首什么样的歌？": "What song do you want?",
  "Claude 还没连接：点这里去设置填 API Key": "Claude isn't connected: click here to enter an API key in Settings",
  "按分类开始": "Start from a category",
  "最近的歌": "Recent songs",
  "全部": "All",
  "← 曲库": "← Library",
  "名称": "Name",
  "画面想法": "Visual ideas",
  "模式": "Mode",
  "← MV 制作": "← MV maker",
  "Key 只保存在服务器内存里：重启服务器后要重新填。": "The key is kept only in the server's memory: enter it again after a server restart.",
  "描述你想要的歌：主题、语言、人声、氛围……（选了分类时可以不写）": "Describe the song you want: theme, language, vocals, mood… (optional when a category is picked)",
  "音乐": "Music",
  "音乐创作": "Music maker",
  "音乐库": "Music Lib",
  "MV 库": "MV Lib",
  "← 音乐库": "← Music Lib",
  "← MV 库": "← MV Lib",
  "最近的 MV": "Recent MVs",
  "还没有 MV 项目：去「MV 制作」新建一个。": "No MV projects yet: create one in MV maker.",
  "还没有 MV 项目。": "No MV projects yet.",
  "音乐库是空的：在「音乐创作」里写第一首歌，或导入音频文件。": "The music library is empty: write your first song in Music maker, or import an audio file.",
  "Suno 生成的 2 首：先在 suno.com 试听，再选一首": "Suno made 2 takes: listen on suno.com, then pick one",
  "正在读取下载额度…": "Checking your download credits…",
  "你有 {0} 个下载额度：选中的那首由应用下载（消耗 1 个）。": "You have {0} download credits: the app downloads the take you pick (uses 1).",
  "你的 Suno 账户没有下载额度（免费版）：选中后在 suno.com 自己下载 MP3，再导入到这首歌。": "Your Suno account has no download credits (Free plan): after picking, download the MP3 on suno.com yourself and import it into this song.",
  "用这首（下载，消耗 1 个下载额度）": "Use this one (download, uses 1 download credit)",
  "选这首": "Pick this one",
  "在 suno.com 试听 ↗": "Listen on suno.com ↗",
  "在 suno.com 打开这首（上面的链接）→ 「⋯」→ 下载 → MP3": "Open this take on suno.com (link above) → \"⋯\" → Download → MP3",
  "选择下载好的文件，导入到这首歌：": "Choose the downloaded file to import it into this song:",
  "如果 suno.com 也不让你下载这首，免费版就只能在线听；可以换 YuE2 本地生成。": "If suno.com doesn't let you download it either, the Free plan can only stream it; you can generate locally with YuE2 instead.",
  "导入失败：{0}": "Import failed: {0}",
  "下载这首歌要消耗 1 个 Suno 下载额度。可以批准下载，或者在 suno.com 自己下载后导入（见下面的两首）。": "Downloading this song uses 1 Suno download credit. Approve it, or download it on suno.com yourself and import it (see the two takes below).",
  "Suno 生成了 2 首：先在 suno.com 试听，再在下面选一首。": "Suno made 2 takes: listen on suno.com first, then pick one below.",
  "音乐工作室": "Music studio", "MV 制作": "MV maker", "新建歌曲": "New song",
  "主题、语言、人声、BPM、氛围……（选了分类时可不写）\nClaude 据此写歌名、曲风和歌词": "Theme, language, vocals, BPM, mood… (optional when a category is picked)\nClaude writes the title, style and lyrics from this",
  "引擎": "Engine", "Claude 写歌": "Claude writes it", "自己写歌词": "Write my own lyrics", "导入音频文件": "Import audio file",
  "导入到曲库": "Import to library", "曲库": "Library", "曲库是空的": "The library is empty", "（未命名）": "(untitled)",
  "歌曲": "Song", "画面想法（可选）：人数与形象、舞台、氛围……\n不选曲库的歌时，这里还要写主题、曲风、语言、BPM":
    "Visual ideas (optional): members and looks, stage, mood…\nWithout a library song, also give the theme, genre, language and BPM",
  "不选：在项目里用 YuE2 生成（旧方式）": "None: generate with YuE2 inside the project (old way)",
  "请填写名称": "Please enter a name", "新建或选择一首歌": "Create or select a song",
  "Claude 写歌词中": "Claude writing", "草稿": "Draft", "生成中": "Generating", "等待你处理": "Needs you", "可用": "Ready",
  "导入的文件": "Imported file", "种子 {0}": "Seed {0}", "无乐谱，MV 分析只按音频切小节/段落": "no score: MV analysis finds bars/sections from the audio only",
  "带乐谱（小节/段落更准）": "with score (more precise bars/sections)", "Claude 正在根据描述写歌名、曲风和歌词…": "Claude is writing the title, style and lyrics from the brief…",
  "导入中…": "Importing…", "先登录 Suno（下方按钮），再点「生成」。": "Sign in to Suno first (button below), then click Generate.",
  "下载这首歌要消耗 1 个 Suno 下载额度。可以批准下载，或者在 suno.com 自己下载后用左侧「导入音频文件」导入。":
    "Downloading this song uses 1 Suno download credit. Approve it, or download it yourself on suno.com and use Import audio file on the left.",
  "Suno 无法下载这首歌（{0}）：请在 suno.com 自己下载后导入。": "Suno can't download this song ({0}): download it on suno.com and import it.",
  "描述": "Brief", "给 Claude 的描述（重写歌词时用）": "Brief for Claude (used when rewriting)", "用 YuE2 生成": "Generate with YuE2",
  "让 Claude 重写歌词": "Have Claude rewrite", "歌词（可选，MV 用来挂歌词）": "Lyrics (optional; the MV uses them to place lyrics)",
  "用这首做 MV": "Make an MV with this song", "用在 MV 项目：": "Used in MV projects: ",
  "让 Claude 按描述重写歌名、曲风和歌词？当前内容会被替换。": "Have Claude rewrite the title, style and lyrics from the brief? The current text will be replaced.",
  "先写曲风和歌词（或让 Claude 写）": "Write a style and lyrics first (or let Claude write them)", "用 Suno 生成 2 首？会消耗 Suno 积分。": "Generate 2 songs with Suno? This spends Suno credits.",
  "删除": "Delete", "没有删除：{0}": "Not deleted: {0}", "任务进行中，不能删除": "A job is running; can't delete now",
  "删除歌曲「{0}」？\n文件夹会移到 trash/songs/（需要时可以手动移回来）。已经用这首歌做的 MV 不受影响。": "Delete the song \"{0}\"?\nIts folder moves to trash/songs/ (you can move it back by hand). MVs already made with it are not affected.",
  "删除 MV「{0}」？\n项目文件夹（含所有画面、视频和成片）会移到 trash/projects/（需要时可以手动移回来）。": "Delete the MV \"{0}\"?\nThe project folder (all frames, clips and the final cut) moves to trash/projects/ (you can move it back by hand).",
  "封面生成中…": "Making cover art…", "封面生成失败：{0}": "Cover art failed: {0}", "重新生成封面": "New cover",
  "生成封面": "Make cover", "自己写封面提示词": "Write the cover prompt yourself",
  "英文描述画面，留空则由 Claude 根据歌名、曲风和歌词来写": "Describe the image in English; leave empty and Claude writes it from the title, style and lyrics",
  "用这个提示词生成": "Generate with this prompt", "先写提示词（或点「重新生成封面」让 Claude 写）": "Write a prompt first (or click \"New cover\" to let Claude write one)",
  "写一段描述，Claude 据此写歌":"Write a brief for Claude to write the song from", "新歌": "New song",
  "歌曲来自音乐工作室：": "Song from the music studio: ", "运行这一步会把曲库里的歌复制到项目。": "Running this step copies the library song into the project.",
  "这首歌还没有音频：先在音乐工作室生成完。": "This song has no audio yet: finish it in the music studio first.", "换一首": "Use another song", "换成这首": "Switch to this song",
  "换歌后，分析及之后的步骤会重新开始（已生成的文件保留）；概念的画面设计不变，歌名/歌词换成新歌的。":
    "After switching, analysis and every later step start over (generated files are kept); the concept keeps its visuals and takes the new song's title and lyrics.",
  "换成这首歌？分析及之后的步骤会重新开始。": "Switch to this song? Analysis and every later step start over.",
  "歌曲来源": "Song source", "本地 YuE2": "Local YuE2", "上传音频文件": "Upload audio file",
  "当前歌曲来自：{0}": "Current song from: {0}", "无乐谱，分析阶段只按音频切小节/段落": "no score, so analysis finds bars/sections from the audio only",
  "Suno 生成中（一次 2 首，约 1–3 分钟）…": "Suno is generating (2 songs per run, about 1–3 min)…",
  "先登录 Suno，再点「运行此步」生成。": "Sign in to Suno first, then click Run this step.",
  "下载这首歌要消耗 1 个 Suno 下载额度。可以批准下载，或者在 suno.com 自己下载后上传文件。":
    "Downloading this song uses 1 Suno download credit. Approve it, or download it yourself on suno.com and upload the file.",
  "上传一个音频文件（mp3 / wav / flac …）。": "Upload an audio file (mp3 / wav / flac …).",
  "Suno 无法下载这首歌（{0}）：请在 suno.com 自己下载后上传文件。": "Suno can't download this song ({0}): download it yourself on suno.com and upload the file.",
  "正在读取 Suno 账户…": "Reading Suno account…", "Suno 生成的歌（一次 2 首，选一首用）": "Songs from Suno (2 per run, pick one)",
  "在 suno.com 试听 / 手动下载": "Listen / download on suno.com", "正在使用": "In use",
  "批准：消耗 1 个下载额度": "Approve: spend 1 download credit", "下载并使用这首": "Download and use this one",
  "用 Suno 再生成 2 首？会消耗 Suno 积分。": "Generate 2 more songs with Suno? This spends Suno credits.",
  "重新生成（消耗 Suno 积分）": "Regenerate (spends Suno credits)", "用 Suno 生成（消耗 Suno 积分）": "Generate with Suno (spends Suno credits)",
  "或者：上传你在 suno.com 下载的文件": "Or: upload the file you downloaded from suno.com", "上传并使用": "Upload and use",
  "已登录 Suno": "Signed in to Suno", "积分 {0}": "{0} credits", "下载额度 {0}": "{0} download credits", "退出": "Sign out",
  "未登录 Suno": "Not signed in to Suno", "登录 Suno": "Sign in to Suno", "在新标签页完成登录后点": "After signing in in the new tab, click",
  "刷新": "Refresh", "确定消耗 1 个 Suno 下载额度下载这首歌？": "Spend 1 Suno download credit to download this song?",
  "先选择一个音频文件": "Choose an audio file first", "上传中…": "Uploading…",
  "按乐谱/节拍切小节、段落和人声小节，并用 Demucs 分离人声（供对口型）。":
    "Splits bars, sections and vocal bars from the score/beats, and separates the vocals with Demucs (for lip-sync).",
  "· 已选 {0}（{1}）": "· picked {0} ({1})", "候选 {0}": "Candidate {0}", "重新生成候选": "Regenerate candidates",
  // design
  "镜头": "Shot", "小节": "Bars", "时长": "Length", "景别": "Framing", "口型": "Lip-sync", "首帧": "First frame", "运动": "Motion",
  "重新设计全部分镜？": "Redesign all shots?", "重新设计分镜": "Redesign shots",
  // frames / videos
  "{0}/{1} 已生成 · 质检未通过 {2} · 点击镜头可改提示词并单独重做":
    "{0}/{1} generated · {2} failed QC · click a shot to edit its prompt and redo it",
  "空镜": "no people", "按小节时间轴把所有片段拼接成片。": "Cuts all clips together on the bar timeline.",
  "下载 {0}": "Download {0}", "重新拼接": "Re-assemble",
  // shot modal
  "{0} · 小节 {1} · {2}s": "{0} · bars {1} · {2}s", "质检：{0}": "QC: {0}", "运动提示词": "Motion prompt",
  "首帧提示词": "First-frame prompt", "用此提示词重做": "Redo with this prompt", "关闭": "Close",
  "重做首帧后，记得在“视频”步骤里重做这个镜头的视频。": "After redoing a first frame, also redo this shot's video in the Videos step.",
  // workflows
  "编辑映射": "Edit mapping", "ComfyUI 工作流": "ComfyUI workflows",
  "每个生成环节用哪个工作流。改动只影响之后的生成（已生成的首帧/视频不变）；不同工作流画风不同，换了之后建议重做相关镜头。":
    "Which workflow each generation step uses. Changes only affect future generations (existing frames/clips stay); workflows differ in look, so consider redoing affected shots after switching.",
  "导入新工作流": "Import a workflow",
  "在 ComfyUI 里打开工作流 → 菜单 Export (API) 导出 JSON。导入后系统会自动猜测提示词/种子/图片/音频等节点，请核对。":
    "Open the workflow in ComfyUI → menu Export (API) to save the JSON. After import the prompt/seed/image/audio nodes are guessed automatically — please check them.",
  "名称，例如 Wan 2.2 i2v 480p": "Name, e.g. Wan 2.2 i2v 480p", "解析": "Parse",
  "先选择一个 JSON 文件": "Choose a JSON file first", "不是有效的 JSON：": "Not valid JSON: ",
  "（不映射）": "(not mapped)",
  "{0} 个节点 · 带 * 的必须映射": "{0} nodes · fields marked * are required",
  "；时长（秒）与帧数映射其一即可": "; map either length (seconds) or frame count",
  "帧率": "FPS", "帧数规则 N×": "Frame rule N×",
  "+1（只在映射“帧数”时使用；LTX 填 8，Wan 填 4）": "+1 (only used when Frames is mapped; LTX: 8, Wan: 4)",
  "保存后用于当前项目": "Use for this project after saving", "保存映射": "Save mapping", "保存到工作流库": "Save to library",
  "从库中移除": "Remove from library",
  "从工作流库移除？（文件保留，已在用的项目仍保留自己的副本）":
    "Remove from the workflow library? (The file is kept; projects already using it keep their own copy.)",
  "请填写名称和描述": "Please enter a name and a brief", "停止当前正在运行的任务？": "Stop the task that is running now?",
  // role / param labels sent by the server (scripts/wf_bindings.py)
  "文生图（成员参考图 / 舞台底图）": "Text to image (member refs / stage plate)", "首帧 · 1 张参考图": "First frame · 1 reference",
  "首帧 · 2 张参考图": "First frame · 2 references", "首帧 · 3 张参考图": "First frame · 3 references",
  "视频 · 图生视频": "Video · image to video", "视频 · 对口型（图 + 人声）": "Video · lip-sync (image + vocals)",
  "参考图 1": "Reference 1", "参考图 2": "Reference 2", "参考图 3": "Reference 3", "首帧图": "First frame image",
  "人声片段": "Vocal clip", "提示词": "Prompt", "种子": "Seed", "宽": "Width", "高": "Height",
  "输出文件名前缀": "Output filename prefix", "时长（秒）": "Length (seconds)", "帧数（与时长二选一）": "Frames (instead of length)",  // local LLM (Unsloth Studio)
  "本地模型（Unsloth Studio）": "Local model (Unsloth Studio)", "本地模型": "Local model",
  "可以把部分或全部任务交给本机 Unsloth Studio 里的模型。它和 ComfyUI / YuE2 共用显卡：需要时自动加载，生成画面或音乐前自动卸载。":
    "Hand some or all tasks to a model running in Unsloth Studio on this PC. It shares the GPU with ComfyUI / YuE2: loaded when needed, unloaded before images or music are generated.",
  "地址": "Address", "模型": "Model", "量化": "Quant", "选项": "Options", "读取模型列表": "List models",
  "例如 unsloth/Qwen3-VL-8B-Instruct-GGUF": "e.g. unsloth/Qwen3-VL-8B-Instruct-GGUF", "可选，例如 UD-Q4_K_XL": "Optional, e.g. UD-Q4_K_XL",
  "思考模式（更慢）": "Thinking (slower)", "用显卡前自动卸载": "Unload before the GPU is needed",
  "每个任务用哪个模型": "Model per task", "测试": "Test", "立即卸载": "Unload now",
  "写歌": "Song writing", "封面提示词": "Cover prompt", "MV 概念": "MV concept", "分镜设计": "Shot design",
  "挑参考图（看图）": "Reference pick (vision)", "质检（看图）": "QC (vision)",
  "已保存（留空不修改）": "Saved (leave empty to keep)", "在 Unsloth Studio 的 Settings → API 里创建": "Create one in Unsloth Studio: Settings → API",
  "Unsloth Studio 没有运行（{0}）": "Unsloth Studio is not running ({0})",
  "Unsloth Studio 已运行，还没有填 API Key": "Unsloth Studio is running; no API key entered yet",
  "Unsloth Studio 已运行 · {0} 已加载": "Unsloth Studio running · {0} loaded",
  "Unsloth Studio 已运行 · 当前加载：{0}": "Unsloth Studio running · loaded now: {0}", "无": "none",
  "处理中…": "Working…", "失败：{0}": "Failed: {0}", "已卸载": "Unloaded",
  "Studio 里有 {0} 个模型（点模型输入框选择）": "{0} models in Studio (pick one in the model box)",
  "测试通过（{0} 秒，含加载）：{1}": "Test passed ({0} s incl. loading): {1}",
  // cast library
  "角色库": "Cast", "角色": "Cast",
  "在 MV 的「成员参考图」步骤把选好的成员存进来，以后新建 MV 时选上，就是同一张脸、同一身造型。":
    "Save members from an MV's reference-portrait step; pick them when you create a new MV and they keep the same face and look.",
  "角色库是空的：在 MV 的「成员参考图」步骤点「存入角色库」。": "The cast is empty: use \"Save to cast\" on an MV's reference-portrait step.",
  "不选 = 由 Claude 设计新成员；最多选 2 个": "None = Claude designs new members; pick up to 2",
  "存入角色库": "Save to cast", "更新角色库": "Update in cast", "已在角色库": "In the cast", "来自角色库": "From the cast",
  "来自：{0}": "From: {0}", "用于 {0} 个 MV": "Used in {0} MVs",
  "已保存到角色库": "Saved to the cast",
  "从角色库删除「{0}」？\n文件夹会移到 trash/cast/。已经用它做的 MV 不受影响。": "Remove \"{0}\" from the cast?\nIts folder moves to trash/cast/. MVs already made with it are not affected.",
  "最多选 2 个角色": "Pick at most 2 members", "这两个角色同名": "These two members have the same name",
  "接上一镜": "Starts from", "结束状态": "Ends with",
  // storyboard editor (board.js)
  "读取分镜…": "Loading storyboard…", "完整提示词表": "Full prompt table", "还没有分镜：先运行分镜设计这一步。": "No storyboard yet: run the shot design step first.",
  "单人": "Solo", "双人": "Duo", "舞台全景": "Stage wide", "背影": "Back view",
  "保存分镜": "Save storyboard", "放弃修改": "Discard edits", "生成预览（静帧 + 音乐）": "Preview (stills + music)",
  "{0} 个镜头 · {1}s · 点击镜头编辑；改动的镜头保存后只重做这些": "{0} shots · {1}s · click a shot to edit; after saving only changed shots are redone",
  "预览（静帧 animatic）": "Preview (stills animatic)", "新镜头": "New shot", "小节 {0}–{1}": "Bars {0}–{1}",
  "还没有首帧": "No first frame yet", "类型": "Type", "对口型": "Lip-sync", "无": "None", "景别": "Shot size", "机位": "Angle",
  "视线": "Gaze", "灯光": "Light", "首帧动作": "First-frame action", "运动": "Motion",
  "锁定（对话修改不会动它）": "Locked (chat edits leave it alone)", "从小节 {0} 拆开": "Split at bar {0}", "拆分": "Split",
  "与下一个合并": "Merge with next", "并入上一个": "Merge into previous",
  "用一句话修改分镜": "Edit the storyboard in one sentence",
  "例：副歌更激烈，多用车；第二段主歌让两人背靠背；结尾慢一点": "E.g. make the chorus more intense and use the car more; back to back in verse 2; slower ending",
  "让模型修改": "Ask the model", "模型会改出一个新版本供对比；锁定的镜头不会变。": "The model writes a new version to compare; locked shots stay as they are.",
  "修改建议": "Proposed edit", "{0} 个镜头有变化": "{0} shots changed", "这个版本不完整，不能应用：{0}": "This version is incomplete and can't be applied: {0}",
  "应用这些修改": "Apply these edits", "放弃": "Discard", "没保存：{0}": "Not saved: {0}", "已保存，正在更新镜头表…": "Saved, updating the shot list…",
  "有未保存的修改：预览用的是已保存的分镜。继续？": "You have unsaved edits: the preview uses the saved storyboard. Continue?",
  "正在生成预览（约 10–30 秒）…": "Making the preview (about 10–30 s)…",
  "有未保存的修改：模型会在已保存的分镜上修改。继续？": "You have unsaved edits: the model edits the saved storyboard. Continue?",
  "模型正在修改分镜（本地模型约 2 分钟）…": "The model is revising the storyboard (about 2 min on the local model)…",
  "已应用，正在更新镜头表…": "Applied, updating the shot list…",
  // creation options
  "画风": "Look", "画幅": "Aspect", "范围": "Range",
  "先只做一段副歌试效果，满意后再做整首。": "Try one chorus first; make the whole song once you like it.",
  "舞台表演": "Stage performance", "成员在一个舞台上演唱，靠灯光推进": "Members perform on one stage; lighting carries the progression",
  "故事": "Story", "2–4 个场景，跟着歌曲讲一个简单的故事": "2–4 locations telling a simple story along the song",
  "视觉化": "Visualizer", "没有人物，抽象画面跟随音乐": "No people: abstract imagery following the music",
  "自动": "Auto", "按歌曲和想法": "From the song and your idea",
  "横屏 16:9": "Landscape 16:9", "竖屏 9:16": "Vertical 9:16", "方形 1:1": "Square 1:1",
  "整首歌": "Whole song", "只做第一段副歌": "First chorus only", "前 45 秒": "First 45 s",
  "自定义小节": "Custom bars", "从": "from", "到": "to", "应用并重新设计分镜": "Apply and redesign",
  "当前：小节 {0}–{1}": "Now: bars {0}–{1}", "当前：整首": "Now: whole song", "场景": "Location",
  "改范围/画幅会重新设计分镜，之后的首帧和视频都要重新生成（旧文件保留）。继续？":
    "Changing the range / aspect redesigns the storyboard; frames and videos are generated again (old files are kept). Continue?",
  "场景（故事模式）": "Locations (story mode)",
  // versions, cut editing, post-production
  "版本（点选使用哪一版，其余都保留）": "Versions (click to use one; all are kept)", "剪辑": "Cut",
  "对口型镜头从头开始（保持口型同步）": "Lip-sync shots start at 0 (keeps the mouth in sync)",
  "从第": "Start at", "秒开始用": "s into the clip", "进入方式": "Transition in",
  "直接切": "Cut", "白闪": "White flash", "黑场": "Dip to black", "淡入": "Fade in", "保存剪辑": "Save cut",
  "已保存（重新拼接后生效）": "Saved (applies on the next cut)", "后期": "Post-production",
  "歌词字幕": "Lyric captions", "卡拉 OK 字幕": "Karaoke captions", "经典（底部）": "Classic (bottom)",
  "大字（下三分之一）": "Bold (lower third)", "简洁（左下，无高亮）": "Minimal (bottom left, no highlight)",
  "鼓点闪光": "Kick flash", "鼓点推镜": "Kick zoom punch", "效果范围": "Effects in", "整首": "Whole song",
  "只在副歌": "Choruses only", "只在高能量段落": "High-energy sections only", "调色": "Colour grade",
  "原色": "None", "暖调": "Warm", "冷调": "Cool", "青橙电影": "Teal & orange", "复古": "Vintage", "黑白": "Black & white", "高对比": "High contrast",
  "导出": "Export", "放大到 1080p（普通插值，不是 AI 超分）": "Upscale to 1080p (plain interpolation, not AI)",
  "鼓点效果用 Demucs 分出的鼓轨找底鼓；字幕按小节显示歌词，逐字高亮是均匀分配的。":
    "Kick effects find the kick drum in the Demucs drum stem; captions show each lyric line over its bars, with the word highlight spread evenly.",
  "保存后期设置并重新拼接": "Save post settings and re-cut", "场景底图": "Location plates",
  "歌词视频": "Lyric video", "舞台画面 + 卡拉 OK 歌词字幕": "Stage visuals + karaoke lyric captions",
};

// Stage names come from the server in English; Chinese names live here.
const STAGE_ZH = { concept: "概念与歌词", music: "歌曲", analysis: "节拍 / 段落分析", refs: "成员参考图",
  design: "分镜设计", frames: "首帧 + 质检", videos: "视频片段 + 质检", assemble: "成片" };

function t(zh, ...a) {
  const s = LANG === "en" && EN[zh] !== undefined ? EN[zh] : zh;
  return s.replace(/\{(\d+)\}/g, (_, i) => a[+i] ?? "");
}

function stageLabel(key, serverLabel) { return LANG === "zh" ? (STAGE_ZH[key] || serverLabel) : serverLabel; }

// Free-form Chinese text produced by the server (workflow names, validation errors) -> English, best effort.
const DYN = [
  [/（内置）/g, " (built-in)"], [/（本地 int8）/g, " (local int8)"], [/（8 步加速）/g, " (8-step turbo)"],
  [/编辑·(\d) 图/g, "edit · $1 image(s)"], [/图生视频/g, "image to video"], [/对口型/g, "lip-sync"],
  [/^(\w+): 节点 (\S+) 不存在$/, "$1: node $2 does not exist"], [/^(\w+): 节点 (\S+) 没有输入 (\S+)$/, "$1: node $2 has no input $3"],
  [/^缺少必填映射：(.+)（(\w+)）$/, (m, l, k) => `Missing required mapping: ${t(l)} (${k})`],
  [/^视频工作流需要映射 时长（秒）或 帧数 之一$/, "A video workflow needs Length (seconds) or Frames mapped"],
  [/^固定值：节点 (\S+) 不存在$/, "Fixed value: node $1 does not exist"],
  [/^不是 API 格式的工作流.*$/, "Not an API-format workflow. Export it from ComfyUI with Export (API) (a normal save contains nodes/links and cannot be submitted)."],
];
function tr(text) {
  if (LANG === "zh" || text == null) return text;
  if (EN[text] !== undefined) return EN[text];
  return DYN.reduce((s, [re, rep]) => s.replace(re, rep), String(text));
}

// Static markup: data-i18n (text), data-i18n-ph (placeholder), data-i18n-title (tooltip). The Chinese source text
// is remembered on first run so switching back and forth works.
function applyStatic() {
  document.documentElement.lang = LANG === "en" ? "en" : "zh";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.dataset.zh ??= el.textContent; el.textContent = t(el.dataset.zh);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.dataset.zhPh ??= el.getAttribute("placeholder"); el.setAttribute("placeholder", t(el.dataset.zhPh));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.dataset.zhTitle ??= el.getAttribute("title"); el.setAttribute("title", t(el.dataset.zhTitle));
  });
  document.querySelectorAll("#langbar button").forEach((b) => b.classList.toggle("on", b.dataset.lang === LANG));
}

function setLang(l) {
  LANG = l;
  try { localStorage.setItem("mv_lang", l); } catch (e) { /* storage blocked */ }
  applyStatic();
  if (typeof onLangChange === "function") onLangChange();
}
