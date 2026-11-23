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
  "写一段描述，Claude 据此写歌": "Write a brief for Claude to write the song from", "新歌": "New song",
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
  "输出文件名前缀": "Output filename prefix", "时长（秒）": "Length (seconds)", "帧数（与时长二选一）": "Frames (instead of length)",
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
