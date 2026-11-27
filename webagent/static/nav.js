// Page router + bottom player. Routes are URL hashes so the browser's back button works:
//   #create (music maker)  #library (music lib)  #song/<id>  #mv (MV maker)  #mvlib (MV lib)  #mv/<projectId>  #cast  #settings
// `tab` (used by app.js / studio.js polling) is "music" on a song page, "mv" on a project page, else the page name.
const PAGES = ["create", "library", "song", "mv", "mvlib", "project", "cast", "settings"];
const NAV_OF = { song: "library", project: "mvlib" };
let page = "create";

function route() {
  const [p, raw] = (location.hash.slice(1) || "create").split("/");
  const id = raw ? decodeURIComponent(raw) : null;
  page = p === "mv" && id ? "project" : PAGES.includes(p) && p !== "project" ? p : "create";
  if (page === "song" && !id) { location.hash = "#library"; return; }
  if (page === "song" && curSong !== id) { curSong = id; songKey = ""; }
  if (page === "project" && cur !== id) { cur = id; view = null; lastPanelKey = ""; }
  tab = page === "song" ? "music" : page === "project" ? "mv" : page;
  document.querySelectorAll("#main > .page").forEach((s) => s.classList.toggle("hidden", s.id !== "pg-" + page));
  document.querySelectorAll("#navlinks a").forEach((a) => a.classList.toggle("on", a.dataset.page === (NAV_OF[page] || page)));
  if (page === "song") { songKey = ""; refreshSong().catch(() => {}); }
  if (page === "project") { lastPanelKey = ""; refresh().catch(() => {}); }
  if (page === "create" || page === "library") refreshSongs().catch(() => {});
  if (page === "mv" || page === "mvlib") refreshList().catch(() => {});
  if (page === "mv") refreshSongs().catch(() => {});
  if (page === "mv" || page === "cast") refreshCast().catch(() => {});
  if (page === "settings") loadLlm().catch(() => {});
  $("#main").scrollTop = 0;
}

// compatibility with the older two-tab calls
function setTab(name) { location.hash = name === "music" ? (curSong ? "#song/" + encodeURIComponent(curSong) : "#library") : (cur ? "#mv/" + encodeURIComponent(cur) : "#mv"); }

// generated cover art: a stable gradient per id (no images needed)
// songs with cover art (songs/<id>/cover.png, `t` = when it was made) show the image instead
const coverUrl = (id, t) => t ? `/songfiles/${encodeURIComponent(id)}/cover.png?t=${t}` : "";
function coverStyle(id, img) {
  if (img) return `background:#111 url('${img}') center/cover no-repeat`;
  let h = 0;
  for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const a = h % 360, b = (a + 40 + (h >> 9) % 120) % 360;
  return `background:radial-gradient(circle at ${20 + (h >> 3) % 60}% ${20 + (h >> 6) % 60}%, hsl(${a} 80% 62%), transparent 60%),`
    + `linear-gradient(135deg, hsl(${b} 60% 28%), hsl(${a} 55% 14%))`;
}

// ---------- bottom player
function playSong(s) {
  $("#player").classList.remove("hidden");
  document.body.classList.add("playing");
  $("#pcover").style.cssText = coverStyle(s.id, coverUrl(s.id, s.cover));
  $("#ptitle2").textContent = s.title || s.id;
  $("#psub").textContent = [t(ENGINE_LABEL[s.engine] || s.engine), s.instrumental ? t("纯音乐") : "", fmtDur(s.duration)].filter(Boolean).join(" · ");
  const a = $("#paudio");
  a.src = `/songfiles/${encodeURIComponent(s.id)}/audio/song.wav?t=${Date.now()}`;
  a.play().catch(() => {});
}
$("#pclose").onclick = () => { $("#paudio").pause(); $("#player").classList.add("hidden"); document.body.classList.remove("playing"); };

window.addEventListener("hashchange", route);
route();

// ---------- delete a song (Music Lib) or an MV project (MV Lib): the server moves the folder to trash/
async function deleteItem(kind, id, title) {
  const song = kind === "song";
  const msg = song ? t("删除歌曲「{0}」？\n文件夹会移到 trash/songs/（需要时可以手动移回来）。已经用这首歌做的 MV 不受影响。", title || id)
    : t("删除 MV「{0}」？\n项目文件夹（含所有画面、视频和成片）会移到 trash/projects/（需要时可以手动移回来）。", title || id);
  if (!confirm(msg)) return false;
  try { await api(`/api/${song ? "songs" : "projects"}/${encodeURIComponent(id)}/delete`, {}); }
  catch (e) {
    let m = e.message || String(e);
    try { m = JSON.parse(m).detail || m; } catch (_) { /* plain text */ }
    alert(t("没有删除：{0}", m)); return false;
  }
  if (song) {
    if (curSong === id) { curSong = null; location.hash = "#library"; }
    await refreshSongs();
  } else {
    if (cur === id) { cur = null; location.hash = "#mvlib"; }
    await refreshList();
  }
  return true;
}
