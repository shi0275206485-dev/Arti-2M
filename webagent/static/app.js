// MV Agent frontend: polls the project state and renders one panel per pipeline stage.
// UI text goes through t() / tr() / stageLabel() from i18n.js (Chinese source strings, English table).
const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
};
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const STATUS = { pending: "未开始", running: "进行中", waiting: "等待确认", done: "完成", error: "出错" };

let cur = null, data = null, view = null, lastPanelKey = "";

let claudeOk = false;
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    claudeOk = s.claude.ok;
    const c = $("#claude");
    c.textContent = s.claude.ok ? t("Claude 已连接") : t("Claude 未配置");
    c.className = "pill " + (s.claude.ok ? "ok" : "bad");
    $("#keywarn").classList.toggle("hidden", s.claude.ok);
    $("#claudestat").textContent = s.claude.ok ? t("已连接。可以在下面换一个 Key。") : t("还没有 Key：Claude 写歌、写分镜和质检都需要它。");
    $("#worker").textContent = s.current ? t("运行中：{0}", s.current[1]) + (s.queue.length ? t("（队列 {0}）", s.queue.length) : "") : t("空闲");
  } catch (e) { /* server restarting */ }
}

async function refreshList() {
  const list = await api("/api/projects");
  const cards = list.map((p) => {
    const st = Object.values(p.stages);
    const done = st.filter((x) => x === "done").length;
    const flag = st.includes("error") ? "出错" : st.includes("waiting") ? "等待确认" : st.includes("running") ? "进行中" : "";
    const cls = st.includes("error") ? "bad" : st.includes("waiting") ? "warn" : st.includes("running") ? "run" : done === st.length ? "ok" : "";
    return `<div class="pcard" data-id="${esc(p.id)}">
      <div class="cover wide" style="${coverStyle(p.id)}">${flag ? `<span class="flag ${cls}">${t(flag)}</span>` : ""}
        ${st.includes("running") ? "" : `<button class="del" data-del="${esc(p.id)}" data-title="${esc(p.title)}" title="${esc(t("删除"))}" aria-label="Delete">🗑</button>`}</div>
      <div class="st">${esc(p.title)}</div>
      <div class="bar"><i style="width:${Math.round(100 * done / st.length)}%"></i></div>
      <div class="sub">${t("{0}/{1} 步", done, st.length)} · ${p.mode === "auto" ? t("全自动") : t("确认模式")}</div></div>`;
  });
  $("#plist").innerHTML = cards.join("") || `<p class="muted">${t("还没有 MV 项目：去「MV 制作」新建一个。")}</p>`;
  $("#hprojs").innerHTML = cards.slice(0, 4).join("") || `<p class="muted">${t("还没有 MV 项目。")}</p>`;
  document.querySelectorAll("#plist .pcard, #hprojs .pcard").forEach((c) => c.onclick = (e) => {
    const del = e.target.closest("[data-del]");
    if (del) { e.stopPropagation(); deleteItem("mv", del.dataset.del, del.dataset.title); return; }
    select(c.dataset.id);
  });
}

function select(id) {   // the router (nav.js) shows the project page
  const h = "#mv/" + encodeURIComponent(id);
  if (location.hash === h) { lastPanelKey = ""; refresh().catch(() => {}); } else location.hash = h;
}

async function refresh() {
  if (!cur || tab !== "mv") return;
  data = await api(`/api/projects/${cur}`);
  $("#empty").classList.add("hidden"); $("#proj").classList.remove("hidden");
  const st = data.state;
  $("#ptitle").textContent = st.title;
  $("#pmode").value = st.mode;
  // default view: the stage that is waiting / running / errored, else the last done one
  const order = data.stages;
  const active = order.find((s) => ["waiting", "running", "error"].includes(st.stages[s].status))
    || [...order].reverse().find((s) => st.stages[s].status === "done") || order[0];
  const v = view || active;
  $("#stepper").innerHTML = order.map((s, i) => {
    const x = st.stages[s];
    return `<li class="${x.status} ${s === v ? "view" : ""}" data-s="${s}"><b>${i + 1}. ${esc(stageLabel(s, data.labels[s]))}</b>${t(STATUS[x.status])}</li>`;
  }).join("");
  $("#stepper").querySelectorAll("li").forEach((li) => li.onclick = () => { view = li.dataset.s; lastPanelKey = ""; refresh(); });
  const log = $("#log"); const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
  log.textContent = data.log.join("\n"); if (atBottom) log.scrollTop = log.scrollHeight;
  // only re-render the panel when something relevant changed (keeps edits in text areas)
  const key = JSON.stringify([LANG, v, st.stages, st.music, st.qc, st.refs, st.final, data.shots.map((s) => [s.frame_file, s.clip_file])]);
  if (key !== lastPanelKey && !document.activeElement?.closest?.("#panel")) { lastPanelKey = key; renderPanel(v); }
}

