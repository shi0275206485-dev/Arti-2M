// Storyboard editor (design stage): timeline of shots on the song's bar grid, per-shot editing, split / merge /
// lock, chat edits by the model (kept as a proposal to compare), and a stills animatic before rendering videos.
const KINDS_B = ["solo", "duo", "stage_wide", "back_view", "empty"];
const SIZES_B = ["close-up", "medium close-up", "medium", "wide"];
const ANGLES_B = ["front", "three-quarter", "side", "low", "high"];
const GAZES_B = ["camera", "partner", "crowd", "down", "up"];
const KIND_LABEL = { solo: "单人", duo: "双人", stage_wide: "舞台全景", back_view: "背影", empty: "空镜" };
const EDIT_FIELDS = ["first_bar", "last_bar", "kind", "members", "lipsync", "size", "angle", "gaze", "light", "action", "motion", "end_state", "location", "locked"];

let board = null;   // {pid, data, rows (working copy), orig (json per row), sel, dirty, msg}

function rowJson(r) { return JSON.stringify(EDIT_FIELDS.map((k) => r[k] ?? null)); }

async function initBoard(force) {
  const box = $("#board");
  if (!box) return;
  let d;
  try { d = await api(`/api/projects/${cur}/board`); }
  catch (e) { box.innerHTML = `<p class="muted">${esc(t("还没有分镜：先运行分镜设计这一步。"))}</p>`; return; }
  if (!board || board.pid !== cur || force || !board.dirty) {
    board = { pid: cur, data: d, rows: structuredClone(d.rows), sel: board?.pid === cur ? board.sel : 0, dirty: false, msg: "" };
  } else {
    board.data = d;   // keep the unsaved edits, refresh proposal / animatic / thumbnails
  }
  board.orig = new Set(d.rows.map(rowJson));
  renderBoard();
}

function bt(i) { return board.data.bars[i]; }
function rowSecs(r) { return bt(r.last_bar).end - bt(r.first_bar).start; }

function renderBoard() {
  const box = $("#board");
  if (!box || !board) return;
  const { data, rows } = board;
  board.sel = Math.min(board.sel, rows.length - 1);
  const total = rows.reduce((a, r) => a + rowSecs(r), 0);
  // section band (only the bars this MV covers)
  const secs = [];
  data.bars.slice(rows[0].first_bar, rows[rows.length - 1].last_bar + 1).forEach((b) => { const l = secs[secs.length - 1]; if (l && l.name === b.section) l.end = b.end; else secs.push({ name: b.section, start: b.start, end: b.end }); });
  const band = secs.map((s) => `<div class="tlsec" style="flex:${(s.end - s.start).toFixed(3)}">${esc(s.name)}</div>`).join("");
  const blocks = rows.map((r, i) => {
    const thumb = r.frame_file && board.orig.has(rowJson(r)) ?`style="flex:${rowSecs(r).toFixed(3)};background-image:url('${F(r.frame_file)}')"` : `style="flex:${rowSecs(r).toFixed(3)}"`;
    const changed = !board.orig.has(rowJson(r));
    return `<div class="tlshot k_${r.kind} ${i === board.sel ? "sel" : ""} ${changed ? "chg" : ""}" data-bi="${i}" ${thumb} title="${esc(r.action)}">
      <span>${r.locked ? "🔒" : ""}${esc((r.members || []).join("+") || t("空镜"))}</span></div>`;
  }).join("");
  const nChanged = rows.filter((r) => !board.orig.has(rowJson(r))).length + (rows.length !== data.rows.length ? 1 : 0);
  let h = rangeBar() + `<div class="boardbar">
      <button class="primary" id="bsave" ${board.dirty ? "" : "disabled"}>${t("保存分镜")}${board.dirty ? ` (${nChanged})` : ""}</button>
      <button id="bundo" ${board.dirty ? "" : "disabled"}>${t("放弃修改")}</button>
      <button id="banim" ${data.busy ? "disabled" : ""}>${t("生成预览（静帧 + 音乐）")}</button>
      <span class="muted">${esc(board.msg || t("{0} 个镜头 · {1}s · 点击镜头编辑；改动的镜头保存后只重做这些", rows.length, total.toFixed(1)))}</span></div>
    <div class="tl"><div class="tlband">${band}</div><div class="tlshots">${blocks}</div></div>`;
  h += shotEditor(rows[board.sel], board.sel);
  h += chatBox();
  if (data.animatic) h += `<div class="label">${t("预览（静帧 animatic）")}</div><video controls src="${F(data.animatic)}?v=${data.animatic.length}" style="width:100%;max-width:720px;border-radius:8px"></video>`;
  box.innerHTML = h;
  bindBoard();
}

