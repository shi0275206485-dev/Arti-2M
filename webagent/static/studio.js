// Music studio: song library (songs/<id>/) independent of MV projects. A finished song is picked when an MV
// project is created (or swapped in at the project's song step). Uses $, api, esc, t from app.js / i18n.js.
let tab = "create", curSong = null, songData = null, songKey = "", libSongs = [], genres = { categories: [] };

const SONG_STATUS = { drafting: "Claude 写歌词中", draft: "草稿", generating: "生成中", needs: "等待你处理", ready: "可用", error: "出错" };
const ENGINE_LABEL = { yue2: "本地 YuE2", suno: "Suno", upload: "导入的文件" };
const SF = (p) => `/songfiles/${curSong}/${p}`;
const fmtDur = (s) => s ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}` : "";

// song cards (library page + "recent songs" on the create page); the play button uses the bottom player
function songCard(s) {
  const busy = ["drafting", "generating"].includes(s.status);
  return `<div class="scard" data-id="${esc(s.id)}">
    <div class="cover" style="${coverStyle(s.id)}">
      ${s.has_audio ? `<button class="play" data-play="${esc(s.id)}" aria-label="Play">▶</button>` : ""}
      ${s.duration ? `<span class="dur">${fmtDur(s.duration)}</span>` : ""}
      ${busy ? `<span class="busy">${t(SONG_STATUS[s.status])}…</span>` : ""}
    </div>
    <div class="st">${esc(s.title || t("（未命名）"))}</div>
    <div class="sub">${t(ENGINE_LABEL[s.engine] || s.engine)}${s.instrumental ? " · " + t("纯音乐") : ""}${s.genre ? " · " + esc(gName(s.genre)) : ""} · ${t(SONG_STATUS[s.status] || s.status)}</div></div>`;
}
function bindSongCards(box) {
  box.querySelectorAll(".scard").forEach((c) => c.onclick = (e) => {
    const p = e.target.closest("[data-play]");
    if (p) { e.stopPropagation(); playSong(libSongs.find((s) => s.id === p.dataset.play)); return; }
    selectSong(c.dataset.id);
  });
}

async function refreshSongs() {
  libSongs = await api("/api/songs");
  const empty = `<p class="muted">${t("音乐库是空的：在「音乐创作」里写第一首歌，或导入音频文件。")}</p>`;
  $("#slist").innerHTML = libSongs.map(songCard).join("") || empty;
  $("#hsongs").innerHTML = libSongs.slice(0, 10).map(songCard).join("") || `<p class="muted">${t("还没有歌。")}</p>`;
  bindSongCards($("#slist")); bindSongCards($("#hsongs"));
  fillSongSelect();
}

// the new-MV form's song picker
function fillSongSelect(preselect) {
  const sel = $("#nsong"); if (!sel) return;
  sel.onchange = () => { sel.dataset.picked = "1"; };   // after a manual pick (even "none"), keep it across refreshes
  const keep = preselect ?? (sel.dataset.picked ? sel.value : sel.value || libSongs.find((s) => s.has_audio)?.id);
  sel.innerHTML = libSongs.filter((s) => s.has_audio).map((s) =>
    `<option value="${esc(s.id)}">${esc(s.title || s.id)} · ${t(ENGINE_LABEL[s.engine] || s.engine)}${s.instrumental ? " · " + t("纯音乐") : ""}${s.duration ? " · " + fmtDur(s.duration) : ""}</option>`).join("")
    + `<option value="">${t("不选：在项目里用 YuE2 生成（旧方式）")}</option>`;
  if ([...sel.options].some((o) => o.value === keep)) sel.value = keep;
}

// ---------- music categories pulled from Spotify (data/genres.json)
const gName = (g) => (LANG === "zh" ? g.name_zh || g.name : g.name) || g.id;
const GENRE_GROUPS = [["genre", "音乐类型"], ["region", "地区 / 语言"], ["mood", "情绪 / 场景"], ["spotify", "Spotify 分类"]];
function genreOptions(selected) {
  const opt = (g) => `<option value="${esc(g.id)}" ${g.id === selected ? "selected" : ""}>${esc(gName(g))}${g.instrumental ? " · " + t("纯音乐") : ""}</option>`;
  return `<option value="">${t("不选分类")}</option>` + GENRE_GROUPS.map(([key, label]) => {
    const cats = genres.categories.filter((g) => (g.group || "genre") === key);
    if (key === "spotify") cats.sort((a, b) => gName(a).localeCompare(gName(b), LANG === "zh" ? "zh" : "en"));
    return cats.length ? `<optgroup label="${esc(t(label))}">${cats.map(opt).join("")}</optgroup>` : "";
  }).join("");
}
function genreHint(id) {
  const g = genres.categories.find((c) => c.id === id);
  return g ? (g.style ? `${t("参考曲风")}: ${esc(g.style)}` : t("（Claude 还没写这个分类的曲风提示）")) : "";
}
let genreTimer = null;
async function loadGenres() {
  genres = await api("/api/genres");
  const n = genres.spotify_count, job = genres.job || {};
  const keep = $("#sgenre").value;
  $("#sgenre").innerHTML = genreOptions(keep);
  $("#sgenrehint").innerHTML = genreHint($("#sgenre").value);
  renderGenreCards();
  $("#spcred").classList.toggle("hidden", !!genres.has_credentials);
  $("#sprefresh").disabled = !genres.has_credentials || job.running;
  $("#spstat").innerHTML = job.running ? (job.phase === "claude" ? t("Claude 正在为每个分类写曲风提示…") : t("正在从 Spotify 拉取…"))
    : job.error ? `<span class="issues">${esc(job.error.includes("(403)") ? t("Spotify 拒绝了分类接口（403）。凭证没有问题，但 Spotify 从 2026 年 2 月起不再向开发模式（Development Mode）应用提供分类接口，只有获批 Extended Quota 的应用能用。请使用内置分类。") : job.error)}</span>`
    : n ? t("{0} 个音乐分类，拉取于 {1}", n, new Date(genres.fetched * 1000).toLocaleString())
    : genres.has_credentials ? t("凭证已保存，点下面按钮拉取") : t("可选：内置分类不需要 Spotify。要加 Spotify 自己的分类，需要一个 Spotify 开发者应用的凭证。");
  clearTimeout(genreTimer);
  if (job.running) genreTimer = setTimeout(() => loadGenres().catch(() => {}), 2000);
  else if (songData && $("#s_genre")) { songKey = ""; refreshSong().catch(() => {}); }
}
$("#sgenre").onchange = () => {
  const g = genres.categories.find((c) => c.id === $("#sgenre").value);
  $("#sgenrehint").innerHTML = genreHint($("#sgenre").value);
  if (g) $("#sinst").checked = !!g.instrumental;
  document.querySelectorAll("#gcards .gcard").forEach((c) => c.classList.toggle("on", c.dataset.id === $("#sgenre").value));
};

// category gallery on the create page: one group at a time, a click picks the category in the prompt box
let genreGroup = "genre";
function renderGenreCards() {
  const groups = GENRE_GROUPS.filter(([k]) => genres.categories.some((g) => (g.group || "genre") === k));
  if (!groups.some(([k]) => k === genreGroup)) genreGroup = groups[0]?.[0] || "genre";
  $("#gtabs").innerHTML = groups.map(([k, label]) => `<button class="${k === genreGroup ? "on" : ""}" data-g="${k}">${t(label)}</button>`).join("");
  $("#gtabs").querySelectorAll("button").forEach((b) => b.onclick = () => { genreGroup = b.dataset.g; renderGenreCards(); });
  const sel = $("#sgenre").value;
  $("#gcards").innerHTML = genres.categories.filter((g) => (g.group || "genre") === genreGroup).map((g) =>
    `<button class="gcard ${g.id === sel ? "on" : ""}" data-id="${esc(g.id)}" style="${coverStyle(g.id)}" title="${esc(g.style || "")}">
      <b>${esc(gName(g))}</b>${g.instrumental ? `<span>${t("纯音乐")}</span>` : ""}</button>`).join("");
  $("#gcards").querySelectorAll(".gcard").forEach((c) => c.onclick = () => {
    const s = $("#sgenre");
    s.value = s.value === c.dataset.id ? "" : c.dataset.id;   // click again to unselect
    s.dispatchEvent(new Event("change"));
    $("#main").scrollTo({ top: 0, behavior: "smooth" }); $("#sbrief").focus({ preventScroll: true });
  });
}
$("#spsave").onclick = async () => {
  try { await api("/api/genres/credentials", { client_id: $("#spcid").value.trim(), client_secret: $("#spsec").value.trim() }); }
  catch (e) { return alert(e.message); }
  $("#spsec").value = ""; await loadGenres();
  if (!genres.categories.length) $("#sprefresh").click();
};
$("#sprefresh").onclick = async () => {
  try { await api("/api/genres/refresh", {}); } catch (e) { return alert(e.message); }
  loadGenres();
};

function selectSong(id) { location.hash = "#song/" + encodeURIComponent(id); }

async function refreshSong() {
  if (!curSong || tab !== "music") return;
  songData = await api(`/api/songs/${curSong}`);
  const log = $("#slog");
  const key = JSON.stringify([LANG, songData.state, songData.has_audio, songData.busy, songData.used_by]);
  if (savesPending) return;   // a redraw now would drop clicks that are still being saved
  if (key !== songKey && !document.activeElement?.closest?.("#songview .edit")) { songKey = key; renderSong(); }
  else if (log) { const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20; log.textContent = songData.log.join("\n"); if (atBottom) log.scrollTop = log.scrollHeight; }
}

const SONG_NEEDS = {
  not_signed_in: "先登录 Suno（下方按钮），再点「生成」。",
  requires_credit: "下载这首歌要消耗 1 个 Suno 下载额度。可以批准下载，或者在 suno.com 自己下载后用左侧「导入音频文件」导入。",
};

// ---------- click-to-choose song settings (lists come from /api/song_options = webagent/studio.py OPTIONS)
let songOpts = null, saveChain = Promise.resolve(), savesPending = 0;
const OPT_ZH = {
  "female vocal": "女声", "male vocal": "男声", "male and female duet vocals": "男女对唱", "female group vocals": "女团合唱",
  "male group vocals": "男团合唱", "child vocal": "童声", "choir vocals": "合唱团", "male rap": "男声说唱", "female rap": "女声说唱",
  "Mandarin Chinese": "普通话", "Cantonese": "粤语", "English": "英语", "Japanese": "日语", "Korean": "韩语", "Spanish": "西班牙语",
  "Mandarin and English": "中英混合",
  happy: "欢快", sad: "伤感", romantic: "浪漫", energetic: "激昂", relaxed: "放松", dark: "暗黑", dreamy: "梦幻", nostalgic: "怀旧",
  epic: "史诗", melancholic: "忧郁", uplifting: "振奋", aggressive: "狂野", mysterious: "神秘", playful: "俏皮", warm: "温暖", emotional: "深情",
  piano: "钢琴", "acoustic guitar": "木吉他", "electric guitar": "电吉他", bass: "贝斯", drums: "鼓", strings: "弦乐",
  synthesizer: "合成器", "808 bass": "808 低音", "electric piano": "电钢琴", saxophone: "萨克斯", trumpet: "小号", violin: "小提琴",
  cello: "大提琴", flute: "长笛", organ: "管风琴", harp: "竖琴", "music box": "八音盒", guzheng: "古筝", erhu: "二胡", dizi: "笛子", pipa: "琵琶",
  short: "短（约 2 分钟）", standard: "标准（约 3 分钟）", long: "长（约 4 分钟）",
};
const optLabel = (v) => LANG === "zh" ? (OPT_ZH[v] || v) : ({ short: "Short (~2 min)", standard: "Standard (~3 min)", long: "Long (~4 min)" }[v] || v.replace(/^./, (c) => c.toUpperCase()));
const YUE_TEXT = {
  cot: [["full", "完整规划（推荐）", "先写旋律+和弦乐谱再生成；MV 分析的小节/段落最准"],
        ["melody", "只规划旋律", "和弦与伴奏交给模型自由发挥"],
        ["off", "不规划", "直接生成，最自由；没有乐谱，MV 只能按音频分析（纯音乐不可用）"]],
  creativity: [["stable", "稳定", "旋律更规整、重复更多"], ["normal", "标准", "YuE2 默认"], ["bold", "大胆", "旋律更多变化，也更容易跑偏"]],
  guidance: [["default", "标准", "YuE2 默认"], ["strong", "加强", "更贴近曲风描述（较慢，更占显存）"], ["stronger", "很强", "实验性；可能牺牲音质"]],
};

function settingsPanel(st) {
  if (!songOpts) return `<p class="muted">${t("正在读取选项…")}</p>`;
  const s = st.settings || {}, O = songOpts.options, inst = st.instrumental;
  const sel = (k, auto) => `<select data-set="${k}"><option value="">${t(auto)}</option>${O[k].map((v) =>
    `<option value="${esc(v)}" ${s[k] === v ? "selected" : ""}>${esc(optLabel(v))}</option>`).join("")}</select>`;
  const chips = (k, max) => `<div class="chips" data-chips="${k}" data-max="${max}">${O[k].map((v) =>
    `<button type="button" class="chip ${(s[k] || []).includes(v) ? "on" : ""}" data-v="${esc(v)}">${esc(optLabel(v))}</button>`).join("")}</div>`;
  const bpm = s.bpm || 0;
  let h = `<div class="label">${t("音乐设定")} <span class="muted small">${t("点选即可；Claude 写歌时也会按这些来")}</span>
      <button type="button" id="st_reset" class="link">${t("清空设定")}</button></div>
    <div class="kv setgrid">
      <div>${t("曲风类型")}</div><input data-set="genre_text" value="${esc(s.genre_text || "")}" placeholder="${esc(t("例如 Mandopop ballad、melodic techno（英文更好）"))}">
      ${inst ? "" : `<div>${t("人声")}</div><div>${sel("vocal", "（自动）")}</div><div>${t("语言")}</div><div>${sel("language", "（自动）")}</div>`}
      <div>${t("情绪")} <span class="muted small">≤3</span></div>${chips("moods", 3)}
      <div>${t("乐器")} <span class="muted small">≤6</span></div>${chips("instruments", 6)}
      <div>${t("速度")}</div><div class="row"><input type="range" id="st_bpm" min="50" max="180" step="1" value="${bpm || 100}" ${bpm ? "" : "disabled"}>
        <b id="st_bpmv" style="min-width:64px">${bpm ? bpm + " BPM" : ""}</b>
        <label class="row"><input type="checkbox" id="st_bpmauto" ${bpm ? "" : "checked"}> ${t("自动")}</label></div>
      <div>${t("长度")}</div><div class="row">${O.length.map((v) =>
        `<label class="row"><input type="radio" name="st_len" value="${v}" ${(s.length || "standard") === v ? "checked" : ""}> ${esc(optLabel(v))}</label>`).join("")}
        <span class="muted small">${t("（决定 Claude 写多长的歌词）")}</span></div>
    </div>`;
  if (st.engine === "yue2") {
    const y = { ...songOpts.yue_defaults, ...(st.yue || {}) };
    const radios = (k) => YUE_TEXT[k].map(([v, label, tip]) => {
      const off = k === "cot" && v === "off" && inst;
      return `<label class="opt ${off ? "muted" : ""}"><input type="radio" name="y_${k}" value="${v}" ${y[k] === v && !off ? "checked" : ""} ${off ? "disabled" : ""}>
        <b>${t(label)}</b> <span class="muted small">${t(tip)}</span></label>`;
    }).join("");
    h += `<details class="yue" ${st.yue && JSON.stringify(st.yue) !== JSON.stringify(songOpts.yue_defaults) ? "open" : ""}>
      <summary>${t("YuE2 生成选项")} <span class="muted small">${t("（默认就好；想要不同效果再调）")}</span></summary>
      <div class="kv">
        <div>${t("作曲方式")}</div><div>${radios("cot")}</div>
        <div>${t("创意度")}</div><div>${radios("creativity")}</div>
        <div>${t("风格贴合度")}</div><div>${radios("guidance")}</div>
        <div>${t("长歌")}</div><label class="opt"><input type="checkbox" id="y_long" ${y.long_score ? "checked" : ""}> <b>${t("加长乐谱上限")}</b>
          <span class="muted small">${t("长歌或密集的编曲不会在结尾被截断（更慢，更占显存）")}</span></label>
        <div>${t("种子")}</div><div class="row"><input id="y_seed" type="number" min="0" value="${st.seed ?? 42}" style="width:140px">
          <button type="button" id="y_seed_rand">${t("随机")}</button><span class="muted small">${t("同样的设定 + 同一个种子 = 同一首歌；「换种子重新生成」会自动换")}</span></div>
      </div></details>`;
  }
  return h;
}

function readSettings() {
  if (!songOpts || !document.querySelector("[data-set=genre_text]")) return undefined;
  const v = (k) => document.querySelector(`[data-set=${k}]`)?.value || "";
  const on = (k) => [...document.querySelectorAll(`[data-chips=${k}] .chip.on`)].map((b) => b.dataset.v);
  return { genre_text: v("genre_text").trim(), vocal: v("vocal"), language: v("language"), moods: on("moods"),
    instruments: on("instruments"), bpm: $("#st_bpmauto").checked ? null : Number($("#st_bpm").value),
    length: document.querySelector("[name=st_len]:checked")?.value || "standard" };
}

function readYue() {
  const r = (k) => document.querySelector(`[name=y_${k}]:checked`)?.value;
  return { cot: r("cot") || "full", creativity: r("creativity") || "normal", guidance: r("guidance") || "default",
    long_score: !!$("#y_long")?.checked };
}

// the generators read plain tags: sub-genre, instruments, vocal + language, moods, tempo
function composeStyle(s, inst) {
  if (!s) return "";
  const parts = [];
  if (inst) parts.push("Instrumental");
  if (s.genre_text) parts.push(s.genre_text);
  if (s.instruments.length) parts.push(s.instruments.join(", "));
  if (!inst && s.vocal) parts.push(s.language ? `${s.vocal}, ${s.language}` : s.vocal);
  else if (!inst && s.language) parts.push(`${s.language} vocals`);
  if (s.moods.length) parts.push(s.moods.join(", "));
  if (s.bpm) parts.push(`${s.bpm} BPM`);
  if (inst) parts.push("no vocals");
  return parts.length > (inst ? 2 : 0) ? parts.join(", ") : "";
}

function bindSettings(V, changed, save) {
  V.querySelectorAll("[data-set]").forEach((el) => el.onchange = changed);
  V.querySelectorAll("[data-chips]").forEach((box) => box.querySelectorAll(".chip").forEach((b) => b.onclick = () => {
    if (!b.classList.contains("on") && box.querySelectorAll(".chip.on").length >= Number(box.dataset.max)) {
      box.classList.add("full"); setTimeout(() => box.classList.remove("full"), 600); return;
    }
    b.classList.toggle("on"); changed();
  }));
  const bpm = $("#st_bpm"), auto = $("#st_bpmauto");
  if (bpm) {
    bpm.oninput = () => { $("#st_bpmv").textContent = bpm.value + " BPM"; };
    bpm.onchange = changed;
    auto.onchange = () => { bpm.disabled = auto.checked; $("#st_bpmv").textContent = auto.checked ? "" : bpm.value + " BPM"; changed(); };
  }
  V.querySelectorAll("[name=st_len]").forEach((r) => r.onchange = save);   // length only steers Claude's lyrics
  V.querySelectorAll("[name^=y_], #y_long, #y_seed").forEach((r) => r.onchange = save);
  if ($("#st_reset")) $("#st_reset").onclick = async () => {
    if (!confirm(t("清空音乐设定？（曲风提示词保留，之后 Claude 写歌会重新选）"))) return;
    V.querySelectorAll("[data-set]").forEach((el) => { el.value = ""; });
    V.querySelectorAll(".chip.on").forEach((b) => b.classList.remove("on"));
    auto.checked = true; bpm.disabled = true; $("#st_bpmv").textContent = "";
    await save();
  };
}

function renderSong() {
  const d = songData, st = d.state, V = $("#songview");
  const working = d.busy || ["drafting", "generating"].includes(st.status);
  const cur0 = st.current || {};
  let h = `<header><h1>${esc(st.title || t("（未命名）"))}</h1><div class="hdr-right"><span class="pill">${t(SONG_STATUS[st.status] || st.status)}</span></div></header>`;
  h = `<div class="songhead"><div class="cover big" style="${coverStyle(st.id)}"></div><div>${h}</div></div>`;
  if (d.has_audio) {
    h += `<audio controls src="${SF("audio/song.wav")}?t=${st.runs.length}" style="width:100%"></audio>
      <p class="muted">${t(ENGINE_LABEL[cur0.source] || cur0.source || "")} · ${fmtDur(st.duration)}` +
      (cur0.source === "yue2" ? ` · ${t("种子 {0}", cur0.seed)}${cur0.truncated ? ` · <span class='issues'>${t("上一版被截断")}</span>` : ""}` : "") +
      (cur0.source && cur0.source !== "yue2" ? ` · ${t("无乐谱，MV 分析只按音频切小节/段落")}` : ` · ${t("带乐谱（小节/段落更准）")}`) + `</p>`;
  }
  if (st.status === "drafting") h += `<p class="muted">${t("Claude 正在根据描述写歌名、曲风和歌词…")}</p>`;
  if (st.status === "generating") h += `<p class="muted">${st.engine === "suno" ? t("Suno 生成中（一次 2 首，约 1–3 分钟）…") : st.engine === "upload" ? t("导入中…") : t("YuE2 生成中（约 2–4 分钟，会先关闭 ComfyUI）…")}</p>`;
  if (st.status === "needs") h += `<div class="issues">${esc(st.needs ? t(SONG_NEEDS[st.needs.reason] || "Suno 无法下载这首歌（{0}）：请在 suno.com 自己下载后导入。", st.needs.reason) : st.msg)}</div>`;
  if (st.status === "error") h += `<div class="issues">${esc(st.msg)}</div>`;

  if (st.engine !== "upload") {
    h += `<div class="edit"><div class="kv">
      <div>${t("标题")}</div><input id="s_title" value="${esc(st.title)}">
      <div>${t("引擎")}</div><select id="s_engine"><option value="yue2">${t("本地 YuE2")}</option><option value="suno">Suno</option></select>
      <div>${t("分类")}</div><div><select id="s_genre">${genreOptions(st.genre?.id || "")}</select>${st.genre && !genres.categories.some((c) => c.id === st.genre.id) ? ` <span class="muted">${esc(gName(st.genre))}</span>` : ""}</div>
      <div>${t("描述")}</div><textarea id="s_brief" rows="2" placeholder="${esc(t("给 Claude 的描述（重写歌词时用）"))}">${esc(st.brief)}</textarea>
      <div></div><label class="row"><input type="checkbox" id="s_inst" ${st.instrumental ? "checked" : ""}> ${t("纯音乐（无人声，不需要歌词）")}</label></div>
      ${settingsPanel(st)}
      <div class="label">${t("曲风提示词")} <span class="muted small">${t("（由上面的设定自动生成，也可以直接改）")}</span></div>
      <textarea id="s_style" rows="2">${esc(st.style)}</textarea>
      <div id="s_stylenote" class="muted small ${st.style_custom && st.style ? "" : "hidden"}">${t("曲风是手动写的；再改上面的设定会重新生成并覆盖它。")}</div>
      <div id="s_lyrbox" class="${st.instrumental ? "hidden" : ""}"><div class="label">${t("歌词")}</div><textarea id="s_lyrics" rows="16" placeholder="[Verse]&#10;...&#10;[Chorus]&#10;...">${esc(st.lyrics)}</textarea></div></div>`;
    if (st.instrumental && st.engine === "yue2") h += `<p class="muted">${t("YuE2 纯音乐：先写谱，再把旋律移到乐器声部，然后生成（比有歌词的多一步规划）。不保证完全没有人声，请试听。")}</p>`;
    if (st.engine === "suno") h += `<div id="sunobox" class="muted">${t("正在读取 Suno 账户…")}</div>`;
    const clips = st.suno?.clips || [];
    if (clips.length) {
      h += `<div class="label">${t("Suno 生成的歌（一次 2 首，选一首用）")}</div><div class="clips">` + clips.map((c) => {
        const used = cur0.source === "suno" && cur0.clip_id === c.id && d.has_audio;
        const needCredit = st.needs?.reason === "requires_credit" && st.needs.id === c.id;
        const btn = used ? `<span class="badge ok">${t("正在使用")}</span>` : c.status !== "complete" ? ""
          : needCredit ? `<button class="primary" data-sdl="${esc(c.id)}" data-credit="1">${t("批准：消耗 1 个下载额度")}</button>`
          : `<button data-sdl="${esc(c.id)}" ${working ? "disabled" : ""}>${t("下载并使用这首")}</button>`;
        return `<div class="clip ${used ? "chosen" : ""}">${c.cover ? `<img src="${esc(c.cover)}" alt="">` : ""}<div>
          <b>${esc(c.title || c.id.slice(0, 8))}</b> <span class="muted">${c.duration ? fmtDur(c.duration) : ""} · ${esc(c.status)}</span><br>
          ${c.song_url ? `<a href="${esc(c.song_url)}" target="_blank" rel="noopener">${t("在 suno.com 试听 / 手动下载")}</a>` : ""} ${btn}</div></div>`;
      }).join("") + `</div>`;
    }
    const gen = d.has_audio || st.runs.length ? (st.engine === "suno" ? t("重新生成（消耗 Suno 积分）") : t("换种子重新生成")) : (st.engine === "suno" ? t("用 Suno 生成（消耗 Suno 积分）") : t("用 YuE2 生成"));
    h += `<div class="actions"><button id="s_save">${t("保存修改")}</button>
      <button id="s_draft" ${working || !(st.brief || st.genre) ? "disabled" : ""}>${t("让 Claude 重写歌词")}</button>
      <button id="s_gen" class="${d.has_audio ? "" : "primary"}" ${working ? "disabled" : ""}>${gen}</button>`;
  } else {
    h += `<div class="edit"><div class="kv"><div>${t("标题")}</div><input id="s_title" value="${esc(st.title)}"></div>
      <div class="label">${t("歌词（可选，MV 用来挂歌词）")}</div><textarea id="s_lyrics" rows="10">${esc(st.lyrics)}</textarea></div>
      <div class="actions"><button id="s_save">${t("保存修改")}</button>`;
  }
  if (d.has_audio) h += `<button id="s_tomv" class="primary">${t("用这首做 MV")}</button>`;
  h += `</div>`;
  if (d.used_by.length) h += `<p class="muted">${t("用在 MV 项目：")}${d.used_by.map((p) => `<a href="#" data-openp="${esc(p)}">${esc(p)}</a>`).join("，")}</p>`;
  h += `<details open><summary>${t("日志")}</summary><pre id="slog"></pre></details>`;
  V.innerHTML = h;
  const log = $("#slog"); log.textContent = d.log.join("\n"); log.scrollTop = log.scrollHeight;
  if ($("#s_engine")) $("#s_engine").value = st.engine;

  let styleCustom = !!st.style_custom;
  const fields = () => {
    const o = { title: $("#s_title").value, lyrics: $("#s_lyrics").value };
    if ($("#s_style")) Object.assign(o, { style: $("#s_style").value, brief: $("#s_brief").value, engine: $("#s_engine").value,
      instrumental: $("#s_inst").checked, settings: readSettings(), style_custom: styleCustom });
    if ($("#y_seed")) Object.assign(o, { yue: readYue(), seed: Number($("#y_seed").value) || 0 });
    const gsel = $("#s_genre")?.value;   // "" clears; an id no longer in the list keeps the stored category
    if (gsel !== undefined && gsel !== (st.genre?.id || "") && (!gsel || genres.categories.some((c) => c.id === gsel))) o.genre = gsel;
    return o;
  };
  // one save at a time, each reading the fields when it runs: quick clicks can't land out of order
  const sid = curSong;
  const save = () => {
    savesPending++;
    return (saveChain = saveChain.catch(() => {}).then(() => api(`/api/songs/${sid}`, fields()))
      .finally(() => { savesPending--; }));
  };
  $("#s_save").onclick = async () => {
    try { await save(); } catch (e) { return alert(t("保存失败：{0}", e.message || e)); }
    $("#s_save").textContent = t("已保存"); songKey = ""; refreshSongs();
  };
  if ($("#s_engine")) $("#s_engine").onchange = async () => { await save(); songKey = ""; refreshSong(); };
  if ($("#s_genre")) $("#s_genre").onchange = async () => { await save(); songKey = ""; refreshSong(); };
  if ($("#s_inst")) $("#s_inst").onchange = async () => {
    if (!styleCustom) recompose();
    await save(); songKey = ""; refreshSong();
  };
  // settings -> style prompt (only overwrites a hand-written style after asking once)
  let askedOverwrite = false;
  const recompose = () => {
    const s = composeStyle(readSettings(), $("#s_inst").checked);
    if (!s) return true;
    if (styleCustom && $("#s_style").value.trim() && !askedOverwrite) {
      askedOverwrite = true;
      if (!confirm(t("曲风是手动写的。按设定重新生成会覆盖它，继续？"))) return false;
    }
    $("#s_style").value = s; styleCustom = false; $("#s_stylenote").classList.add("hidden");
    return true;
  };
  const settingsChanged = async () => { if (recompose()) await save(); };
  if ($("#s_style")) $("#s_style").oninput = () => { styleCustom = true; };
  bindSettings(V, settingsChanged, save);
  if ($("#y_seed_rand")) $("#y_seed_rand").onclick = async () => { $("#y_seed").value = Math.floor(Math.random() * 2147483647); await save(); };
  if ($("#s_draft")) $("#s_draft").onclick = async () => {
    if (!confirm(t("让 Claude 按描述重写歌名、曲风和歌词？当前内容会被替换。"))) return;
    try { await save(); await api(`/api/songs/${curSong}/run`, { task: "draft" }); }
    catch (e) { return alert(t("没有开始：{0}", e.message || e)); }
    songKey = ""; refreshSong();
  };
  if ($("#s_gen")) $("#s_gen").onclick = async () => {
    const f = fields();
    if (!f.style.trim() || (!f.instrumental && !f.lyrics.trim())) return alert(t(f.instrumental ? "先写曲风（或让 Claude 写）" : "先写曲风和歌词（或让 Claude 写）"));
    if (f.engine === "suno" && !confirm(t("用 Suno 生成 2 首？会消耗 Suno 积分。"))) return;
    const seedEdited = $("#y_seed") && Number($("#y_seed").value) !== st.seed;   // a seed the user typed is used as-is
    const b = $("#s_gen"), label = b.textContent; b.disabled = true; b.textContent = t("提交中…");
    try {
      await save();
      await api(`/api/songs/${curSong}/run`, { task: "generate", new_seed: f.engine === "yue2" && !seedEdited && (d.has_audio || st.runs.length > 0 || st.status === "error") });
    } catch (e) {   // never fail silently: say why nothing started
      b.disabled = false; b.textContent = label;
      return alert(t("没有开始生成：{0}", e.message || e));
    }
    songKey = ""; refreshSong();
  };
  V.querySelectorAll("[data-sdl]").forEach((b) => b.onclick = async () => {
    const credit = !!b.dataset.credit;
    if (credit && !confirm(t("确定消耗 1 个 Suno 下载额度下载这首歌？"))) return;
    b.disabled = true;
    await api(`/api/songs/${curSong}/run`, { task: "suno_download", clip_id: b.dataset.sdl, confirm: credit });
    songKey = ""; refreshSong();
  });
  if ($("#s_tomv")) $("#s_tomv").onclick = () => {
    location.hash = "#mv"; fillSongSelect(curSong);
    if (!$("#ntitle").value) $("#ntitle").value = st.title;
    setTimeout(() => $("#nbrief").focus(), 50);
  };
  V.querySelectorAll("[data-openp]").forEach((a) => a.onclick = (e) => { e.preventDefault(); select(a.dataset.openp); });
  if (st.engine === "suno") loadSuno(false);
}

// ---------- sidebar actions
$("#screate").onclick = async () => {
  const brief = $("#sbrief").value.trim(), genre = $("#sgenre").value;
  if (!brief && !genre) return alert(t("选一个分类或写一段描述，Claude 据此写歌"));
  const r = await api("/api/songs", { brief, genre, draft: true, engine: $("#sengine").value, instrumental: $("#sinst").checked });
  $("#sbrief").value = ""; await refreshSongs(); selectSong(r.id);
};
$("#sblank").onclick = async () => {
  const r = await api("/api/songs", { title: t("新歌"), genre: $("#sgenre").value, draft: false, engine: $("#sengine").value, instrumental: $("#sinst").checked });
  await refreshSongs(); selectSong(r.id);
};
$("#sfile").onchange = () => { if ($("#sfile").files[0]) $("#simport").click(); };
$("#simport").onclick = async () => {
  const f = $("#sfile").files[0];
  if (!f) return alert(t("先选择一个音频文件"));
  const b = $("#simport"); b.disabled = true; b.textContent = t("上传中…");
  const r = await fetch(`/api/song_import?name=${encodeURIComponent(f.name)}`, { method: "POST", body: f });
  b.disabled = false; b.textContent = t("导入到曲库");
  if (!r.ok) return alert(await r.text());
  $("#sfile").value = ""; await refreshSongs(); selectSong((await r.json()).id);
};
refreshSongs().catch(() => {});
loadGenres().catch(() => {});
api("/api/song_options").then((o) => { songOpts = o; songKey = ""; refreshSong().catch(() => {}); }).catch(() => {});
setInterval(() => { if (tab === "music") refreshSong().catch(() => {}); }, 2500);
setInterval(() => refreshSongs().catch(() => {}), 8000);