function actionsBar(stage, extra = "", noApprove = false) {
  const s = data.state.stages[stage];
  let h = `<div class="actions">`;
  if (s.status === "waiting" && !noApprove) h += `<button class="primary" data-approve="${stage}">${t("确认，进入下一步")}</button>`;
  if (s.status === "error" || s.status === "pending") h += `<button data-run="${stage}">${s.status === "error" ? t("重试此步") : t("运行此步")}</button>`;
  h += extra + `</div>`;
  if (s.msg && s.status === "error") h = `<div class="issues">${esc(s.msg)}</div>` + h;
  return h;
}

function bindCommon() {
  $("#panel").querySelectorAll("[data-approve]").forEach((b) => b.onclick = async () => { await api(`/api/projects/${cur}/approve/${b.dataset.approve}`, {}); view = null; refresh(); });
  $("#panel").querySelectorAll("[data-run]").forEach((b) => b.onclick = async () => { await api(`/api/projects/${cur}/run/${b.dataset.run}`, {}); refresh(); });
  $("#panel").querySelectorAll("[data-act]").forEach((b) => b.onclick = async () => {
    if (b.dataset.confirm && !window.confirm(b.dataset.confirm)) return;
    await api(`/api/projects/${cur}/action`, { task: b.dataset.act }); refresh();
  });
}

const F = (p) => `/files/${cur}/${p}`;