const RANGE_LABEL = { full: "整首歌", chorus: "只做第一段副歌", first45: "前 45 秒" };

// part of the song + aspect ratio: changing either means a new shot design (and new frames / videos)
function rangeBar() {
  const d = board.data, o = d.opts, n = d.bars.length - 1;
  const custom = typeof o.range === "object";
  const [a, b] = d.range || [0, n];
  const barOpt = (v) => d.bars.map((x) => `<option value="${x.i}" ${x.i === v ? "selected" : ""}>${x.i} · ${esc(x.section)} · ${x.start.toFixed(1)}s</option>`).join("");
  return `<div class="rangebar"><span class="muted">${t("范围")}</span>
    <select id="brange">${Object.entries(RANGE_LABEL).map(([k, l]) => `<option value="${k}" ${!custom && o.range === k ? "selected" : ""}>${t(l)}</option>`).join("")}
      <option value="custom" ${custom ? "selected" : ""}>${t("自定义小节")}</option></select>
    <span id="bcustom" class="${custom ? "" : "hidden"}">${t("从")} <select id="bfrom">${barOpt(a)}</select> ${t("到")} <select id="bto">${barOpt(b)}</select></span>
    <span class="muted">${t("画幅")}</span><select id="baspect">${["16:9", "9:16", "1:1"].map((x) => `<option ${o.aspect === x ? "selected" : ""}>${x}</option>`).join("")}</select>
    <button id="bropts" class="hidden">${t("应用并重新设计分镜")}</button>
    <span class="muted">${d.range ? t("当前：小节 {0}–{1}", a, b) : t("当前：整首")} · ${esc(o.vmode)}</span></div>`;
}

function opt(list, v, label = (x) => x) { return list.map((x) => `<option value="${esc(x)}" ${x === v ? "selected" : ""}>${esc(label(x))}</option>`).join(""); }

function shotEditor(r, i) {
  const d = board.data;
  const lyr = [...new Set(d.bars.slice(r.first_bar, r.last_bar + 1).map((b) => b.lyric).filter(Boolean))].join(" / ");
  const splitOpts = [];
  for (let b = r.first_bar + 1; b <= r.last_bar; b++) splitOpts.push(b);
  const mem = d.members.map((m) => `<label class="chk"><input type="checkbox" data-bm="${esc(m)}" ${r.members.includes(m) ? "checked" : ""}>${esc(m)}</label>`).join("");
  return `<div class="shoted">
    <div class="shothead"><b>${esc(r.sid || t("新镜头"))}</b> · ${t("小节 {0}–{1}", r.first_bar, r.last_bar)} · ${rowSecs(r).toFixed(1)}s · ${esc(bt(r.first_bar).section)}
      ${lyr ? `<span class="muted">· ${esc(lyr)}</span>` : ""}
      <span class="sp"></span>
      <button data-bnav="-1" ${i === 0 ? "disabled" : ""}>◀</button><button data-bnav="1" ${i === board.rows.length - 1 ? "disabled" : ""}>▶</button></div>
    <div class="shotgrid">
      ${r.frame_file ? `<img class="shotthumb" src="${F(r.frame_file)}">` : `<div class="shotthumb none">${t("还没有首帧")}</div>`}
      <div class="kv">
        <div>${t("类型")}</div><select data-bf="kind">${opt(KINDS_B, r.kind, (x) => t(KIND_LABEL[x]))}</select>
        <div>${t("成员")}</div><div>${mem}</div>
        <div>${t("对口型")}</div><select data-bf="lipsync"><option value="">${t("无")}</option>${opt(d.members, r.lipsync)}</select>
        <div>${t("景别")}</div><select data-bf="size">${opt(SIZES_B, r.size)}</select>
        <div>${t("机位")}</div><select data-bf="angle">${opt(ANGLES_B, r.angle)}</select>
        <div>${t("视线")}</div><select data-bf="gaze">${opt(GAZES_B, r.gaze)}</select>
        <div>${t("灯光")}</div><select data-bf="light">${opt(Object.keys(d.lights), r.light)}</select>
        ${Object.keys(d.locations || {}).length ? `<div>${t("场景")}</div><select data-bf="location">${opt(Object.keys(d.locations), r.location)}</select>` : ""}
      </div>
      <div class="kv wide">
        <div>${t("首帧动作")}</div><textarea data-bf="action" rows="3">${esc(r.action)}</textarea>
        <div>${t("运动")}</div><textarea data-bf="motion" rows="2">${esc(r.motion)}</textarea>
        <div>${t("结束状态")}</div><input data-bf="end_state" value="${esc(r.end_state || "")}">
        ${r.prev_state ? `<div>${t("接上一镜")}</div><div class="state">${esc(r.prev_state)}</div>` : ""}
      </div>
    </div>
    <div class="actions">
      <label class="chk"><input type="checkbox" id="block" ${r.locked ? "checked" : ""}>${t("锁定（对话修改不会动它）")}</label>
      ${splitOpts.length ? `<select id="bsplitat">${splitOpts.map((b) => `<option value="${b}">${t("从小节 {0} 拆开", b)}</option>`).join("")}</select><button id="bsplit">${t("拆分")}</button>` : ""}
      ${i < board.rows.length - 1 ? `<button id="bmergen">${t("与下一个合并")}</button>` : ""}
      ${i > 0 ? `<button id="bmergep">${t("并入上一个")}</button>` : ""}
    </div></div>`;
}

