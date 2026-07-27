/**
 * Minimax TTS 控制台前端逻辑
 * 通过 window.AstrBotPluginPage bridge 与后端通信
 */

const bridge = window.AstrBotPluginPage;

// 全局状态
const state = {
  ctx: null,
  uiConfig: {
    color_mode: "dynamic",
    brand_color: "#0f6cbd",
    background_mode: "theme",
    custom_background: "#f5f5f5",
    custom_background_dark: "#1a1a1a",
    background_image: "",
    corner_radius: 10,
  },
  voices: [],
};

// ========== 初始化 ==========
async function init() {
  state.ctx = await bridge.ready();
  applyTheme(state.ctx);
  applyI18n(state.ctx);
  bindEvents();
  await loadUiConfig();
  applyUiConfig();
  loadOverview();
  loadStaticVoices();  // 先加载内置音色填充下拉

  bridge.onContext((newCtx) => {
    state.ctx = newCtx;
    applyTheme(newCtx);
    applyI18n(newCtx);
    applyUiConfig();
  });
}

// ========== 主题 ==========
function applyTheme(ctx) {
  // data-theme 已由 bridge SDK 维护，这里只处理额外取色
  applyUiConfig();
}

// ========== 国际化 ==========
function applyI18n(ctx) {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    const fallback = el.textContent;
    el.textContent = bridge.t(key, fallback);
  });
}

// ========== UI 配置 ==========
async function loadUiConfig() {
  try {
    const cfg = await bridge.apiGet("config/ui");
    state.uiConfig = { ...state.uiConfig, ...cfg };
  } catch (e) {
    console.warn("加载 UI 配置失败，使用默认", e);
  }
}

function applyUiConfig() {
  const root = document.documentElement;
  const ui = state.uiConfig;
  const isDark = state.ctx?.isDark;

  // 品牌色
  if (ui.color_mode === "static" && ui.brand_color) {
    root.style.setProperty("--color-brand", ui.brand_color);
    // 简单派生 hover/pressed
    root.style.setProperty("--color-brand-hover", shadeColor(ui.brand_color, -10));
    root.style.setProperty("--color-brand-pressed", shadeColor(ui.brand_color, -20));
    root.style.setProperty("--color-brand-fg", ui.brand_color);
    root.style.setProperty("--color-brand-border", ui.brand_color);
  }

  // 背景
  const app = document.getElementById("app");
  app.classList.remove("bg-mode-brand-gradient", "bg-mode-custom");
  app.style.backgroundImage = "";
  app.style.backgroundSize = "";
  app.style.backgroundPosition = "";
  app.style.backgroundAttachment = "";
  if (ui.background_mode === "brand_gradient") {
    app.classList.add("bg-mode-brand-gradient");
  } else if (ui.background_mode === "custom") {
    const bg = isDark
      ? ui.custom_background_dark || "#1a1a1a"
      : ui.custom_background || "#f5f5f5";
    root.style.setProperty("--color-app-bg", bg);
    app.classList.add("bg-mode-custom");
  } else if (ui.background_mode === "image" && ui.background_image) {
    app.style.backgroundImage = `url('./bg?t=${Date.now()}')`;
    app.style.backgroundSize = "cover";
    app.style.backgroundPosition = "center";
    app.style.backgroundAttachment = "fixed";
  }

  // 圆角
  if (ui.corner_radius != null) {
    root.style.setProperty("--radius-large", `${ui.corner_radius}px`);
    root.style.setProperty("--radius-xlarge", `${ui.corner_radius}px`);
  }

  // 同步设置面板的输入框
  syncSettingsInputs();
  // 同步背景图预览
  updateBgPreview();
}

function syncSettingsInputs() {
  const ui = state.uiConfig;
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el && val != null) el.value = val;
  };
  set("ui-color-mode", ui.color_mode);
  set("ui-brand-color", ui.brand_color);
  set("ui-brand-color-picker", ui.brand_color);
  set("ui-bg-mode", ui.background_mode);
  set("ui-radius", ui.corner_radius);
  set("ui-custom-bg", ui.custom_background);
  set("ui-custom-bg-picker", ui.custom_background);
  set("ui-custom-bg-dark", ui.custom_background_dark);
  set("ui-custom-bg-dark-picker", ui.custom_background_dark);
}