function renderPanel(stage) {
  const st = data.state, P = $("#panel");
  const c = st.concept;
  let h = `<h2>${esc(stageLabel(stage, data.labels[stage]))}</h2>`;
  if (stage === "concept") {
    if (!c) h += `<p class="muted">${t("Claude 正在根据你的描述写概念、歌词和成员形象…")}</p>` + actionsBar(stage);
    else {
      h += `<div class="kv"><div>${t("标题")}</div><input id="c_title" value="${esc(c.title)}">
        <div>${t("曲风")}</div><textarea id="c_style" rows="2">${esc(c.style)}</textarea>
        <div>${t("舞台底图")}</div><textarea id="c_plate" rows="3">${esc(c.stage_plate)}</textarea>
        <div>${t("画面风格")}</div><textarea id="c_fstyle" rows="2">${esc(c.frame_style)}</textarea></div>
        <div class="label">${t("成员")}</div>` + c.members.map((m, i) => `<div class="kv"><div>${esc(m.name)}</div>
        <textarea data-m="${i}" rows="3">${esc(m.look)}</textarea></div>`).join("") +
        `<div class="label">${t("灯光状态")}</div><div class="muted">${c.lights.map((l) => `<b>${esc(l.key)}</b>: ${esc(l.description)}`).join("<br>")}</div>
        <div class="label">${t("歌词")}</div><textarea id="c_lyrics" rows="18">${esc(c.lyrics)}</textarea>` +
        actionsBar(stage, `<button id="savec">${t("保存修改")}</button><button data-act="regen_concept" data-confirm="${esc(t("重新让 Claude 写概念？当前修改会丢失。"))}">${t("重新生成概念")}</button>`);
    }
  } else if (stage === "music") {
    h += musicPanel(st);
  } else if (stage === "analysis") {
    h += `<p class="muted">${t("按乐谱/节拍切小节、段落和人声小节，并用 Demucs 分离人声（供对口型）。")}</p>` + actionsBar(stage);
  } else if (stage === "refs") {
    h += Object.entries(data.refs).map(([name, r]) => `<div class="label">${esc(name)} ${r.chosen ? esc(t("· 已选 {0}（{1}）", r.chosen.cand, r.chosen.reason)) : ""}</div>
      <div class="refs">${r.cands.map((f, k) => `<div class="card ${r.chosen && r.chosen.cand === k ? "chosen" : ""}" data-ref="${esc(name)}" data-k="${k}">
      <img src="${F("shots/refs/" + f)}?v=${Date.now() % 100000}"><div class="meta">${t("候选 {0}", k)}</div></div>`).join("")}</div>`).join("");
    h += actionsBar(stage, `<button data-act="regen_refs">${t("重新生成候选")}</button>`);
  } else if (stage === "design") {
    if (data.plate) h += `<img src="${F("shots/plates/stage.png")}" style="max-width:520px;border-radius:8px"><br>`;
    h += `<div class="tablewrap"><table><tr>${["镜头", "小节", "时长", "景别", "成员", "口型", "歌词", "首帧", "运动"].map((x) => `<th>${t(x)}</th>`).join("")}</tr>` +
      data.shots.map((s) => `<tr><td>${s.id}</td><td>${s.bars.join("–")}</td><td>${s.seconds.toFixed(1)}</td><td>${esc(s.shot)}</td>
        <td>${esc(s.members.join(", "))}</td><td>${esc(s.lipsync || "")}</td><td>${esc(s.lyrics.join(" / "))}</td>
        <td>${esc(s.frame.prompt)}</td><td>${esc(s.video.prompt)}</td></tr>`).join("") + `</table></div>`;
    h += actionsBar(stage, `<button data-act="regen_design" data-confirm="${esc(t("重新设计全部分镜？"))}">${t("重新设计分镜")}</button>`);
  } else if (stage === "frames" || stage === "videos") {
    const vid = stage === "videos";
    const n = data.shots.length, have = data.shots.filter((s) => vid ? s.clip_file : s.frame_file).length;
    const fails = data.shots.filter((s) => (vid ? s.qc_clip : s.qc_frame)?.ok === false).length;
    h += `<p class="muted">${t("{0}/{1} 已生成 · 质检未通过 {2} · 点击镜头可改提示词并单独重做", have, n, fails)}</p><div class="grid">` +
      data.shots.map((s) => {
        const q = vid ? s.qc_clip : s.qc_frame;
        const badge = q ? `<span class="badge ${q.ok ? "ok" : "bad"}">${q.ok ? "QC ✓" : "QC ✗"}</span>` : "";
        const media = vid ? (s.clip_file ? `<video src="${F(s.clip_file)}" muted loop preload="metadata"></video>` : `<img>`)
          : (s.frame_file ? `<img src="${F(s.frame_file)}" loading="lazy">` : `<img>`);
        return `<div class="card" data-shot="${s.id}">${media}${badge}<div class="meta">${s.id} · ${esc(s.shot)} · ${esc(s.members.join("+") || t("空镜"))}${s.lipsync ? " · 🎤" + esc(s.lipsync) : ""}</div></div>`;
      }).join("") + `</div>`;
    h += actionsBar(stage);
  } else if (stage === "assemble") {
    h += st.final ? `<video controls src="${F(st.final)}" style="width:100%;border-radius:8px"></video><p><a href="${F(st.final)}" download>${esc(t("下载 {0}", st.final))}</a></p>`
      : `<p class="muted">${t("按小节时间轴把所有片段拼接成片。")}</p>`;
    h += actionsBar(stage, st.final ? `<button data-act="assemble">${t("重新拼接")}</button>` : "");
  }
  P.innerHTML = h;
  bindCommon();
  if (stage === "music") bindMusic(st);
  const save = $("#savec");
  if (save) save.onclick = async () => {
    const nc = structuredClone(c);
    nc.title = $("#c_title").value; nc.style = $("#c_style").value; nc.stage_plate = $("#c_plate").value;
    nc.frame_style = $("#c_fstyle").value; nc.lyrics = $("#c_lyrics").value;
    P.querySelectorAll("[data-m]").forEach((x) => nc.members[+x.dataset.m].look = x.value);
    await api(`/api/projects/${cur}/concept`, { concept: nc }); save.textContent = t("已保存"); lastPanelKey = "";
  };
  P.querySelectorAll("[data-ref]").forEach((el) => el.onclick = async () => {
    await api(`/api/projects/${cur}/pick_ref`, { name: el.dataset.ref, k: +el.dataset.k }); lastPanelKey = ""; refresh();
  });
  P.querySelectorAll("video").forEach((v) => { v.onmouseenter = () => v.play(); v.onmouseleave = () => v.pause(); });
  P.querySelectorAll("[data-shot]").forEach((el) => el.onclick = () => openShot(el.dataset.shot, stage === "videos"));
}