function chatBox() {
  const pr = board.data.proposal;
  let h = `<div class="label">${t("用一句话修改分镜")}</div>
    <div class="row"><textarea id="bchat" rows="2" style="flex:1" placeholder="${esc(t("例：副歌更激烈，多用车；第二段主歌让两人背靠背；结尾慢一点"))}"></textarea>
    <button id="bchatgo" ${board.data.busy ? "disabled" : ""}>${t("让模型修改")}</button></div>
    <p class="muted">${t("模型会改出一个新版本供对比；锁定的镜头不会变。")}</p>`;
  if (!pr) return h;
  const old = new Map(board.data.rows.map((r) => [r.first_bar, r]));
  h += `<div class="proposal"><div><b>${t("修改建议")}</b> · “${esc(pr.message)}” · ${t("{0} 个镜头有变化", pr.changed.length)}</div>`;
  if (pr.errors?.length) h += `<div class="issues">${esc(t("这个版本不完整，不能应用：{0}", pr.errors.slice(0, 3).join("; ")))}</div>`;
  h += pr.rows.filter((r) => pr.changed.includes(r.first_bar)).map((r) => {
    const o = old.get(r.first_bar);
    return `<div class="pchg"><span class="muted">${t("小节 {0}–{1}", r.first_bar, r.last_bar)} · ${esc(t(KIND_LABEL[r.kind]))} ${esc(r.members.join("+"))} · ${esc(r.size)}</span><br>
      ${o && o.last_bar === r.last_bar ? `<s>${esc(o.action)}</s><br>` : ""}${esc(r.action)}</div>`;
  }).join("");
  h += `<div class="actions"><button class="primary" id="bpapply" ${pr.errors?.length ? "disabled" : ""}>${t("应用这些修改")}</button><button id="bpdiscard">${t("放弃")}</button></div></div>`;
  return h;
}

function boardEdit(fn) {
  fn(board.rows);
  board.dirty = true; board.msg = "";
  renderBoard();
}