// 颜色变亮/变暗工具
function shadeColor(hex, percent) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const num = parseInt(h, 16);
  const amt = Math.round(2.55 * percent);
  const r = Math.max(0, Math.min(255, (num >> 16) + amt));
  const g = Math.max(0, Math.min(255, ((num >> 8) & 0xff) + amt));
  const b = Math.max(0, Math.min(255, (num & 0xff) + amt));
  return "#" + ((r << 16) | (g << 8) | b).toString(16).padStart(6, "0");
}

// ========== 事件绑定 ==========
function bindEvents() {
  // Tabs
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // 刷新
  document.getElementById("btn-refresh-all").onclick = loadOverview;
  document.getElementById("btn-refresh-logs").onclick = loadLogs;

  // 音色
  document.getElementById("btn-load-voices").onclick = loadVoices;
  document.getElementById("voice-filter").oninput = filterVoices;
  document.getElementById("voice-type").onchange = loadVoices;

  // 克隆
  const cloneInput = document.getElementById("clone-source");
  const cloneDrop = document.getElementById("clone-drop");
  cloneInput.onchange = (e) => {
    const f = e.target.files[0];
    document.getElementById("clone-file-name").textContent = f ? f.name : "未选择文件";
  };
  ["dragover", "dragenter"].forEach((evt) => {
    cloneDrop.addEventListener(evt, (e) => {
      e.preventDefault();
      cloneDrop.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    cloneDrop.addEventListener(evt, (e) => {
      e.preventDefault();
      cloneDrop.classList.remove("dragover");
    });
  });
  cloneDrop.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) {
      cloneInput.files = e.dataTransfer.files;
      document.getElementById("clone-file-name").textContent = f.name;
    }
  });
  document.getElementById("btn-clone").onclick = doClone;

  // 按 ID 加载已有音色
  document.getElementById("btn-load-voice").onclick = loadVoiceById;
  document.getElementById("load-voice-id").addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadVoiceById();
  });

  // 背景图上传
  const bgInput = document.getElementById("bg-image-file");
  const bgDrop = document.getElementById("bg-drop");
  bgInput.onchange = (e) => {
    const f = e.target.files[0];
    document.getElementById("bg-file-name").textContent = f
      ? f.name
      : "点击或拖拽图片到此处（jpg/png/webp/gif，建议 ≤2MB）";
  };
  ["dragover", "dragenter"].forEach((evt) => {
    bgDrop.addEventListener(evt, (e) => {
      e.preventDefault();
      bgDrop.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    bgDrop.addEventListener(evt, (e) => {
      e.preventDefault();
      bgDrop.classList.remove("dragover");
    });
  });
  bgDrop.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) {
      bgInput.files = e.dataTransfer.files;
      document.getElementById("bg-file-name").textContent = f.name;
    }
  });
  document.getElementById("btn-bg-upload").onclick = uploadBgImage;
  document.getElementById("btn-bg-remove").onclick = removeBgImage;

  // 调试
  document.getElementById("btn-debug-synth").onclick = doDebugSynth;
  document.getElementById("debug-speed").oninput = (e) => {
    document.getElementById("debug-speed-val").textContent = parseFloat(e.target.value).toFixed(1);
  };

  // 设置
  document.getElementById("btn-save-ui").onclick = saveUiConfig;
  document.getElementById("btn-reset-ui").onclick = resetUiConfig;

  // 颜色选择器与文本框联动
  linkColorPicker("ui-brand-color-picker", "ui-brand-color");
  linkColorPicker("ui-custom-bg-picker", "ui-custom-bg");
  linkColorPicker("ui-custom-bg-dark-picker", "ui-custom-bg-dark");

  // 实时预览
  ["ui-color-mode", "ui-brand-color", "ui-bg-mode", "ui-radius",
   "ui-custom-bg", "ui-custom-bg-dark"].forEach((id) => {
    document.getElementById(id).addEventListener("input", previewUiConfig);
  });
}

