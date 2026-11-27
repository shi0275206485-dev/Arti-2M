// Settings: local LLM (Unsloth Studio) instead of Claude, chosen per task. Server: /api/llm* (webagent/llm_local.py).
const LLM_TASKS = { song: "写歌", cover: "封面提示词", concept: "MV 概念", design: "分镜设计", pick: "挑参考图（看图）", qc: "质检（看图）" };
const errText = (e) => { let m = e.message || String(e); try { m = JSON.parse(m).detail || m; } catch (_) { /* text */ } return m; };

async function loadLlm() {
  const r = await api("/api/llm");
  const c = r.config, st = r.status;
  $("#llm_url").value = c.base_url; $("#llm_model").value = c.model; $("#llm_variant").value = c.gguf_variant;
  $("#llm_key").value = ""; $("#llm_key").placeholder = c.has_key ? t("已保存（留空不修改）") : t("在 Unsloth Studio 的 Settings → API 里创建");
  $("#llm_think").checked = c.thinking; $("#llm_unload").checked = c.unload_for_gpu;
  $("#llm_tasks").innerHTML = r.tasks.map((k) => `<div>${esc(t(LLM_TASKS[k] || k))}</div>
    <select data-task="${k}"><option value="claude">Claude</option><option value="local" ${c.tasks[k] === "local" ? "selected" : ""}>${t("本地模型")}</option></select>`).join("");
  $("#llmstat").textContent = !st.reachable ? t("Unsloth Studio 没有运行（{0}）", c.base_url)
    : !st.has_key ? t("Unsloth Studio 已运行，还没有填 API Key")
    : st.ok === false ? (st.error || "")
    : st.loaded ? t("Unsloth Studio 已运行 · {0} 已加载", c.model) : t("Unsloth Studio 已运行 · 当前加载：{0}", st.active || t("无"));
}

function llmForm() {
  const tasks = {};
  document.querySelectorAll("#llm_tasks [data-task]").forEach((s) => tasks[s.dataset.task] = s.value);
  return { base_url: $("#llm_url").value, api_key: $("#llm_key").value, model: $("#llm_model").value,
           gguf_variant: $("#llm_variant").value, thinking: $("#llm_think").checked, unload_for_gpu: $("#llm_unload").checked, tasks };
}

async function llmDo(btn, fn) {
  const msg = $("#llm_msg"); btn.disabled = true; msg.textContent = t("处理中…");
  try { msg.textContent = await fn(); } catch (e) { msg.textContent = t("失败：{0}", errText(e)); }
  btn.disabled = false; loadLlm().catch(() => {}); refreshStatus();
}

$("#llm_save").onclick = () => llmDo($("#llm_save"), async () => { await api("/api/llm", { config: llmForm() }); return t("已保存"); });
$("#llm_list").onclick = () => llmDo($("#llm_list"), async () => {
  await api("/api/llm", { config: llmForm() });
  const ms = await api("/api/llm/models");
  $("#llm_models").innerHTML = ms.map((m) => `<option value="${esc(m.id)}">${m.loaded ? "● " : ""}${esc(m.id)}</option>`).join("");
  return t("Studio 里有 {0} 个模型（点模型输入框选择）", ms.length);
});
$("#llm_test").onclick = () => llmDo($("#llm_test"), async () => {
  await api("/api/llm", { config: llmForm() });
  const r = await api("/api/llm/test", {});
  return t("测试通过（{0} 秒，含加载）：{1}", r.seconds, JSON.stringify(r.answer));
});
$("#llm_unload_now").onclick = () => llmDo($("#llm_unload_now"), async () => { await api("/api/llm/unload", {}); return t("已卸载"); });