function bindBoard() {
  const B = $("#board");
  B.querySelectorAll("[data-bi]").forEach((el) => el.onclick = () => { board.sel = +el.dataset.bi; renderBoard(); });
  B.querySelectorAll("[data-bnav]").forEach((el) => el.onclick = () => { board.sel += +el.dataset.bnav; renderBoard(); });
  const r = board.rows[board.sel];
  B.querySelectorAll("[data-bf]").forEach((el) => el.onchange = () => boardEdit(() => { r[el.dataset.bf] = el.value || (el.dataset.bf === "lipsync" ? null : ""); }));
  B.querySelectorAll("[data-bm]").forEach((el) => el.onchange = () => boardEdit(() => {
    const m = el.dataset.bm;
    r.members = el.checked ? [...r.members, m] : r.members.filter((x) => x !== m);
    r.members = board.data.members.filter((x) => r.members.includes(x));   // keep the stage order (left first)
    if (r.lipsync && !r.members.includes(r.lipsync)) r.lipsync = null;
    if (!r.members.length) r.kind = "empty"; else if (r.kind === "empty") r.kind = r.members.length > 1 ? "duo" : "solo";
  }));
  const lk = $("#block"); if (lk) lk.onchange = () => boardEdit(() => { if (lk.checked) r.locked = true; else delete r.locked; });
  const sp = $("#bsplit"); if (sp) sp.onclick = () => boardEdit((rows) => {
    const at = +$("#bsplitat").value, a = { ...r, last_bar: at - 1 }, b = { ...r, first_bar: at, sid: null, frame_file: null };
    delete a.locked; delete b.locked;
    rows.splice(board.sel, 1, a, b);
  });
  const mn = $("#bmergen"); if (mn) mn.onclick = () => boardEdit((rows) => { const n = rows[board.sel + 1]; rows.splice(board.sel, 2, { ...r, last_bar: n.last_bar }); });
  const mp = $("#bmergep"); if (mp) mp.onclick = () => boardEdit((rows) => { const p = rows[board.sel - 1]; rows.splice(board.sel - 1, 2, { ...p, last_bar: r.last_bar }); board.sel -= 1; });
  $("#bundo").onclick = () => initBoard(true);
  const showApply = () => { $("#bcustom").classList.toggle("hidden", $("#brange").value !== "custom"); $("#bropts").classList.remove("hidden"); };
  ["#brange", "#bfrom", "#bto", "#baspect"].forEach((id) => { const el = $(id); if (el) el.onchange = showApply; });
  $("#bropts").onclick = async () => {
    const rv = $("#brange").value;
    const range = rv === "custom" ? { bars: [+$("#bfrom").value, +$("#bto").value] } : rv;
    if (!confirm(t("改范围/画幅会重新设计分镜，之后的首帧和视频都要重新生成（旧文件保留）。继续？"))) return;
    try { await api(`/api/projects/${cur}/opts`, { range, aspect: $("#baspect").value }); }
    catch (e) { let m = e.message; try { m = JSON.parse(m).detail || m; } catch (_) { /* text */ } return alert(m); }
    await api(`/api/projects/${cur}/action`, { task: "regen_design" });
    board = null; lastPanelKey = ""; refresh();
  };
  $("#bsave").onclick = async () => {
    try { await api(`/api/projects/${cur}/board`, { rows: board.rows }); }
    catch (e) { let m = e.message; try { m = JSON.parse(m).detail || m; } catch (_) { /* text */ } board.msg = t("没保存：{0}", m); return renderBoard(); }
    board.dirty = false; board.msg = t("已保存，正在更新镜头表…"); renderBoard();
    setTimeout(() => { lastPanelKey = ""; refresh(); }, 2500);
  };
  $("#banim").onclick = async () => {
    if (board.dirty && !confirm(t("有未保存的修改：预览用的是已保存的分镜。继续？"))) return;
    await api(`/api/projects/${cur}/action`, { task: "animatic" }); board.msg = t("正在生成预览（约 10–30 秒）…"); renderBoard();
  };
  $("#bchatgo").onclick = async () => {
    const m = $("#bchat").value.trim();
    if (!m) return;
    if (board.dirty && !confirm(t("有未保存的修改：模型会在已保存的分镜上修改。继续？"))) return;
    try { await api(`/api/projects/${cur}/board/chat`, { message: m }); }
    catch (e) { let x = e.message; try { x = JSON.parse(x).detail || x; } catch (_) { /* text */ } return alert(x); }
    board.msg = t("模型正在修改分镜（本地模型约 2 分钟）…"); renderBoard();
  };
  const pa = $("#bpapply"); if (pa) pa.onclick = async () => {
    try { await api(`/api/projects/${cur}/board`, { rows: board.data.proposal.rows }); }
    catch (e) { let m = e.message; try { m = JSON.parse(m).detail || m; } catch (_) { /* text */ } return alert(m); }
    board.dirty = false; board.msg = t("已应用，正在更新镜头表…"); renderBoard();
    setTimeout(() => { lastPanelKey = ""; refresh(); }, 2500);
  };
  const pd = $("#bpdiscard"); if (pd) pd.onclick = async () => { await api(`/api/projects/${cur}/board/discard`, {}); initBoard(); };
}