// ---------- music stage: local YuE2 / Suno / uploaded file
const SRC_LABEL = { yue2: "本地 YuE2", suno: "Suno", upload: "上传音频文件" };
const NEEDS_MSG = {
  not_signed_in: "先登录 Suno，再点「运行此步」生成。",
  requires_credit: "下载这首歌要消耗 1 个 Suno 下载额度。可以批准下载，或者在 suno.com 自己下载后上传文件。",
  upload: "上传一个音频文件（mp3 / wav / flac …）。",
};
let sunoInfo = null;

function musicPanel(st) {
  const m = st.music, src = m.source || "yue2", status = st.stages.music.status, busy = status === "running";
  const cur = m.current || {};
  if (src === "library") return libraryMusicPanel(st);
  let h = `<div class="srcbar"><span class="muted">${t("歌曲来源")}</span>` + Object.keys(SRC_LABEL).map((k) =>
    `<button data-src="${k}" class="${k === src ? "on" : ""}" ${busy ? "disabled" : ""}>${t(SRC_LABEL[k])}</button>`).join("") + `</div>`;
  if (data.has_audio) {
    const cs = cur.source || "yue2";
    h += `<audio controls src="${F("audio/song.wav")}?t=${m.runs.length}" style="width:100%"></audio><p class="muted">` +
      t("当前歌曲来自：{0}", t(SRC_LABEL[cs] || cs)) +
      (cs === "yue2" ? ` · ${t("种子 {0} · 已生成 {1} 版", cur.seed ?? m.seed, m.runs.filter((r) => (r.source || "yue2") === "yue2").length)}` : "") +
      (cur.truncated ? ` · <span class='issues'>${t("上一版被截断")}</span>` : "") +
      (cs !== "yue2" ? ` · ${t("无乐谱，分析阶段只按音频切小节/段落")}` : "") + `</p>`;
  } else if (busy) {
    h += `<p class="muted">${src === "suno" ? t("Suno 生成中（一次 2 首，约 1–3 分钟）…") : t("YuE2 生成中（约 2–4 分钟，会先关闭 ComfyUI）…")}</p>`;
  }
  if (m.needs) h += `<div class="issues">${esc(t(NEEDS_MSG[m.needs.reason] || "Suno 无法下载这首歌（{0}）：请在 suno.com 自己下载后上传文件。", m.needs.reason))}</div>`;
  let extra = "";
  if (src === "yue2") {
    if (data.has_audio) extra = `<button data-act="regen_music">${t("换种子重新生成")}</button>`;
  } else if (src === "suno") {
    h += `<div id="sunobox" class="muted">${t("正在读取 Suno 账户…")}</div>`;
    const clips = m.suno?.clips || [];
    if (clips.length) {
      h += `<div class="label">${t("Suno 生成的歌（一次 2 首，选一首用）")}</div><div class="clips">` + clips.map((c) => {
        const used = cur.source === "suno" && cur.clip_id === c.id && data.has_audio;
        const needCredit = m.needs?.reason === "requires_credit" && m.needs.id === c.id;
        const btn = used ? `<span class="badge ok">${t("正在使用")}</span>`
          : c.status !== "complete" ? ""
          : needCredit ? `<button class="primary" data-sunodl="${esc(c.id)}" data-credit="1">${t("批准：消耗 1 个下载额度")}</button>`
          : `<button data-sunodl="${esc(c.id)}" ${busy ? "disabled" : ""}>${t("下载并使用这首")}</button>`;
        return `<div class="clip ${used ? "chosen" : ""}">${c.cover ? `<img src="${esc(c.cover)}" alt="">` : ""}<div>
          <b>${esc(c.title || c.id.slice(0, 8))}</b> <span class="muted">${c.duration ? Math.round(c.duration) + "s" : ""} · ${esc(c.status)}</span><br>
          ${c.song_url ? `<a href="${esc(c.song_url)}" target="_blank" rel="noopener">${t("在 suno.com 试听 / 手动下载")}</a>` : ""} ${btn}
        </div></div>`;
      }).join("") + `</div>`;
    }
    if (status !== "pending") extra = `<button data-act="regen_music" data-confirm="${esc(t("用 Suno 再生成 2 首？会消耗 Suno 积分。"))}">${t("重新生成（消耗 Suno 积分）")}</button>`;
  }
  if (src !== "yue2") {
    h += `<div class="label">${src === "suno" ? t("或者：上传你在 suno.com 下载的文件") : t("上传音频文件")}</div>
      <div class="upload"><input type="file" id="songfile" accept="audio/*,.mp3,.wav,.flac,.m4a,.ogg"><button id="songup">${t("上传并使用")}</button></div>`;
  }
  return h + actionsBar("music", extra, !!m.needs || !data.has_audio);
}