function linkColorPicker(pickerId, textId) {
  const picker = document.getElementById(pickerId);
  const text = document.getElementById(textId);
  picker.addEventListener("input", () => { text.value = picker.value; });
  text.addEventListener("input", () => {
    if (/^#[0-9a-fA-F]{6}$/.test(text.value)) picker.value = text.value;
  });
}

function previewUiConfig() {
  state.uiConfig = {
    color_mode: document.getElementById("ui-color-mode").value,
    brand_color: document.getElementById("ui-brand-color").value,
    background_mode: document.getElementById("ui-bg-mode").value,
    custom_background: document.getElementById("ui-custom-bg").value,
    custom_background_dark: document.getElementById("ui-custom-bg-dark").value,
    background_image: state.uiConfig.background_image || "",
    corner_radius: parseInt(document.getElementById("ui-radius").value) || 10,
  };
  applyUiConfig();
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".tab-content").forEach((c) => {
    c.classList.toggle("active", c.id === `tab-${name}`);
  });
  if (name === "logs") loadLogs();
  if (name === "overview") loadOverview();
}

// ========== 状态总览 ==========
async function loadOverview() {
  try {
    const stats = await bridge.apiGet("stats");
    const apiBadge = document.getElementById("api-status-badge");
    if (stats.api_ok) {
      apiBadge.className = "badge badge-success";
      apiBadge.textContent = "API 正常";
    } else {
      apiBadge.className = "badge badge-danger";
      apiBadge.textContent = "API 异常";
    }
    document.getElementById("stat-api").innerHTML = stats.api_ok
      ? '<span class="badge badge-success">正常</span>'
      : '<span class="badge badge-danger">异常</span>';
    document.getElementById("stat-today").textContent = stats.today_count || 0;
    document.getElementById("stat-cache").textContent =
      `${(stats.cache_size_mb || 0).toFixed(1)} MB`;
    document.getElementById("stat-ffmpeg").innerHTML = stats.ffmpeg_available
      ? '<span class="badge badge-success">可用</span>'
      : '<span class="badge badge-warning">不可用</span>';
    document.getElementById("stat-mode").textContent = stats.mode || "—";
    document.getElementById("stat-model").textContent = stats.model || "—";
    document.getElementById("stat-voice").textContent = stats.voice_id || "—";
    document.getElementById("stat-polish").textContent = "—";  // 由 config/full 补充
    try {
      const full = await bridge.apiGet("config/full");
      const polishEnabled = (full.polish || {}).enabled;
      document.getElementById("stat-polish").innerHTML = polishEnabled
        ? '<span class="badge badge-info">已启用</span>'
        : '<span class="badge badge-neutral">未启用</span>';
    } catch (_) {}
  } catch (e) {
    showToast(`加载状态失败: ${e.message}`, "error");
  }
}

// ========== 音色管理 ==========
async function loadStaticVoices() {
  try {
    const data = await bridge.apiGet("voices/static");
    state.voices = data.voices || [];
    fillDebugVoiceSelect();
    if (document.getElementById("voice-list").querySelector(".empty-state")) {
      renderVoices(state.voices);
    }
  } catch (_) {}
}

async function loadVoices() {
  const listEl = document.getElementById("voice-list");
  listEl.innerHTML = '<div class="empty-state"><div class="skeleton" style="height:60px"></div></div>';
  const voiceType = document.getElementById("voice-type").value;
  try {
    const data = await bridge.apiGet("voices");
    let voices = data.voices || [];
    if (voiceType !== "all") {
      voices = voices.filter((v) => (v.type || "") === voiceType);
    }
    state.voices = voices;
    renderVoices(voices);
    fillDebugVoiceSelect();
    showToast(`已加载 ${voices.length} 个音色`, "success");
  } catch (e) {
    listEl.innerHTML = `<div class="empty-state">
      <div class="empty-state-icon">⚠️</div>
      <p>加载失败：${e.message}</p>
      <p class="text-sm text-muted">已显示内置音色列表</p>
    </div>`;
    renderVoices(state.voices);
  }
}