// MV project whose song comes from the music studio
function libraryMusicPanel(st) {
  const m = st.music, song = libSongs.find((s) => s.id === m.song_id);
  let h = `<p>${t("歌曲来自音乐工作室：")}<a href="#" data-opensong="${esc(m.song_id)}"><b>${esc(song?.title || m.song_id)}</b></a></p>`;
  if (data.has_audio) h += `<audio controls src="${F("audio/song.wav")}?t=${m.runs.length}" style="width:100%"></audio>`;
  else if (st.stages.music.status !== "waiting") h += `<p class="muted">${t("运行这一步会把曲库里的歌复制到项目。")}</p>`;
  if (st.stages.music.status === "waiting" && !data.has_audio) h += `<div class="issues">${t("这首歌还没有音频：先在音乐工作室生成完。")}</div>`;
  const others = libSongs.filter((s) => s.has_audio && s.id !== m.song_id);
  if (others.length) h += `<div class="label">${t("换一首")}</div><div class="upload"><select id="swapsong">${others.map((s) =>
    `<option value="${esc(s.id)}">${esc(s.title || s.id)}${s.duration ? " · " + fmtDur(s.duration) : ""}</option>`).join("")}</select>
    <button id="swapgo">${t("换成这首")}</button></div><p class="muted">${t("换歌后，分析及之后的步骤会重新开始（已生成的文件保留）；概念的画面设计不变，歌名/歌词换成新歌的。")}</p>`;
  return h + actionsBar("music", "", !data.has_audio);
}

async function loadSuno(force) {
  if (!$("#sunobox")) return;
  try { sunoInfo = await api(`/api/suno${force ? "?refresh=1" : ""}`); } catch (e) { sunoInfo = { signed_in: false, error: e.message }; }
  const box = $("#sunobox");
  if (!box) return;
  const s = sunoInfo;
  box.innerHTML = s.signed_in
    ? `${t("已登录 Suno")} · ${esc(s.plan || "")} · ${t("积分 {0}", s.credits ?? "?")} · ${t("下载额度 {0}", s.download_credits ?? "?")}${s.models ? " · " + esc(s.models.join(", ")) : ""}
       ${s.error ? `<span class="issues">${esc(s.error)}</span>` : ""} <button id="sunoout">${t("退出")}</button>`
    : `${t("未登录 Suno")} <button id="sunoin" class="primary">${t("登录 Suno")}</button>${s.error ? ` <span class="issues">${esc(s.error)}</span>` : ""}`;
  const i = $("#sunoin"), o = $("#sunoout");
  if (i) i.onclick = async () => {
    const w = window.open("about:blank", "_blank");   // open synchronously so the popup isn't blocked
    try { const r = await api("/api/suno/login"); w.location = r.url; } catch (e) { w.close(); return alert(e.message); }
    box.insertAdjacentHTML("beforeend", ` <span>${t("在新标签页完成登录后点")} <button id="sunore">${t("刷新")}</button></span>`);
    $("#sunore").onclick = () => loadSuno(true);
  };
  if (o) o.onclick = async () => { await api("/api/suno/logout", {}); loadSuno(true); };
}

function bindMusic(st) {
  $("#panel").querySelectorAll("[data-opensong]").forEach((a) => a.onclick = (e) => { e.preventDefault(); selectSong(a.dataset.opensong); });
  const sg = $("#swapgo");
  if (sg) sg.onclick = async () => {
    if (!confirm(t("换成这首歌？分析及之后的步骤会重新开始。"))) return;
    await api(`/api/projects/${cur}/action`, { task: "use_song", song_id: $("#swapsong").value }); lastPanelKey = ""; refresh();
  };
  $("#panel").querySelectorAll("[data-src]").forEach((b) => b.onclick = async () => {
    await api(`/api/projects/${cur}/music_source`, { source: b.dataset.src }); lastPanelKey = ""; refresh();
  });
  $("#panel").querySelectorAll("[data-sunodl]").forEach((b) => b.onclick = async () => {
    const credit = !!b.dataset.credit;
    if (credit && !window.confirm(t("确定消耗 1 个 Suno 下载额度下载这首歌？"))) return;
    b.disabled = true;
    await api(`/api/projects/${cur}/action`, { task: "suno_download", clip_id: b.dataset.sunodl, confirm: credit });
    refresh();
  });
  const up = $("#songup");
  if (up) up.onclick = async () => {
    const f = $("#songfile").files[0];
    if (!f) return alert(t("先选择一个音频文件"));
    up.disabled = true; up.textContent = t("上传中…");
    const r = await fetch(`/api/projects/${cur}/upload_audio?name=${encodeURIComponent(f.name)}`, { method: "POST", body: f });
    if (!r.ok) { alert(await r.text()); up.disabled = false; up.textContent = t("上传并使用"); return; }
    lastPanelKey = ""; refresh();
  };
  if ((st.music.source || "yue2") === "suno") loadSuno(false);
}

let modalKind = null;   // "shot" | "workflows": re-rendered on language switch
let modalShot = null;

function closeModal() { $("#modal").classList.add("hidden"); modalKind = null; }

function openShot(sid, vid, keepText) {
  modalKind = "shot"; modalShot = [sid, vid];
  const s = data.shots.find((x) => x.id === sid);
  const q = vid ? s.qc_clip : s.qc_frame;
  const media = vid ? (s.clip_file ? `<video controls autoplay loop src="${F(s.clip_file)}"></video>` : "")
    : (s.frame_file ? `<img src="${F(s.frame_file)}">` : "");
  $("#mbox").innerHTML = `<h2>${esc(t("{0} · 小节 {1} · {2}s", sid, s.bars.join("–"), s.seconds.toFixed(2)))}</h2>${media}
    ${q && !q.ok ? `<div class="issues">${esc(t("质检：{0}", q.issues.join(LANG === "en" ? "; " : "；")))}</div>` : ""}
    <div class="label">${vid ? t("运动提示词") : t("首帧提示词")}</div>
    <textarea id="mprompt" rows="6">${esc(keepText ?? (vid ? s.video.prompt : s.frame.prompt))}</textarea>
    <div class="actions"><button class="primary" id="mregen">${t("用此提示词重做")}</button><button id="mclose">${t("关闭")}</button></div>
    <p class="muted">${t("重做首帧后，记得在“视频”步骤里重做这个镜头的视频。")}</p>`;
  $("#modal").classList.remove("hidden");
  $("#mclose").onclick = closeModal;
  $("#mregen").onclick = async () => {
    const txt = $("#mprompt").value;
    await api(`/api/projects/${cur}/action`, vid ? { task: "regen_clip", sid, motion: txt } : { task: "regen_frame", sid, prompt: txt });
    closeModal(); refresh();
  };
}

// ---------- ComfyUI workflows: choose per role for this project, import API workflows with node mapping
let wfLib = null;