function renderVoices(voices) {
  const filter = document.getElementById("voice-filter").value.toLowerCase();
  const filtered = voices.filter(
    (v) =>
      !filter ||
      (v.name || "").toLowerCase().includes(filter) ||
      (v.voice_id || "").toLowerCase().includes(filter),
  );
  const listEl = document.getElementById("voice-list");
  if (filtered.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><p>无匹配音色</p></div>';
    return;
  }
  listEl.innerHTML = filtered
    .map(
      (v) => `
    <div class="stat-card">
      <div class="flex-between">
        <div style="overflow:hidden">
          <div class="text-bold truncate">${v.name || "未命名"}</div>
          <div class="text-mono text-sm text-muted truncate">${v.voice_id || ""}</div>
        </div>
        <button class="btn btn-subtle btn-sm" data-voice="${v.voice_id}" data-name="${v.name || ""}">
          ▶ 试听
        </button>
      </div>
    </div>
  `,
    )
    .join("");
  listEl.querySelectorAll("button[data-voice]").forEach((btn) => {
    btn.onclick = () => previewVoice(btn.dataset.voice, btn.dataset.name);
  });
}

function filterVoices() {
  renderVoices(state.voices);
}

function fillDebugVoiceSelect() {
  const sel = document.getElementById("debug-voice");
  const cur = sel.value;
  sel.innerHTML = state.voices
    .map(
      (v) =>
        `<option value="${v.voice_id}">${v.name} (${v.voice_id})</option>`,
    )
    .join("");
  if (cur && state.voices.some((v) => v.voice_id === cur)) {
    sel.value = cur;
  }
}

async function previewVoice(voiceId, name) {
  showToast(`正在合成 ${name || voiceId} 的试听...`, "info");
  try {
    const result = await bridge.apiPost("preview", {
      voice_id: voiceId,
      text: "你好，这是该音色的试听样本。",
    });
    playAudio(result.audio_path, `试听: ${name || voiceId}`);
  } catch (e) {
    showToast(`试听失败: ${e.message}`, "error");
  }
}