async function openWorkflows() {
  modalKind = "workflows";
  wfLib = await api("/api/workflows");
  const sel = await api(`/api/projects/${cur}/workflows`);
  const rows = Object.entries(wfLib.roles).map(([role, r]) => {
    const opts = wfLib.library.filter((e) => e.role === role)
      .map((e) => `<option value="${esc(e.id)}" ${sel[role] === e.id ? "selected" : ""}>${esc(tr(e.name))}</option>`).join("");
    const isUser = !sel[role].startsWith("builtin:");
    return `<tr><td>${esc(tr(r.label))}</td><td><select data-wfrole="${role}">${opts}</select></td>
      <td>${isUser ? `<button data-wfedit="${esc(sel[role])}">${t("编辑映射")}</button>` : ""}</td></tr>`;
  }).join("");
  $("#mbox").innerHTML = `<h2>${t("ComfyUI 工作流")}</h2>
    <p class="muted">${t("每个生成环节用哪个工作流。改动只影响之后的生成（已生成的首帧/视频不变）；不同工作流画风不同，换了之后建议重做相关镜头。")}</p>
    <table>${rows}</table>
    <div class="label">${t("导入新工作流")}</div>
    <p class="muted">${t("在 ComfyUI 里打开工作流 → 菜单 Export (API) 导出 JSON。导入后系统会自动猜测提示词/种子/图片/音频等节点，请核对。")}</p>
    <div class="row"><input id="wfname" placeholder="${esc(t("名称，例如 Wan 2.2 i2v 480p"))}" style="flex:2">
      <select id="wfrole" style="flex:1">${Object.entries(wfLib.roles).map(([k, r]) => `<option value="${k}">${esc(tr(r.label))}</option>`).join("")}</select></div>
    <div class="row"><input type="file" id="wffile" accept=".json,application/json"><button id="wfparse">${t("解析")}</button></div>
    <div id="wfmap"></div>
    <div class="actions"><button id="wfclose">${t("关闭")}</button></div>`;
  $("#modal").classList.remove("hidden");
  $("#wfclose").onclick = closeModal;
  $("#mbox").querySelectorAll("[data-wfrole]").forEach((s) => s.onchange = async () => {
    await api(`/api/projects/${cur}/workflows`, { role: s.dataset.wfrole, id: s.value }); openWorkflows();
  });
  $("#mbox").querySelectorAll("[data-wfedit]").forEach((b) => b.onclick = async () => {
    const r = await api(`/api/workflows/${encodeURIComponent(b.dataset.wfedit)}`);
    $("#wfname").value = r.entry.name; $("#wfrole").value = r.entry.role;
    renderMapping(r, r.entry.role, null, r.entry);
  });
  $("#wfparse").onclick = async () => {
    const f = $("#wffile").files[0];
    if (!f) return alert(t("先选择一个 JSON 文件"));
    let wf;
    try { wf = JSON.parse(await f.text()); } catch (e) { return alert(t("不是有效的 JSON：") + e.message); }
    const role = $("#wfrole").value;
    if (!$("#wfname").value.trim()) $("#wfname").value = f.name.replace(/\.json$/i, "");
    renderMapping(await api("/api/workflows/inspect", { role, workflow: wf }), role, wf, null);
  };
}