// ========== 语音克隆 ==========
async function doClone() {
  const fileInput = document.getElementById("clone-source");
  const file = fileInput.files[0];
  if (!file) {
    showToast("请选择源音频文件", "warning");
    return;
  }
  const voiceId = document.getElementById("clone-voice-id").value.trim();
  if (!voiceId || !/^[a-zA-Z0-9_]+$/.test(voiceId)) {
    showToast("音色 ID 只能包含字母数字下划线", "warning");
    return;
  }
  const model = document.getElementById("clone-model").value;
  const previewText = document.getElementById("clone-preview-text").value;

  const btn = document.getElementById("btn-clone");
  btn.disabled = true;
  btn.textContent = "上传中...";
  const resultEl = document.getElementById("clone-result");
  resultEl.innerHTML = '<div class="progress"><div class="progress-bar" style="width:30%"></div></div>';

  try {
    // 1. 上传文件
    const uploadResp = await bridge.upload("clone/upload", file);
    resultEl.innerHTML = '<div class="progress"><div class="progress-bar" style="width:60%"></div></div>';

    // 2. 执行克隆
    btn.textContent = "克隆中...";
    const cloneResp = await bridge.apiPost("clone/start", {
      source_file_id: uploadResp.file_id,
      voice_id: voiceId,
      model: model,
      preview_text: previewText,
    });

    if (cloneResp.success) {
      let audioHtml = "";
      if (cloneResp.audio_path) {
        audioHtml = `<div class="audio-player mt-s">
          <audio controls src="./audio?path=${encodeURIComponent(cloneResp.audio_path)}"></audio>
        </div>`;
      }
      resultEl.innerHTML = `
        <span class="badge badge-success">克隆成功</span>
        <p class="text-sm text-muted mt-s">音色 ID: <code>${voiceId}</code></p>
        ${audioHtml}
      `;
      showToast("语音克隆成功！", "success");
    } else {
      throw new Error("克隆未成功");
    }
  } catch (e) {
    resultEl.innerHTML = `<span class="badge badge-danger">克隆失败</span>
      <p class="text-sm text-muted mt-s">${e.message}</p>`;
    showToast(`克隆失败: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "开始克隆";
  }
}

// ========== 按 ID 加载已有音色 ==========
async function loadVoiceById() {
  const voiceId = document.getElementById("load-voice-id").value.trim();
  if (!voiceId) {
    showToast("请输入音色 ID", "warning");
    return;
  }
  const btn = document.getElementById("btn-load-voice");
  btn.disabled = true;
  btn.textContent = "查询中...";
  const resultEl = document.getElementById("load-voice-result");
  resultEl.innerHTML = '<div class="skeleton" style="height:90px"></div>';
  try {
    const data = await bridge.apiGet("voice/get", { voice_id: voiceId });
    const label = (data.voice && (data.voice.name || data.voice.voice_id)) || voiceId;
    const typeBadge = data.found
      ? (data.voice.type === "system"
          ? '<span class="badge badge-info">系统音色</span>'
          : '<span class="badge badge-success">克隆音色</span>')
      : '<span class="badge badge-warning">未在列表中</span>';
    const note = data.found
      ? ""
      : `<p class="text-sm text-muted mt-s">${escapeHtml(data.note || "若 Minimax 端仍有效即可试听/设为默认")}</p>`;
    resultEl.innerHTML = `
      <div class="stat-card">
        <div class="flex-between">
          <div style="overflow:hidden">
            <div class="text-bold truncate">${escapeHtml(label)}</div>
            <div class="text-mono text-sm text-muted truncate">${escapeHtml(voiceId)}</div>
            <div class="mt-s">${typeBadge}</div>
          </div>
        </div>
        ${note}
        <div class="flex gap-s mt-m">
          <button class="btn btn-subtle btn-sm" id="btn-preview-loaded">▶ 试听</button>
          <button class="btn btn-primary btn-sm" id="btn-set-default">设为默认音色</button>
        </div>
      </div>`;
    document.getElementById("btn-preview-loaded").onclick = () =>
      previewVoice(voiceId, label);
    document.getElementById("btn-set-default").onclick = () =>
      setDefaultVoice(voiceId, label);
    showToast(data.found ? "已找到该音色" : "未在列表中找到，仍可试听", data.found ? "success" : "info");
  } catch (e) {
    resultEl.innerHTML = `<div class="stat-card">
      <span class="badge badge-danger">查询失败</span>
      <p class="text-sm text-muted mt-s">${escapeHtml(e.message)}</p>
    </div>`;
    showToast(`查询失败: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "查询音色";
  }
}

async function setDefaultVoice(voiceId, name) {
  try {
    await bridge.apiPost("voice/set_default", { voice_id: voiceId });
    showToast(`已将「${name}」设为默认音色`, "success");
    loadOverview();
  } catch (e) {
    showToast(`设置失败: ${e.message}`, "error");
  }
}

// ========== 背景图上传 ==========
async function uploadBgImage() {
  const fileInput = document.getElementById("bg-image-file");
  const file = fileInput.files[0];
  if (!file) {
    showToast("请选择背景图片", "warning");
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    showToast("图片不能超过 5MB", "warning");
    return;
  }
  const btn = document.getElementById("btn-bg-upload");
  btn.disabled = true;
  btn.textContent = "上传中...";
  try {
    const resp = await bridge.upload("bg/upload", file);
    state.uiConfig.background_image = resp.path;
    document.getElementById("bg-file-name").textContent = resp.filename || file.name;
    updateBgPreview();
    // 自动切换到图片背景模式并预览
    document.getElementById("ui-bg-mode").value = "image";
    previewUiConfig();
    showToast("背景图上传成功，已切换为图片背景", "success");
  } catch (e) {
    showToast(`上传失败: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "上传";
  }
}

async function removeBgImage() {
  try {
    await bridge.apiPost("bg/remove");
    state.uiConfig.background_image = "";
    document.getElementById("bg-file-name").textContent =
      "点击或拖拽图片到此处（jpg/png/webp/gif，建议 ≤2MB）";
    document.getElementById("bg-image-file").value = "";
    updateBgPreview();
    applyUiConfig();
    showToast("已移除背景图", "info");
  } catch (e) {
    showToast(`移除失败: ${e.message}`, "error");
  }
}

function updateBgPreview() {
  const ui = state.uiConfig;
  const wrap = document.getElementById("bg-preview-wrap");
  const img = document.getElementById("bg-preview");
  if (ui.background_image && wrap && img) {
    img.src = `./bg?t=${Date.now()}`;
    wrap.style.display = "";
  } else if (wrap) {
    wrap.style.display = "none";
  }
}

// ========== 调试试听 ==========
async function doDebugSynth() {
  const text = document.getElementById("debug-text").value.trim();
  if (!text) {
    showToast("请输入合成文本", "warning");
    return;
  }
  const voice = document.getElementById("debug-voice").value;
  const speed = parseFloat(document.getElementById("debug-speed").value);
  const emotion = document.getElementById("debug-emotion").value;

  const btn = document.getElementById("btn-debug-synth");
  btn.disabled = true;
  btn.textContent = "合成中...";
  const resultEl = document.getElementById("debug-result");
  resultEl.innerHTML = '<div class="progress"><div class="progress-bar" style="width:50%"></div></div>';

  try {
    const result = await bridge.apiPost("debug/synth", {
      text,
      voice_id: voice,
      speed,
      emotion,
    });
    resultEl.innerHTML = `
      <div class="audio-player">
        <audio controls src="./audio?path=${encodeURIComponent(result.audio_path)}"></audio>
      </div>
      <p class="text-sm text-muted mt-s">
        耗时 ${result.elapsed_ms}ms · 字符 ${result.usage_chars}
      </p>
    `;
    showToast("合成成功", "success");
  } catch (e) {
    resultEl.innerHTML = `<span class="badge badge-danger">合成失败</span>
      <p class="text-sm text-muted mt-s">${e.message}</p>`;
    showToast(`合成失败: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "合成试听";
  }
}

// ========== 运行日志 ==========
async function loadLogs() {
  try {
    const data = await bridge.apiGet("logs", { limit: 200 });
    const body = document.getElementById("logs-body");
    const logs = data.logs || [];
    if (logs.length === 0) {
      body.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center">暂无记录</td></tr>';
      return;
    }
    body.innerHTML = logs
      .slice()
      .reverse()
      .map(
        (l) => `<tr>
          <td class="text-mono text-sm">${l.time || ""}</td>
          <td>${l.mode || ""}</td>
          <td>${l.chars || 0}</td>
          <td>${l.elapsed_ms || 0}ms</td>
          <td>${l.cached ? '<span class="badge badge-success">命中</span>' : '<span class="badge badge-neutral">合成</span>'}</td>
          <td class="text-sm text-muted truncate" style="max-width:240px">${escapeHtml(l.preview || "")}</td>
        </tr>`,
      )
      .join("");
  } catch (e) {
    showToast(`加载日志失败: ${e.message}`, "error");
  }
}

// ========== 界面设置 ==========
async function saveUiConfig() {
  previewUiConfig();
  try {
    await bridge.apiPost("config/save", { ui: state.uiConfig });
    showToast("设置已保存", "success");
  } catch (e) {
    showToast(`保存失败: ${e.message}`, "error");
  }
}

function resetUiConfig() {
  state.uiConfig = {
    color_mode: "dynamic",
    brand_color: "#0f6cbd",
    background_mode: "theme",
    custom_background: "#f5f5f5",
    custom_background_dark: "#1a1a1a",
    background_image: "",
    corner_radius: 10,
  };
  applyUiConfig();
  showToast("已恢复默认（需点击保存生效）", "info");
}

// ========== 工具 ==========
function playAudio(path, label) {
  const container = document.createElement("div");
  container.className = "toast";
  container.style.cssText = "min-width:320px;padding:12px";
  container.innerHTML = `
    <div class="text-sm text-bold mb-s">${label || "试听"}</div>
    <audio controls autoplay src="./audio?path=${encodeURIComponent(path)}" style="width:100%"></audio>
  `;
  document.getElementById("toast-container").appendChild(container);
  setTimeout(() => {
    container.style.animation = "toast-out 0.25s forwards";
    setTimeout(() => container.remove(), 300);
  }, 30000);
}

function showToast(msg, type = "info") {
  const t = document.createElement("div");
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  document.getElementById("toast-container").appendChild(t);
  setTimeout(() => {
    t.style.animation = "toast-out 0.25s forwards";
    setTimeout(() => t.remove(), 300);
  }, 3000);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// 启动
init();