function renderMapping(info, role, wf, existing) {
  const box = $("#wfmap");
  if (!info.ok) { box.innerHTML = `<div class="issues">${info.errors.map((e) => esc(tr(e))).join("<br>")}</div>`; return; }
  const bind = existing ? existing.bind : info.suggest;
  const key = (n, i) => `${n}|${i}`;
  const optsFor = (sel) => `<option value="">${t("（不映射）")}</option>` + info.inputs.map((x) => {
    const v = typeof x.value === "string" ? x.value.slice(0, 40) : JSON.stringify(x.value);
    const k = key(x.node, x.input);
    return `<option value="${esc(k)}" ${sel === k ? "selected" : ""}>#${esc(x.node)} ${esc(x.class)}${x.title ? " “" + esc(x.title) + "”" : ""} · ${esc(x.input)} = ${esc(v)}</option>`;
  }).join("");
  const params = wfLib.roles[role].params;
  const video = wfLib.roles[role].kind === "video";
  box.innerHTML = `<p class="muted">${t("{0} 个节点 · 带 * 的必须映射", info.nodes)}${video ? t("；时长（秒）与帧数映射其一即可") : ""}</p><table>` +
    params.map((p) => `<tr><td>${esc(tr(p.label))}${p.required ? " *" : ""}</td><td><select data-bind="${p.key}">${optsFor(bind[p.key] ? key(...bind[p.key]) : "")}</select></td></tr>`).join("") +
    `</table>` + (video ? `<div class="row">${t("帧率")} <input id="wffps" type="number" value="${existing?.fps ?? 24}" style="width:80px">
      ${t("帧数规则 N×")}<input id="wfmul" type="number" value="${existing?.frame_multiple ?? 1}" style="width:60px">${t("+1（只在映射“帧数”时使用；LTX 填 8，Wan 填 4）")}</div>` : "") +
    `<label class="row"><input type="checkbox" id="wfuse" checked> ${t("保存后用于当前项目")}</label>
     <div class="actions"><button class="primary" id="wfsave">${existing ? t("保存映射") : t("保存到工作流库")}</button>
     ${existing ? `<button class="danger" id="wfdel">${t("从库中移除")}</button>` : ""}</div><div id="wferr" class="issues"></div>`;
  $("#wfsave").onclick = async () => {
    const b = {};
    box.querySelectorAll("[data-bind]").forEach((s) => { if (s.value) b[s.dataset.bind] = s.value.split("|"); });
    const body = { name: $("#wfname").value, role, bind: b, fixed: existing?.fixed || {},
      fps: video ? +$("#wffps").value : 24, frame_multiple: video ? +$("#wfmul").value : 1 };
    if (wf) body.workflow = wf; if (existing) body.id = existing.id;
    const r = await api("/api/workflows/save", body);
    if (!r.ok) { $("#wferr").innerHTML = r.errors.map((e) => esc(tr(e))).join("<br>"); return; }
    if ($("#wfuse").checked) await api(`/api/projects/${cur}/workflows`, { role, id: r.id });
    openWorkflows();
  };
  const del = $("#wfdel");
  if (del) del.onclick = async () => {
    if (!confirm(t("从工作流库移除？（文件保留，已在用的项目仍保留自己的副本）"))) return;
    await api("/api/workflows/remove", { id: existing.id });
    await api(`/api/projects/${cur}/workflows`, { role, id: `builtin:${role}` }); openWorkflows();
  };
}

// called by setLang() in i18n.js
function onLangChange() {
  refreshStatus(); refreshList().catch(() => {});
  lastPanelKey = ""; if (cur && data) refresh().catch(() => {});
  songKey = ""; route(); refreshSongs().catch(() => {});
  if (typeof loadGenres === "function") loadGenres().catch(() => {});   // category dropdown names + groups + hint
  if (modalKind === "shot") openShot(modalShot[0], modalShot[1], $("#mprompt")?.value);
  else if (modalKind === "workflows" && !$("#wfmap")?.innerHTML) openWorkflows().catch(() => {});
  // an open mapping form is left as is (re-rendering would drop the user's dropdown choices)
}

document.querySelectorAll("#langbar button").forEach((b) => b.onclick = () => setLang(b.dataset.lang));
$("#wfbtn").onclick = () => openWorkflows().catch((e) => alert(e.message));
$("#modal").onclick = (e) => { if (e.target.id === "modal") closeModal(); };
$("#create").onclick = async () => {
  const title = $("#ntitle").value.trim(), brief = $("#nbrief").value.trim(), song_id = $("#nsong").value;
  if (!title || (!brief && !song_id)) return alert(t(song_id ? "请填写名称" : "请填写名称和描述"));
  const mode = document.querySelector("input[name=nmode]:checked").value;
  const r = await api("/api/projects", song_id ? { title, brief, mode, song_id } : { title, brief, mode, music_source: "yue2" });
  $("#ntitle").value = ""; $("#nbrief").value = "";
  await refreshList(); select(r.id);
};
$("#setkey").onclick = async () => { await api("/api/key", { key: $("#key").value }); $("#key").value = ""; refreshStatus(); };
$("#pmode").onchange = async () => { await api(`/api/projects/${cur}/mode`, { mode: $("#pmode").value }); refreshList(); };
$("#cancel").onclick = async () => { if (confirm(t("停止当前正在运行的任务？"))) await api("/api/cancel", {}); };

applyStatic();
refreshStatus(); refreshList();
setInterval(() => { refreshStatus(); refresh().catch(() => {}); }, 2500);
setInterval(refreshList, 8000);
$("#pdelete").onclick = () => cur && deleteItem("mv", cur, data?.state?.title);
