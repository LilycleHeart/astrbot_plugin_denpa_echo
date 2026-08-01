/**
 * Minimax TTS 控制台前端逻辑
 * 通过 window.AstrBotPluginPage bridge 与后端通信
 */

import {
  argbFromHex,
  hexFromArgb,
  themeFromSourceColor,
  sourceColorFromImage,
} from "./vendor/material-color-utilities.js";

const bridge = window.AstrBotPluginPage;

// 全局状态
const state = {
  ctx: null,
  uiConfig: {
    color_mode: "dynamic",
    brand_color: "#ff8ab9",
    background_mode: "theme",
    custom_background: "#F5F6F8",
    custom_background_dark: "#0C0E13",
    background_image: "",
    background_accent: "",
    corner_radius: 14,
    acrylic_enabled: true,
    material_opacity: 45,
    material_blur: 5,
    material_type: "acrylic",
    font_mode: "misans",
    glow_enabled: true,
    glow_intensity: 40,
    shadow_enabled: true,
    shadow_intensity: 60,
    bg_scrim: 40,
    viz_mode: "spectrum",
  },
  voices: [],
  hiddenVoices: new Set(),
  voiceManageMode: false,
  voiceBrowseMode: false,
  _browseVoices: [],
};

/** 持久化用户音色列表到后端独立文件 */
function _persistVoices() {
  bridge.apiPost("dashboard/voices", {
    my_voices: state.voices,
    hidden_voices: [...state.hiddenVoices],
  }).catch(() => {});
}

/** 从后端加载已持久化的音色列表 */
async function _loadPersistedVoices() {
  try {
    const data = await bridge.apiGet("dashboard/voices");
    if (Array.isArray(data.my_voices)) state.voices = data.my_voices;
    if (Array.isArray(data.hidden_voices)) state.hiddenVoices = new Set(data.hidden_voices);
  } catch (_) {}
}

// ========== 初始化 ==========
async function init() {
  state.ctx = await bridge.ready();
  await loadUiConfig();   // 先加载配置，避免 applyTheme 用默认色闪一下
  applyTheme(state.ctx);
  applyI18n(state.ctx);
  bindEvents();
  applyUiConfig();
  syncThemeIcon();
  document.getElementById("app").classList.add("ready");
  loadOverview();
  await _loadPersistedVoices();  // 恢复已持久化的用户音色列表
  loadStaticVoices();  // 填充调试下拉
  Waveform.init();     // 启动波形可视化器

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
  syncThemeIcon();
  applyUiConfig();
}

// 主题切换图标（亮色显示月亮→切暗色, 暗色显示太阳→切亮色）
const ICON_SUN = "M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0a.996.996 0 0 0 0-1.41l-1.06-1.06zm1.06-10.96a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36c.39-.39.39-1.03 0-1.41s-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z";
const ICON_MOON = "M12 3c-4.97 0-9 4.03-9 9s4.03 9 9 9 9-4.03 9-9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z";
function syncThemeIcon() {
  const pathEl = document.getElementById("icon-theme-path");
  const labelEl = document.getElementById("btn-theme-label");
  if (!pathEl) return;
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  pathEl.setAttribute("d", dark ? ICON_SUN : ICON_MOON);
  if (labelEl) labelEl.textContent = dark ? "亮色主题" : "暗色主题";
}

// ========== 国际化 ==========
function applyI18n(ctx) {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    const translated = bridge.t(key, "");
    if (!translated) return;
    // 若元素含子元素（如 label 内嵌 <span id="...-val">），仅替换首个文本节点，
    // 避免 textContent 赋值销毁子节点导致数值 span 丢失
    if (el.childElementCount > 0) {
      const firstText = Array.from(el.childNodes).find(n => n.nodeType === 3 && n.textContent.trim());
      if (firstText) {
        firstText.textContent = translated + " ";
      } else {
        el.insertBefore(document.createTextNode(translated + " "), el.firstChild);
      }
    } else {
      el.textContent = translated;
    }
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
  const isDark = currentIsDark();

  // 品牌色（单源 source: static=手动色, dynamic=背景图提取; 两者都经 MCU 派生全套品牌调色板）
  if (ui.color_mode === "static" && ui.brand_color) {
    applyPalette(ui.brand_color, isDark);
  } else if (ui.color_mode === "dynamic") {
    if (ui.background_mode === "image" && ui.background_image) {
      // 已有提取结果 → 同步套用，跳过取色（持久化后瞬时完成、不再卡）
      if (ui.background_accent) {
        applyPalette(ui.background_accent, isDark);
      } else {
        applyDynamicAccent(ui.background_image);
      }
    } else {
      applyPalette(DEFAULT_SOURCE, isDark);
    }
  }

  // 背景（挂在固定定位的 #bg-layer 上，脱离文档流，tab 切换不影响）
  const body = document.body;
  const bgLayer = document.getElementById("bg-layer");
  body.classList.remove("bg-mode-brand-gradient", "bg-mode-custom");
  if (bgLayer) bgLayer.style.backgroundImage = "";
  if (ui.background_mode === "brand_gradient") {
    body.classList.add("bg-mode-brand-gradient");
  } else if (ui.background_mode === "custom") {
    const bg = isDark
      ? ui.custom_background_dark || "#1a1a1a"
      : ui.custom_background || "#f5f5f5";
    root.style.setProperty("--color-app-bg", bg);
    body.classList.add("bg-mode-custom");
  } else if (ui.background_mode === "image" && ui.background_image) {
    const bgSrc = ui.background_image.startsWith("data:")
      ? ui.background_image
      : `./bg?t=${Date.now()}`;
    if (bgLayer) bgLayer.style.backgroundImage = `url('${bgSrc}')`;
  }

  // 圆角（同时驱动 large/xlarge/medium/small，确保整页可见生效；始终应用，避免配置缺失时静默失效）
  const r = Math.max(0, Math.min(40, Number(ui.corner_radius ?? 14)));
  root.style.setProperty("--radius-large", `${r}px`);
  root.style.setProperty("--radius-xlarge", `${r}px`);
  root.style.setProperty("--radius-medium", `${Math.min(r, 12)}px`);
  root.style.setProperty("--radius-small", `${Math.min(r, 10)}px`);

  // 材质 / 模糊（单令牌统一，全表面一致；设置面板可调）
  root.style.setProperty("--material-opacity", ((ui.material_opacity ?? 45) / 100).toString());
  root.style.setProperty("--material-blur", `${ui.material_blur ?? 5}px`);
  // 背景图暗色遮罩强度
  root.style.setProperty("--bg-scrim", (ui.bg_scrim ?? 40) / 100);
  // 声纹可视化模式
  try { Waveform.setVizMode(ui.viz_mode || "spectrum"); } catch (_) {}
  const appEl = document.getElementById("app");
  if (appEl) {
    appEl.classList.toggle("bg-image-active", !!(ui.background_mode === "image" && ui.background_image));
    if (ui.acrylic_enabled === false) appEl.classList.add("acrylic-off");
    else appEl.classList.remove("acrylic-off");

    // 材质类型：亚克力 / 云母（共用同一 --material-opacity / --material-blur 源）
    if (ui.material_type === "mica") appEl.classList.add("material-mica");
    else appEl.classList.remove("material-mica");

    // 泛光（默认关闭，强度可调）
    if (ui.glow_enabled === true) appEl.classList.remove("glow-off");
    else appEl.classList.add("glow-off");
    root.style.setProperty("--glow-strength", ((ui.glow_intensity ?? 15) / 100).toString());

    // 阴影（默认关闭，强度可调）
    if (ui.shadow_enabled === true) appEl.classList.remove("shadow-off");
    else appEl.classList.add("shadow-off");
    root.style.setProperty("--shadow-strength", ((ui.shadow_intensity ?? 50) / 100).toString());

    // 字体：MiSans 优先 / 系统内置优先
    if (ui.font_mode === "builtin") {
      appEl.classList.add("font-builtin");
      appEl.classList.remove("font-misans");
    } else {
      appEl.classList.add("font-misans");
      appEl.classList.remove("font-builtin");
    }
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
  const radiusVal = document.getElementById("ui-radius-val");
  if (radiusVal) radiusVal.textContent = `${ui.corner_radius ?? 14}px`;
  set("ui-custom-bg", ui.custom_background);
  set("ui-custom-bg-picker", ui.custom_background);
  set("ui-custom-bg-dark", ui.custom_background_dark);
  set("ui-custom-bg-dark-picker", ui.custom_background_dark);
  set("ui-material", ui.material_opacity ?? 45);
  set("ui-blur", ui.material_blur ?? 5);
  const ac = document.getElementById("ui-acrylic-on");
  if (ac) ac.checked = ui.acrylic_enabled !== false;
  const matVal = document.getElementById("ui-material-val");
  if (matVal) matVal.textContent = `${ui.material_opacity ?? 45}%`;
  const blurVal = document.getElementById("ui-blur-val");
  if (blurVal) blurVal.textContent = `${ui.material_blur ?? 5}px`;
  const mt = document.getElementById("ui-material-type");
  if (mt) mt.value = ui.material_type || "acrylic";
  const fo = document.getElementById("ui-font");
  if (fo) fo.value = ui.font_mode || "misans";
  const go = document.getElementById("ui-glow-on");
  if (go) go.checked = ui.glow_enabled === true;
  const gi = document.getElementById("ui-glow");
  if (gi) gi.value = ui.glow_intensity ?? 15;
  const goVal = document.getElementById("ui-glow-val");
  if (goVal) goVal.textContent = `${ui.glow_intensity ?? 15}%`;
  const so = document.getElementById("ui-shadow-on");
  if (so) so.checked = ui.shadow_enabled === true;
  const si = document.getElementById("ui-shadow");
  if (si) si.value = ui.shadow_intensity ?? 50;
  const soVal = document.getElementById("ui-shadow-val");
  if (soVal) soVal.textContent = `${ui.shadow_intensity ?? 50}%`;
  const scrim = document.getElementById("ui-scrim");
  if (scrim) scrim.value = ui.bg_scrim ?? 40;
  const scrimVal = document.getElementById("ui-scrim-val");
  if (scrimVal) scrimVal.textContent = `${ui.bg_scrim ?? 40}%`;
  const vizMode = document.getElementById("ui-viz-mode");
  if (vizMode) vizMode.value = ui.viz_mode || "spectrum";
}

// ========== 品牌色引擎 (Material Color Utilities / M3) ==========
// 单源 source 色 → 派生整套品牌调色板。亮/暗主题分别采用 M3 light/dark scheme 的
// tone, 保证: ① 任意 source 色下对比度均达 WCAG AA; ② 主题切换颜色自动统一
// (light=深 primary / dark=浅 primary, 同 hue 同源); ③ 选中态/容器不依赖材质不透明度。
const DEFAULT_SOURCE = "#ff8ab9";
const paletteCache = {};        // sourceHex|theme -> 派生结果
const dynamicSourceCache = {};  // 背景图 src -> 提取的 source hex

function currentIsDark() {
  return document.documentElement.getAttribute("data-theme") === "dark";
}

// 状态色(成功/警告)用规范源色经 MCU 派生, 与品牌同源但语义独立
const STATUS_SOURCES = { success: "#1B9C5D", warning: "#C98A1B" };
const statusCache = {};
function statusColors(isDark) {
  const key = isDark ? "d" : "l";
  if (statusCache[key]) return statusCache[key];
  const mk = (src) => {
    const s = isDark
      ? themeFromSourceColor(argbFromHex(src)).schemes.dark
      : themeFromSourceColor(argbFromHex(src)).schemes.light;
    return { fg: hexFromArgb(s.primary), bg: hexFromArgb(s.primaryContainer) };
  };
  const v = { success: mk(STATUS_SOURCES.success), warning: mk(STATUS_SOURCES.warning) };
  statusCache[key] = v;
  return v;
}

// "255, 255, 255" 形式, 供 rgba(var(--x), a) 复用
function rgbStr(hex) {
  const h = hex.replace("#", "");
  return `${parseInt(h.slice(0, 2), 16)}, ${parseInt(h.slice(2, 4), 16)}, ${parseInt(h.slice(4, 6), 16)}`;
}

// sRGB Alpha 合成: 把前景色 fg 以透明度 a 叠在背景 bg 上 (M3 抬升层 surface tint scrim 即此算法)
function alphaComposite(fg, bg, a) {
  const ph = fg.replace("#", ""), bh = bg.replace("#", "");
  const pr = parseInt(ph.slice(0, 2), 16), pg = parseInt(ph.slice(2, 4), 16), pb = parseInt(ph.slice(4, 6), 16);
  const br = parseInt(bh.slice(0, 2), 16), bg2 = parseInt(bh.slice(2, 4), 16), bb = parseInt(bh.slice(4, 6), 16);
  const r = Math.round(a * pr + (1 - a) * br);
  const g = Math.round(a * pg + (1 - a) * bg2);
  const b = Math.round(a * pb + (1 - a) * bb);
  const to = (x) => x.toString(16).padStart(2, "0");
  return `#${to(r)}${to(g)}${to(b)}`;
}

// —— M3 Surface Container 五级 tone (固定 tone, 色相/彩度来自 neutral 板) ——
// 亮色: 抬升越高 tone 越低(越灰); 暗色: 抬升越高 tone 越高(越亮)。页面(surface)最浅/最深。
// 抬升层叠加 primary 蒙版(surface tint scrim), 制造「轻重」而保持单强调色。
const SURFACE_TONES = {
  light: { appBg: 98, low: 96, mid: 94, high: 92, highest: 90 },
  dark: { appBg: 6, low: 10, mid: 12, high: 17, highest: 22 },
};
// 各抬升层的 primary 蒙版透明度 (M3 elevation scrim: level1~5 ≈ 5/8/11/12/14%)
const SCRIM = { low: 0.05, mid: 0.08, high: 0.11, highest: 0.14 };

// 全量调色板派生: 品牌角色 + 中性层级 + 状态色, 全部来自 material-color-utilities
// (themeFromSourceColor 的 M3 scheme + TonalPalette)。单一源色即可派生整套,
// 保证双主题 + 任意源色下所有颜色都来自 MCU, 且文字压表面均达 WCAG AA (已审计)。
function derivePalette(sourceHex, isDark) {
  sourceHex = sourceHex || DEFAULT_SOURCE;
  const key = sourceHex.toLowerCase() + (isDark ? ":d" : ":l");
  if (paletteCache[key]) return paletteCache[key];
  const argb = argbFromHex(sourceHex);
  const theme = themeFromSourceColor(argb);
  const s = isDark ? theme.schemes.dark : theme.schemes.light;
  const tp = theme.palettes.primary;            // 官方品牌调色板(M3 primary)
  const neutral = theme.palettes.neutral;        // 官方中性调色板(表面/文字)
  const nv = theme.palettes.neutralVariant;      // 官方中性变体调色板(描边)
  const st = SURFACE_TONES[isDark ? "dark" : "light"];
  const sc = (t) => hexFromArgb(neutral.tone(t));           // 容器 tone 本色
  const primaryHex = hexFromArgb(s.primary);                // 抬升层蒙版色(品牌)
  // —— M3 Surface Container 五级 + 抬升层 primary 蒙版: 制造「轻重」而保持单强调色 ——
  const cLow = sc(st.low), cMid = sc(st.mid), cHigh = sc(st.high), cHighest = sc(st.highest);
  const appBg = sc(st.appBg);
  const bg1 = alphaComposite(primaryHex, cLow, SCRIM.low);         // 导航/侧栏(低抬升)
  const bg2 = alphaComposite(primaryHex, cMid, SCRIM.mid);         // 卡片(中抬升)
  const bg3 = alphaComposite(primaryHex, cHigh, SCRIM.high);       // 输入/hover(高抬升)
  const bg4 = alphaComposite(primaryHex, cHighest, SCRIM.highest); // 弹层/toast(最高抬升)
  const pal = {
    // —— 品牌角色 (M3 primary 系列) ——
    brand: hexFromArgb(s.primary),
    onBrand: hexFromArgb(s.onPrimary),
    surface: hexFromArgb(s.primaryContainer),
    onSurface: hexFromArgb(s.onPrimaryContainer),
    hover: hexFromArgb(tp.tone(isDark ? 76 : 44)),
    pressed: hexFromArgb(tp.tone(isDark ? 84 : 36)),
    tint: hexFromArgb(tp.tone(isDark ? 24 : 90)),   // 薄染(亮=浅洗 / 暗=深色洗)
    weak: hexFromArgb(tp.tone(isDark ? 32 : 88)),
    line: hexFromArgb(tp.tone(isDark ? 48 : 60)),
    // —— 次要色组 (M3 secondary: 低强调度填充, 如 Filter Chip / 分段控件选中态) ——
    secondary: hexFromArgb(s.secondary),
    onSecondary: hexFromArgb(s.onSecondary),
    secondaryContainer: hexFromArgb(s.secondaryContainer),
    onSecondaryContainer: hexFromArgb(s.onSecondaryContainer),
    // —— 三级色组 (M3 tertiary: 视觉差异化点缀, 如特惠/特征/新消息标签) ——
    tertiary: hexFromArgb(s.tertiary),
    onTertiary: hexFromArgb(s.onTertiary),
    tertiaryContainer: hexFromArgb(s.tertiaryContainer),
    onTertiaryContainer: hexFromArgb(s.onTertiaryContainer),
    // —— 中性前景 (官方 neutral / neutralVariant 板; fg3 取 neutralVariant.tone 保证 AA) ——
    fg1: hexFromArgb(s.onSurface),
    fg2: hexFromArgb(s.onSurfaceVariant),
    fg3: hexFromArgb(nv.tone(isDark ? 66 : 40)),  // 三级文字(官方中性变体板, 双主题均达 AA)
    fg4: hexFromArgb(s.outlineVariant),
    fgInverted: hexFromArgb(s.inverseOnSurface),
    // —— 中性背景层级 (M3 Surface Container 五级 + 抬升层 primary 蒙版) ——
    appBg: appBg, bg1: bg1, bg2: bg2, bg3: bg3, bg4: bg4,
    bgInv: hexFromArgb(s.inverseSurface),
    stroke1: hexFromArgb(s.outline),
    stroke2: hexFromArgb(s.outlineVariant),
    stroke3: isDark ? hexFromArgb(nv.tone(40)) : hexFromArgb(nv.tone(90)),
    // —— 品牌染色前景 (纯 M3 TonalPalette, 非 color-mix 灰字) ——
    fgTinted: hexFromArgb(tp.tone(isDark ? 80 : 36)),
    fgTinted2: hexFromArgb(tp.tone(isDark ? 70 : 44)),
    // —— 弹层 / 云母 ——
    popupBg: isDark ? sc(st.high) : sc(st.highest),   // 弹层用高/最高容器 tone
    popupFg: hexFromArgb(s.onSurface),
    mica1: sc(isDark ? st.low : st.appBg),
    mica2: sc(isDark ? st.appBg : st.low),
    // —— 状态色 (M3 error 角色 + 规范源派生 success/warning) ——
    errorFg: hexFromArgb(s.error),
    errorBg: hexFromArgb(s.errorContainer),
  };
  paletteCache[key] = pal;
  return pal;
}

let _paletteCache = "";
function applyPalette(sourceHex, isDark) {
  const key = `${sourceHex}|${isDark}`;
  if (key === _paletteCache) return;   // 颜色/明暗未变则跳过整段 MCU 重算，避免拖动非颜色滑块时重复计算卡顿
  _paletteCache = key;
  const p = derivePalette(sourceHex, isDark);
  const st = statusColors(isDark);
  const root = document.documentElement;
  const set = (k, v) => root.style.setProperty(k, v);
  // 品牌角色
  set("--color-brand", p.brand);
  set("--color-brand-on", p.onBrand);
  set("--color-brand-surface", p.surface);
  set("--color-on-brand-surface", p.onSurface);
  set("--color-brand-hover", p.hover);
  set("--color-brand-pressed", p.pressed);
  set("--color-brand-tint", p.tint);
  set("--color-brand-weak", p.weak);
  set("--color-brand-line", p.line);
  // 次要色组 (secondary)
  set("--color-secondary", p.secondary);
  set("--color-on-secondary", p.onSecondary);
  set("--color-secondary-container", p.secondaryContainer);
  set("--color-on-secondary-container", p.onSecondaryContainer);
  // 三级色组 (tertiary)
  set("--color-tertiary", p.tertiary);
  set("--color-on-tertiary", p.onTertiary);
  set("--color-tertiary-container", p.tertiaryContainer);
  set("--color-on-tertiary-container", p.onTertiaryContainer);
  // 中性前景
  set("--color-fg-1", p.fg1);
  set("--color-fg-2", p.fg2);
  set("--color-fg-3", p.fg3);
  set("--color-fg-4", p.fg4);
  set("--color-fg-inverted", p.fgInverted);
  // 中性背景层级
  set("--color-app-bg", p.appBg);
  set("--color-bg-1", p.bg1);
  set("--color-bg-2", p.bg2);
  set("--color-bg-3", p.bg3);
  set("--color-bg-4", p.bg4);
  set("--color-bg-inverted", p.bgInv);
  // 描边
  set("--color-stroke-1", p.stroke1);
  set("--color-stroke-2", p.stroke2);
  set("--color-stroke-3", p.stroke3);
  // 品牌染色前景
  set("--color-fg-tinted", p.fgTinted);
  set("--color-fg-tinted-2", p.fgTinted2);
  // 弹层 / 云母
  set("--popup-bg", p.popupBg);
  set("--popup-fg", p.popupFg);
  set("--mica-tint-1", p.mica1);
  set("--mica-tint-2", p.mica2);
  // 半透明表面(rgba)由各级容器 tone 派生, 与材质不透明度解耦
  set("--acrylic-rgb", rgbStr(p.bg2));        // 卡片(中抬升)
  set("--acrylic-rgb-low", rgbStr(p.bg1));    // 侧栏/导航(低抬升)
  set("--acrylic-rgb-high", rgbStr(p.bg4));   // toast/弹层(高抬升)
  set("--control-rgb", rgbStr(p.bg3));        // 输入(高抬升)
  // 状态色
  set("--color-success-fg", st.success.fg);
  set("--color-success-bg", st.success.bg);
  set("--color-warning-fg", st.warning.fg);
  set("--color-warning-bg", st.warning.bg);
  set("--color-error-fg", p.errorFg);
  set("--color-error-bg", p.errorBg);
}

// 动态取色: 用 MCU 官方算法从背景图提取主色(替代手写 extractImageAccent / clampAccent)
function applyDynamicAccent(imageSrc) {
  const isDark = currentIsDark();
  const cacheKey = imageSrc.substring(0, 64);
  if (dynamicSourceCache[cacheKey]) {
    applyPalette(dynamicSourceCache[cacheKey], isDark);
    return;
  }
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = async () => {
    try {
      // 缩小到 64x64 再取色，避免处理全分辨率大图卡顿
      const size = 64;
      const cvs = document.createElement("canvas");
      cvs.width = size; cvs.height = size;
      const c = cvs.getContext("2d");
      c.drawImage(img, 0, 0, size, size);
      const small = new Image();
      small.src = cvs.toDataURL("image/png");
      await new Promise((res) => { small.onload = res; });
      const srcArgb = await sourceColorFromImage(small);
      const hex = hexFromArgb(srcArgb);
      dynamicSourceCache[cacheKey] = hex;
      const ui = state.uiConfig;
      if (ui.color_mode === "dynamic" && ui.background_mode === "image") {
        applyPalette(hex, currentIsDark());
        if (ui.background_accent !== hex) {
          ui.background_accent = hex;
          bridge.apiPost("config/save", { ui: state.uiConfig }).catch(() => {});
        }
      }
    } catch (e) {
      console.warn("动态取色失败，使用默认色", e);
    }
  };
  img.onerror = () => console.warn("背景图加载失败，使用默认色");
  img.src = imageSrc.startsWith("data:") ? imageSrc : `./bg?t=${Date.now()}`;
}

// ========== 事件绑定 ==========
function bindEvents() {
  // Tabs
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // Sidebar 收缩/展开（持久化到 localStorage）
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebar-toggle");
  if (sidebar && sidebarToggle) {
    try {
      if (localStorage.getItem("mmtts_sidebar_collapsed") === "1") {
        sidebar.classList.add("collapsed");
      }
    } catch (_) { /* localStorage 不可用时忽略 */ }
    sidebarToggle.addEventListener("click", () => {
      const collapsed = sidebar.classList.toggle("collapsed");
      try {
        localStorage.setItem("mmtts_sidebar_collapsed", collapsed ? "1" : "0");
      } catch (_) { /* ignore */ }
    });
  }

  // 刷新
  document.getElementById("btn-refresh-all").onclick = loadOverview;
  document.getElementById("btn-refresh-logs").onclick = loadLogs;

  // 主题切换：从点击位置生成圆形遮罩外扩，View Transitions 让新旧主题同帧渲染
  const themeBtn = document.getElementById("btn-theme");
  if (themeBtn) {
    themeBtn.addEventListener("click", (e) => {
      const html = document.documentElement;
      const switchTheme = () => {
        html.dataset.theme = html.dataset.theme === "dark" ? "light" : "dark";
        syncThemeIcon();
        applyUiConfig(); // 重新套用动态取色 / 静态色
      };
      // 原点取指针位置；取不到（键盘触发等）时回退到屏幕中心
      const x = e.clientX || window.innerWidth / 2;
      const y = e.clientY || window.innerHeight / 2;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (document.startViewTransition && !reduce) {
        // 计算到最远角的半径，确保圆形遮罩能完整覆盖整个视口
        const r = Math.hypot(
          Math.max(x, window.innerWidth - x),
          Math.max(y, window.innerHeight - y)
        );
        html.style.setProperty("--vt-x", x + "px");
        html.style.setProperty("--vt-y", y + "px");
        html.style.setProperty("--vt-r", r + "px");
        document.startViewTransition(switchTheme);
      } else {
        switchTheme(); // 不支持 View Transitions 或减少动效时直接切换
      }
    });
  }

  // 音色
  document.getElementById("btn-load-voices").onclick = browseVoices;
  document.getElementById("btn-voice-back").onclick = backToMyVoices;
  document.getElementById("voice-filter").oninput = () => _renderBrowseFiltered();
  document.getElementById("btn-voice-search").onclick = voiceSearch;
  document.getElementById("voice-type").onchange = () => _renderBrowseList();
  document.getElementById("voice-show-hidden").onchange = () => renderVoices(state.voices);
  _bindBatchBar();
  document.getElementById("btn-voice-manage").onclick = () => {
    state.voiceManageMode = !state.voiceManageMode;
    document.getElementById("btn-voice-manage").textContent = state.voiceManageMode ? "完成管理" : "管理音色";
    renderVoices(state.voices);
  };

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
      : "点击或拖拽图片到此处（jpg/png/webp/gif，建议 ≤20MB）";
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
  document.getElementById("debug-speed").addEventListener("input", (e) => {
    document.getElementById("debug-speed-val").textContent = parseFloat(e.target.value).toFixed(1);
  });

  // 设置
  document.getElementById("btn-save-ui").onclick = saveUiConfig;
  document.getElementById("btn-reset-ui").onclick = resetUiConfig;
  document.getElementById("btn-save-plugin-cfg").onclick = savePluginConfig;

  // 滑动条数值即时显示（独立于 previewUiConfig，确保拖动时数值始终同步）
  const _sliderPairs = [
    ["ui-material", "ui-material-val", (v) => `${v}%`],
    ["ui-blur", "ui-blur-val", (v) => `${v}px`],
    ["ui-glow", "ui-glow-val", (v) => `${v}%`],
    ["ui-shadow", "ui-shadow-val", (v) => `${v}%`],
    ["ui-scrim", "ui-scrim-val", (v) => `${v}%`],
  ];
  _sliderPairs.forEach(([sliderId, valId, fmt]) => {
    const slider = document.getElementById(sliderId);
    const valEl = document.getElementById(valId);
    if (slider && valEl) {
      slider.addEventListener("input", () => { valEl.textContent = fmt(slider.value); });
    }
  });

  // 颜色选择器与文本框联动
  linkColorPicker("ui-brand-color-picker", "ui-brand-color");
  linkColorPicker("ui-custom-bg-picker", "ui-custom-bg");
  linkColorPicker("ui-custom-bg-dark-picker", "ui-custom-bg-dark");

  // 实时预览
  ["ui-color-mode", "ui-brand-color", "ui-bg-mode", "ui-radius",
   "ui-custom-bg", "ui-custom-bg-dark", "ui-material", "ui-blur", "ui-acrylic-on",
   "ui-material-type", "ui-font", "ui-glow-on", "ui-glow", "ui-shadow-on", "ui-shadow", "ui-scrim", "ui-viz-mode"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", previewUiConfig);
  });
}

function linkColorPicker(pickerId, textId) {
  const picker = document.getElementById(pickerId);
  const text = document.getElementById(textId);
  if (!picker || !text) return;
  // 取色器拖动也要实时触发预览（否则只有文本框直接输入才生效）
  picker.addEventListener("input", () => {
    text.value = picker.value;
    previewUiConfig();
  });
  text.addEventListener("input", () => {
    if (/^#[0-9a-fA-F]{6}$/.test(text.value)) {
      picker.value = text.value;
      previewUiConfig();
    }
  });
}

let _applyRaf = null;
function previewUiConfig() {
  const mat = document.getElementById("ui-material");
  const blur = document.getElementById("ui-blur");
  const ac = document.getElementById("ui-acrylic-on");
  const matVal = document.getElementById("ui-material-val");
  const blurVal = document.getElementById("ui-blur-val");
  const mtEl = document.getElementById("ui-material-type");
  const foEl = document.getElementById("ui-font");
  const goEl = document.getElementById("ui-glow-on");
  const giEl = document.getElementById("ui-glow");
  const goVal = document.getElementById("ui-glow-val");
  const soEl = document.getElementById("ui-shadow-on");
  const siEl = document.getElementById("ui-shadow");
  const soVal = document.getElementById("ui-shadow-val");
  const radiusEl = document.getElementById("ui-radius");
  const radiusVal = document.getElementById("ui-radius-val");
  // 解析: 0 是合法值, 不能用 || 回退(否则拖到最左会跳回默认值)
  let matV = parseInt(mat ? mat.value : "", 10); if (Number.isNaN(matV)) matV = 45;
  let blurV = parseInt(blur ? blur.value : "", 10); if (Number.isNaN(blurV)) blurV = 5;
  let radiusV = parseInt(radiusEl ? radiusEl.value : "", 10); if (Number.isNaN(radiusV)) radiusV = 14;
  if (matVal) matVal.textContent = `${matV}%`;
  if (blurVal) blurVal.textContent = `${blurV}px`;
  if (radiusVal) radiusVal.textContent = `${radiusV}px`;   // 圆角数值实时显示（修复：原缺 -val span）
  if (goVal) goVal.textContent = `${giEl ? giEl.value : 15}%`;
  if (soVal) soVal.textContent = `${siEl ? siEl.value : 50}%`;
  state.uiConfig = {
    color_mode: document.getElementById("ui-color-mode").value,
    brand_color: document.getElementById("ui-brand-color").value,
    background_mode: document.getElementById("ui-bg-mode").value,
    custom_background: document.getElementById("ui-custom-bg").value,
    custom_background_dark: document.getElementById("ui-custom-bg-dark").value,
    background_image: state.uiConfig.background_image || "",
    corner_radius: radiusV,
    acrylic_enabled: ac ? ac.checked : true,
    material_opacity: matV,
    material_blur: blurV,
    material_type: mtEl ? mtEl.value : "acrylic",
    font_mode: foEl ? foEl.value : "misans",
    glow_enabled: goEl ? goEl.checked : false,
    glow_intensity: giEl ? (parseInt(giEl.value, 10) || 0) : 15,
    shadow_enabled: soEl ? soEl.checked : false,
    shadow_intensity: siEl ? (parseInt(siEl.value, 10) || 0) : 60,
    bg_scrim: (() => { const s = document.getElementById("ui-scrim"); return s ? (parseInt(s.value, 10) || 0) : 40; })(),
    viz_mode: document.getElementById("ui-viz-mode")?.value || "spectrum",
  };
  // 数值即时更新；重计算（含 MCU 调色板推导）用 rAF 合并到下一帧，拖动顺滑、首帧不再卡
  if (_applyRaf) cancelAnimationFrame(_applyRaf);
  _applyRaf = requestAnimationFrame(() => { _applyRaf = null; applyUiConfig(); });
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
  if (name === "voices") renderVoices(state.voices);
  if (["settings", "synth", "send", "ai", "advanced"].includes(name)) loadPluginConfig();
  // 切到含声纹画布的视图变为可见后, 重新测量画布尺寸, 消除过期 backing store 造成的锯齿/细线
  try { Waveform.refresh(); } catch (_) {}
}

// ========== 状态总览 ==========
async function loadOverview() {
  try {
    const stats = await bridge.apiGet("stats");
    const apiBadge = document.getElementById("api-status-badge");
    if (stats.api_ok) {
      apiBadge.className = "badge badge-brand";
      apiBadge.textContent = "API 正常";
    } else {
      apiBadge.className = "badge badge-danger";
      apiBadge.textContent = "API 异常";
    }
    document.getElementById("stat-api").innerHTML = stats.api_ok
      ? '<span class="badge badge-brand">正常</span>'
      : '<span class="badge badge-danger">异常</span>';
    document.getElementById("stat-today").textContent = stats.today_count || 0;
    document.getElementById("stat-cache").textContent =
      `${(stats.cache_size_mb || 0).toFixed(1)} MB`;
    document.getElementById("stat-ffmpeg").innerHTML = stats.ffmpeg_available
      ? '<span class="badge badge-brand">可用</span>'
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
  // 仅填充调试合成下拉，不影响用户音色列表
  try {
    const data = await bridge.apiGet("voices");
    const all = data.voices || [];
    _fillDebugSelect(all);
  } catch (_) {
    try {
      const data = await bridge.apiGet("voices/static");
      _fillDebugSelect(data.voices || []);
    } catch (__) {}
  }
}

function _fillDebugSelect(all) {
  const sel = document.getElementById("debug-voice");
  if (!sel) return;
  const cur = sel.value;
  // 合并用户列表 + 全部音色（去重），确保调试下拉能选到所有
  const merged = [...state.voices];
  all.forEach((v) => { if (!merged.some((x) => x.voice_id === v.voice_id)) merged.push(v); });
  sel.innerHTML = merged
    .map((v) => `<option value="${v.voice_id}">${v.name || v.voice_id} (${v.voice_id})</option>`)
    .join("");
  if (cur && merged.some((v) => v.voice_id === cur)) sel.value = cur;
}

function addToMyVoices(voice) {
  if (state.voices.some((v) => v.voice_id === voice.voice_id)) {
    showToast("该音色已在列表中", "info");
    return;
  }
  state.voices.push(voice);
  _persistVoices();
  fillDebugVoiceSelect();
  if (!state.voiceBrowseMode) renderVoices(state.voices);
  showToast(`已添加: ${voice.name || voice.voice_id}`, "success");
}

async function browseVoices() {
  state.voiceBrowseMode = true;
  document.getElementById("voice-toolbar-mine").style.display = "none";
  document.getElementById("voice-toolbar-browse").style.display = "";
  document.getElementById("voice-mode-hint").textContent = "官方音色库（点击 + 添加）";
  document.getElementById("voice-batch-bar").style.display = "none";
  await _renderBrowseList();
}

function backToMyVoices() {
  state.voiceBrowseMode = false;
  document.getElementById("voice-toolbar-browse").style.display = "none";
  document.getElementById("voice-toolbar-mine").style.display = "";
  document.getElementById("voice-mode-hint").textContent = "我的音色列表";
  document.getElementById("voice-filter").value = "";
  renderVoices(state.voices);
}

async function _renderBrowseList() {
  const listEl = document.getElementById("voice-list");
  listEl.innerHTML = '<div class="skeleton" style="height:60px"></div>';
  try {
    const voiceType = document.getElementById("voice-type").value;
    const data = await bridge.apiGet("voices");
    let voices = data.voices || [];
    if (voiceType !== "all") voices = voices.filter((v) => (v.type || "") === voiceType);
    state._browseVoices = voices;
    _renderBrowseFiltered();
  } catch (e) {
    listEl.innerHTML = `<div class="empty-state"><p>加载失败: ${e.message}</p></div>`;
  }
}

function _renderBrowseFiltered() {
  const listEl = document.getElementById("voice-list");
  const filter = (document.getElementById("voice-filter").value || "").toLowerCase();
  const voices = (state._browseVoices || []).filter((v) =>
    !filter || (v.name || "").toLowerCase().includes(filter) || (v.voice_id || "").toLowerCase().includes(filter)
  );
  if (voices.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><p>无匹配音色</p></div>';
    return;
  }
  const _ico = (d, s = 16) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="currentColor" style="vertical-align:-2px"><path d="${d}"/></svg>`;
  const ICO_ADD = "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z";
  const ICO_PLAY = "M8 5v14l11-7z";
  listEl.innerHTML = voices.map((v) => {
    const inList = state.voices.some((x) => x.voice_id === v.voice_id);
    return `<div class="stat-card">
      <div class="flex-between">
        <div style="overflow:hidden">
          <div class="text-bold truncate">${v.name || "未命名"}</div>
          <div class="text-mono text-sm text-muted truncate">${v.voice_id}</div>
        </div>
        <div class="flex gap-s">
          <button class="btn btn-subtle btn-sm" data-bplay="${v.voice_id}" data-bname="${v.name || ""}" title="试听">${_ico(ICO_PLAY)}</button>
          <button class="btn btn-subtle btn-sm" data-badd="${v.voice_id}" ${inList ? "disabled" : ""} title="添加">${inList ? "✓" : _ico(ICO_ADD)}</button>
        </div>
      </div>
    </div>`;
  }).join("");
  listEl.querySelectorAll("button[data-bplay]").forEach((btn) => {
    btn.onclick = () => previewVoice(btn.dataset.bplay, btn.dataset.bname);
  });
  listEl.querySelectorAll("button[data-badd]").forEach((btn) => {
    btn.onclick = () => {
      const v = (state._browseVoices || []).find((x) => x.voice_id === btn.dataset.badd);
      if (v) addToMyVoices(v);
      btn.disabled = true;
      btn.textContent = "✓";
    };
  });
}

function voiceSearch() {
  const q = (document.getElementById("voice-filter").value || "").trim();
  const matches = (state._browseVoices || []).filter((v) =>
    (v.name || "").toLowerCase().includes(q.toLowerCase()) || (v.voice_id || "").toLowerCase().includes(q.toLowerCase())
  );
  if (matches.length > 0 || !q) {
    _renderBrowseFiltered();
    return;
  }
  // 无匹配，尝试按 ID 查询添加
  bridge.apiGet("voice/get", { voice_id: q }).then((data) => {
    const label = (data.voice && (data.voice.name || data.voice.voice_id)) || q;
    addToMyVoices({ voice_id: q, name: label, type: data.voice?.type || "voice_cloning" });
    document.getElementById("voice-filter").value = "";
    _renderBrowseFiltered();
  }).catch(() => {
    addToMyVoices({ voice_id: q, name: q, type: "voice_cloning" });
    document.getElementById("voice-filter").value = "";
    _renderBrowseFiltered();
  });
}

function renderVoices(voices) {
  const showHidden = document.getElementById("voice-show-hidden")?.checked;
  const manage = state.voiceManageMode;
  const filtered = voices.filter(
    (v) => (showHidden || !state.hiddenVoices.has(v.voice_id)),
  );
  const listEl = document.getElementById("voice-list");
  const batchBar = document.getElementById("voice-batch-bar");
  if (batchBar) batchBar.style.display = (manage && voices.length) ? "" : "none";
  if (filtered.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><p>无匹配音色</p></div>';
    return;
  }
  const _ico = (d, size = 16) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="currentColor" style="vertical-align:-2px"><path d="${d}"/></svg>`;
  const ICO_PLAY = "M8 5v14l11-7z";
  const ICO_EDIT = "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z";
  const ICO_STAR = "M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z";
  const ICO_HIDE = "M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z";
  const ICO_SHOW = "M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z";
  listEl.innerHTML = filtered
    .map(
      (v) => `
    <div class="stat-card" style="${state.hiddenVoices.has(v.voice_id) ? 'opacity:0.5' : ''}">
      <div class="flex-between">
        <div style="display:flex;align-items:center;gap:8px;overflow:hidden">
          ${manage ? `<input type="checkbox" class="voice-chk" value="${v.voice_id}" style="width:16px;height:16px;accent-color:var(--color-brand);flex-shrink:0" />` : ""}
          <div style="overflow:hidden">
            <div class="text-bold truncate">${v.name || "未命名"}</div>
            <div class="text-mono text-sm text-muted truncate">${v.voice_id || ""}</div>
          </div>
        </div>
        <div class="flex gap-s">
          <button class="btn btn-subtle btn-sm" data-voice="${v.voice_id}" data-name="${v.name || ""}" title="试听">${_ico(ICO_PLAY)}</button>
          <button class="btn btn-subtle btn-sm" data-default="${v.voice_id}" data-name="${v.name || ""}" title="设为默认">${_ico(ICO_STAR)}</button>
          <button class="btn btn-subtle btn-sm" data-rename="${v.voice_id}" title="重命名">${_ico(ICO_EDIT)}</button>
          ${manage ? `<button class="btn btn-subtle btn-sm" data-hide="${v.voice_id}" title="${state.hiddenVoices.has(v.voice_id) ? '取消隐藏' : '隐藏'}">${_ico(state.hiddenVoices.has(v.voice_id) ? ICO_SHOW : ICO_HIDE)}</button>` : ""}
        </div>
      </div>
    </div>
  `,
    )
    .join("");
  listEl.querySelectorAll("button[data-voice]").forEach((btn) => {
    btn.onclick = () => previewVoice(btn.dataset.voice, btn.dataset.name);
  });
  listEl.querySelectorAll("button[data-default]").forEach((btn) => {
    btn.onclick = () => setDefaultVoice(btn.dataset.default, btn.dataset.name);
  });
  listEl.querySelectorAll("button[data-hide]").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.dataset.hide;
      if (state.hiddenVoices.has(id)) state.hiddenVoices.delete(id);
      else state.hiddenVoices.add(id);
      _persistVoices();
      renderVoices(state.voices);
    };
  });
  listEl.querySelectorAll("button[data-rename]").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.dataset.rename;
      const v = state.voices.find((x) => x.voice_id === id);
      if (!v) return;
      const card = btn.closest(".stat-card");
      const nameEl = card.querySelector(".text-bold");
      if (!nameEl || nameEl.querySelector("input")) return;
      const old = v.name || "";
      nameEl.innerHTML = `<input class="input" style="padding:2px 6px;font-size:inherit;font-weight:inherit;width:100%" value="${old.replace(/"/g, "&quot;")}" />`;
      const inp = nameEl.querySelector("input");
      inp.focus();
      inp.select();
      const commit = () => {
        const nv = inp.value.trim();
        if (nv && nv !== old) {
          v.name = nv;
          _persistVoices();
          fillDebugVoiceSelect();
          showToast(`已重命名为: ${nv}`, "success");
        }
        renderVoices(state.voices);
      };
      inp.onkeydown = (e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") renderVoices(state.voices); };
      inp.onblur = commit;
    };
  });
}

function _getCheckedVoiceIds() {
  return [...document.querySelectorAll(".voice-chk:checked")].map((c) => c.value);
}
function _bindBatchBar() {
  const bar = document.getElementById("voice-batch-bar");
  if (!bar || bar._bound) return;
  bar._bound = true;
  document.getElementById("btn-voice-select-all").onclick = () => {
    document.querySelectorAll(".voice-chk").forEach((c) => { c.checked = true; });
  };
  document.getElementById("btn-voice-deselect").onclick = () => {
    document.querySelectorAll(".voice-chk").forEach((c) => { c.checked = false; });
  };
  document.getElementById("btn-voice-batch-hide").onclick = () => {
    _getCheckedVoiceIds().forEach((id) => state.hiddenVoices.add(id));
    _persistVoices();
    renderVoices(state.voices);
    showToast("已批量隐藏", "success");
  };
  document.getElementById("btn-voice-batch-show").onclick = () => {
    _getCheckedVoiceIds().forEach((id) => state.hiddenVoices.delete(id));
    _persistVoices();
    renderVoices(state.voices);
    showToast("已批量取消隐藏", "success");
  };
}

function fillDebugVoiceSelect() {
  const sel = document.getElementById("debug-voice");
  const cur = sel.value;
  const visible = state.voices.filter((v) => !state.hiddenVoices.has(v.voice_id));
  sel.innerHTML = visible
    .map(
      (v) =>
        `<option value="${v.voice_id}">${v.name} (${v.voice_id})</option>`,
    )
    .join("");
  if (cur && visible.some((v) => v.voice_id === cur)) {
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
    const blobUrl = base64ToBlobUrl(result.audio_base64, "audio/wav");
    playAudio(blobUrl || result.audio_path, `试听: ${name || voiceId}`, !!blobUrl);
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
      const cloneAudioSrc = base64ToBlobUrl(cloneResp.audio_base64, cloneResp.audio_mime || "audio/mpeg")
        || (cloneResp.audio_path ? `./audio?path=${encodeURIComponent(cloneResp.audio_path)}` : "");
      if (cloneAudioSrc) {
        audioHtml = `<div class="audio-player mt-s">
          <audio controls preload="metadata" src="${cloneAudioSrc}"></audio>
        </div>`;
      }
      resultEl.innerHTML = `
        <span class="badge badge-brand">克隆成功</span>
        <p class="text-sm text-muted mt-s">音色 ID: <code>${voiceId}</code></p>
        ${audioHtml}
      `;
      // 接入波形
      const cloneAudio = resultEl.querySelector('audio');
      if (cloneAudio) Waveform.attachAudio(cloneAudio);
      showToast("语音克隆成功！", "success");
      // 刷新音色列表与调试下拉，让新克隆音色立即可选
      loadStaticVoices();
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
    const inLocalList = state.voices.some((v) => v.voice_id === voiceId);
    const typeBadge = inLocalList
      ? '<span class="badge badge-brand">已在列表中</span>'
      : data.found
        ? (data.voice.type === "system"
            ? '<span class="badge badge-info">系统音色</span>'
            : '<span class="badge badge-brand">克隆音色</span>')
        : '<span class="badge badge-warning">未在列表中</span>';
    const note = (data.found || inLocalList)
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
          <button class="btn btn-subtle btn-sm" id="btn-add-to-list" ${inLocalList ? "disabled" : ""}>${inLocalList ? "✓ 已在列表" : "＋ 加入列表"}</button>
          <button class="btn btn-primary btn-sm" id="btn-set-default">设为默认音色</button>
        </div>
      </div>`;
    document.getElementById("btn-preview-loaded").onclick = () =>
      previewVoice(voiceId, label);
    document.getElementById("btn-add-to-list").onclick = () => {
      if (!state.voices.some((v) => v.voice_id === voiceId)) {
        state.voices.push({ voice_id: voiceId, name: label, type: data.voice?.type || "voice_cloning" });
        fillDebugVoiceSelect();
        renderVoices(state.voices);
        showToast(`已加入列表: ${label}`, "success");
      } else {
        showToast("该音色已在列表中", "info");
      }
    };
    document.getElementById("btn-set-default").onclick = () =>
      setDefaultVoice(voiceId, label);
    showToast(inLocalList ? "该音色已在列表中" : data.found ? "已找到该音色" : "未在列表中找到，仍可试听", inLocalList ? "info" : data.found ? "success" : "info");
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
  if (file.size > 20 * 1024 * 1024) {
    showToast("图片不能超过 20MB", "warning");
    return;
  }
  const btn = document.getElementById("btn-bg-upload");
  btn.disabled = true;
  btn.textContent = "上传中...";
  try {
    const resp = await bridge.upload("bg/upload", file);
    console.log("[bg/upload] resp:", JSON.stringify(resp).substring(0, 200));
    // bridge.upload 返回格式不固定，兼容多种结构
    const dataUri = resp.data || (resp.body && resp.body.data) || (typeof resp === "string" && resp.startsWith("data:") ? resp : "");
    if (!dataUri) throw new Error("上传响应中未找到背景图数据");
    state.uiConfig.background_image = dataUri;
    state.uiConfig.background_accent = "";
    state.uiConfig.background_mode = "image";
    document.getElementById("bg-file-name").textContent = (resp && resp.filename) || file.name;
    document.getElementById("ui-bg-mode").value = "image";
    updateBgPreview();
    // 直接应用背景（不依赖 previewUiConfig 重建 state 的时序）
    const body = document.body;
    body.classList.remove("bg-mode-brand-gradient", "bg-mode-custom");
    const bgLayer = document.getElementById("bg-layer");
    if (bgLayer) bgLayer.style.backgroundImage = `url('${dataUri}')`;
    const appEl = document.getElementById("app");
    if (appEl) appEl.classList.add("bg-image-active");
    // 立即触发动态取色
    if (state.uiConfig.color_mode === "dynamic") {
      applyDynamicAccent(dataUri);
    }
    // 持久化
    bridge.apiPost("config/save", { ui: state.uiConfig }).catch(() => {});
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
    state.uiConfig.background_accent = "";
    document.getElementById("bg-file-name").textContent =
      "点击或拖拽图片到此处（jpg/png/webp/gif，建议 ≤20MB）";
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
    img.src = ui.background_image.startsWith("data:")
      ? ui.background_image
      : `./bg?t=${Date.now()}`;
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
    const audioSrc = base64ToBlobUrl(result.audio_base64, "audio/wav")
      || `./audio?path=${encodeURIComponent(result.audio_path)}`;
    resultEl.innerHTML = `
      <div class="audio-player">
        <audio controls preload="metadata" src="${audioSrc}"></audio>
      </div>
      <p class="text-sm text-muted mt-s">
        耗时 ${result.elapsed_ms}ms · 字符 ${result.usage_chars}
      </p>
    `;
    const dbgAudio = resultEl.querySelector('audio');
    if (dbgAudio) {
      dbgAudio.addEventListener('error', () => {
        showToast('音频加载失败：可能是缓存目录未配置被服务端拦截（403），请检查插件设置后刷新重试', 'error');
      });
      Waveform.attachAudio(dbgAudio);
    }
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
          <td>${l.cached ? '<span class="badge badge-brand">命中</span>' : '<span class="badge badge-neutral">合成</span>'}</td>
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
    brand_color: "#ff8ab9",
    background_mode: "theme",
    custom_background: "#F5F6F8",
    custom_background_dark: "#0C0E13",
    background_image: "",
    background_accent: "",
    corner_radius: 14,
    acrylic_enabled: true,
    material_opacity: 45,
    material_blur: 5,
    material_type: "acrylic",
    font_mode: "misans",
    glow_enabled: true,
    glow_intensity: 40,
    shadow_enabled: true,
    shadow_intensity: 60,
    viz_mode: "spectrum",
  };
  applyUiConfig();
  showToast("已恢复默认（需点击保存生效）", "info");
}

// ========== 插件配置（TTS / 音频 / 发送 / 高级）==========
async function loadPluginConfig() {
  try {
    const cfg = await bridge.apiGet("config/full");
    const tts = cfg.tts || {};
    const audio = cfg.audio || {};
    const sm = cfg.send_mode || {};
    const adv = cfg.advanced || {};
    const vm = cfg.voice_modify || {};
    const tp = cfg.text_processing || {};
    const pl = cfg.polish || {};
    const emo = cfg.auto_emotion || {};
    const pd = cfg.pronunciation_dict || {};
    const set = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    // API
    set("cfg-api-key", cfg.api_key || "");
    set("cfg-group-id", cfg.group_id || "");
    set("cfg-api-region", cfg.api_region || "china");
    // TTS
    set("cfg-tts-model", tts.model || "speech-2.8-hd");
    set("cfg-tts-voice-id", tts.voice_id || "female-shaonv");
    set("cfg-tts-speed", tts.speed ?? 1.0);
    set("cfg-tts-vol", tts.vol ?? 1.0);
    set("cfg-tts-pitch", tts.pitch ?? 0);
    set("cfg-tts-emotion", tts.emotion || "");
    set("cfg-tts-lang", tts.language_boost || "auto");
    setChk("cfg-tts-latex", !!tts.latex_read);
    setChk("cfg-tts-normalize", !!tts.text_normalization);
    // Audio
    set("cfg-audio-format", audio.format || "mp3");
    set("cfg-audio-rate", String(audio.sample_rate || 32000));
    set("cfg-audio-bitrate", String(audio.bitrate || 128000));
    set("cfg-audio-channel", String(audio.channel || 1));
    // Send mode
    set("cfg-send-mode", sm.mode || "intercept");
    set("cfg-send-scope", sm.trigger_scope || "all");
    setChk("cfg-send-keep-text", sm.keep_text !== false);
    setChk("cfg-send-sync", sm.use_sync !== false);
    set("cfg-send-min", sm.min_length ?? 1);
    set("cfg-send-max", sm.max_length ?? 5000);
    // Advanced
    set("cfg-adv-timeout", adv.request_timeout ?? 60);
    set("cfg-adv-retry", adv.retry_times ?? 2);
    set("cfg-adv-cache-mb", adv.cache_max_size_mb ?? 500);
    set("cfg-adv-log", adv.log_level || "INFO");
    // Voice modify
    setChk("cfg-vm-on", !!vm.enabled);
    set("cfg-vm-fx", vm.sound_effects || "");
    set("cfg-vm-pitch", vm.pitch ?? 0);
    set("cfg-vm-intensity", vm.intensity ?? 0);
    set("cfg-vm-timbre", vm.timbre ?? 0);
    // Text processing
    setChk("cfg-tp-markdown", tp.markdown_filter !== false);
    setChk("cfg-tp-emoji", tp.emoji_filter !== false);
    setChk("cfg-tp-url", tp.url_filter !== false);
    setChk("cfg-tp-ws", tp.normalize_whitespace !== false);
    // Polish
    setChk("cfg-polish-on", !!pl.enabled);
    setChk("cfg-polish-fallback", pl.fallback_on_error !== false);
    set("cfg-polish-tokens", pl.max_tokens ?? 2048);
    set("cfg-polish-timeout", pl.timeout ?? 15);
    // Auto emotion
    setChk("cfg-emo-on", !!emo.enabled);
    setChk("cfg-emo-fallback", emo.fallback_on_error !== false);
    set("cfg-emo-default", emo.default_emotion || "");
    set("cfg-emo-timeout", emo.timeout ?? 10);
    // Pronunciation dict
    setChk("cfg-pd-on", !!pd.enabled);
    const entries = (pd.tone || []).map(t => t.entry || "").filter(Boolean).join("\n");
    set("cfg-pd-entries", entries);
  } catch (e) {
    console.warn("加载插件配置失败", e);
  }
}

async function savePluginConfig() {
  const val = (id) => document.getElementById(id)?.value;
  const num = (id, fallback) => { const v = parseFloat(val(id)); return Number.isNaN(v) ? fallback : v; };
  const int = (id, fallback) => { const v = parseInt(val(id), 10); return Number.isNaN(v) ? fallback : v; };
  const chk = (id) => document.getElementById(id)?.checked ?? false;
  const pdText = val("cfg-pd-entries") || "";
  const pdEntries = pdText.split("\n").map(s => s.trim()).filter(Boolean).map(entry => ({ entry }));
  const payload = {
    api_key: val("cfg-api-key"),
    group_id: val("cfg-group-id"),
    api_region: val("cfg-api-region"),
    tts: {
      model: val("cfg-tts-model"),
      voice_id: val("cfg-tts-voice-id"),
      speed: num("cfg-tts-speed", 1.0),
      vol: num("cfg-tts-vol", 1.0),
      pitch: int("cfg-tts-pitch", 0),
      emotion: val("cfg-tts-emotion"),
      language_boost: val("cfg-tts-lang"),
      latex_read: chk("cfg-tts-latex"),
      text_normalization: chk("cfg-tts-normalize"),
    },
    audio: {
      format: val("cfg-audio-format"),
      sample_rate: int("cfg-audio-rate", 32000),
      bitrate: int("cfg-audio-bitrate", 128000),
      channel: int("cfg-audio-channel", 1),
    },
    send_mode: {
      mode: val("cfg-send-mode"),
      trigger_scope: val("cfg-send-scope"),
      keep_text: chk("cfg-send-keep-text"),
      use_sync: chk("cfg-send-sync"),
      min_length: int("cfg-send-min", 1),
      max_length: int("cfg-send-max", 5000),
    },
    advanced: {
      request_timeout: int("cfg-adv-timeout", 60),
      retry_times: int("cfg-adv-retry", 2),
      cache_max_size_mb: int("cfg-adv-cache-mb", 500),
      log_level: val("cfg-adv-log"),
    },
    voice_modify: {
      enabled: chk("cfg-vm-on"),
      sound_effects: val("cfg-vm-fx"),
      pitch: int("cfg-vm-pitch", 0),
      intensity: int("cfg-vm-intensity", 0),
      timbre: int("cfg-vm-timbre", 0),
    },
    text_processing: {
      markdown_filter: chk("cfg-tp-markdown"),
      emoji_filter: chk("cfg-tp-emoji"),
      url_filter: chk("cfg-tp-url"),
      normalize_whitespace: chk("cfg-tp-ws"),
    },
    polish: {
      enabled: chk("cfg-polish-on"),
      fallback_on_error: chk("cfg-polish-fallback"),
      max_tokens: int("cfg-polish-tokens", 2048),
      timeout: int("cfg-polish-timeout", 15),
    },
    auto_emotion: {
      enabled: chk("cfg-emo-on"),
      fallback_on_error: chk("cfg-emo-fallback"),
      default_emotion: val("cfg-emo-default"),
      timeout: num("cfg-emo-timeout", 10),
    },
    pronunciation_dict: {
      enabled: chk("cfg-pd-on"),
      tone: pdEntries,
    },
  };
  try {
    await bridge.apiPost("config/save", payload);
    showToast("插件配置已保存", "success");
  } catch (e) {
    showToast(`保存失败: ${e.message}`, "error");
  }
}

/** 将后端返回的 base64 音频转为 Blob URL（绕开插件页相对路径路由问题） */
function base64ToBlobUrl(b64, mime) {
  if (!b64) return "";
  try {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], { type: mime || "audio/wav" });
    return URL.createObjectURL(blob);
  } catch (_) { return ""; }
}

// ========== 工具 ==========
function playAudio(path, label, isBlobUrl) {
  const container = document.createElement("div");
  container.className = "toast";
  container.style.cssText = "min-width:320px;padding:12px";
  const src = isBlobUrl ? path : `./audio?path=${encodeURIComponent(path)}`;
  container.innerHTML = `
    <div class="text-sm text-bold mb-s">${label || "试听"}</div>
    <audio controls autoplay preload="metadata" src="${src}" style="width:100%"></audio>
  `;
  // 接入波形可视化器（同源 ./audio 可用 WebAudio 分析）
  const audioEl = container.querySelector('audio');
  if (audioEl) {
    audioEl.addEventListener('error', () => {
      showToast('音频加载失败，无法播放', 'error');
    });
    Waveform.attachAudio(audioEl);
  }
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

// ========== 实时波形可视化器（签名元素）==========
const Waveform = (() => {
  let canvas, ctx, w, h;
  let raf = null;
  let audioCtx = null, analyser = null, sourceNode = null;
  let idlePhase = 0;
  let energy = 1;          // 音频能量（1=空闲，>1=有信号）
  let audioMix = 0;        // 0=空闲形态, 1=音频驱动形态（平滑过渡）
  let vizMode = "spectrum"; // "spectrum" | "wave"

  function setVizMode(mode) { vizMode = mode; }

  /** 读取品牌色（--color-brand），失败回退信号粉 */
  function brandRGB() {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue('--color-brand').trim() || '#ff8ab9';
    const m = v.match(/^#?([0-9a-f]{6})$/i);
    if (!m) return [236, 72, 153];
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgba(c, a) { return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
  function lighten(c, amt) {
    return [
      Math.round(c[0] + (255 - c[0]) * amt),
      Math.round(c[1] + (255 - c[1]) * amt),
      Math.round(c[2] + (255 - c[2]) * amt),
    ];
  }

  function init() {
    canvas = document.getElementById('waveform-canvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    requestAnimationFrame(() => resize());
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => resize());
      ro.observe(canvas);
    }
    window.addEventListener('resize', resize);
    loop();
  }

  function refresh() {
    if (canvas) resize();
  }

  function resize() {
    let cw = canvas.clientWidth, ch = canvas.clientHeight;
    if (cw < 2 || ch < 2) { const r = canvas.getBoundingClientRect(); cw = r.width; ch = r.height; }
    if (cw < 2 || ch < 2) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = cw; h = ch;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
  }

  /** 将 HTMLAudioElement 接入 WebAudio 分析（同源 ./audio 可用） */
  function attachAudio(audioEl) {
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
      }
      if (audioCtx.state === "suspended") {
        audioCtx.resume().then(() => audioEl.play().catch(() => {})).catch(() => {});
      } else {
        audioEl.play().catch(() => {});
      }
      if (sourceNode) { try { sourceNode.disconnect(); } catch (_) {} }
      sourceNode = audioCtx.createMediaElementSource(audioEl);
      sourceNode.connect(analyser);
      analyser.connect(audioCtx.destination);
    } catch (e) {
      console.warn('[Waveform] AudioContext attach failed:', e.message);
    }
  }

  function loop() {
    raf = requestAnimationFrame(loop);
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    const C = brandRGB();
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    ctx.shadowBlur = 0;

    const binCount = analyser ? analyser.frequencyBinCount : 128;
    const freqData = new Uint8Array(binCount);
    if (analyser) analyser.getByteFrequencyData(freqData);

    const hasSignal = freqData.some(v => v > 12);

    // 平滑跟踪音频能量和形态混合
    let target = 1;
    if (hasSignal) {
      let sum = 0;
      for (let i = 0; i < freqData.length; i++) sum += freqData[i];
      target = 1 + (sum / freqData.length / 255) * 2.5;
    }
    energy += (target - energy) * 0.08;

    if (vizMode === "wave") {
      // 流动波形模式：上升快(指数)，下降匀速10秒
      if (hasSignal) {
        audioMix += (1 - audioMix) * 0.035;
      } else {
        audioMix -= 1 / 600;  // 匀速，60fps下恰好10秒归零
        if (audioMix < 0) audioMix = 0;
      }
      drawWave(freqData, C, dark);
    } else {
      // 频谱模式：有信号画柱状图，否则画空闲流动线
      audioMix = 0;
      hasSignal ? drawSpectrum(freqData, C, dark) : drawWave(freqData, C, dark);
    }
  }

  /* ── 频谱柱状图（有音频播放时）── */
  function drawSpectrum(data, C, dark) {
    const n = data.length;
    const barW = Math.max(1.5, w / n * 0.65);
    const gap = w / n - barW;
    if (dark) { ctx.shadowColor = rgba(C, 0.90); ctx.shadowBlur = 16; }
    else { ctx.shadowColor = rgba(C, 0.45); ctx.shadowBlur = 6; }

    for (let i = 0; i < n; i++) {
      const x = i * (barW + gap);
      const barH = (data[i] / 255) * h * 0.72;
      const y = h - barH;
      const grad = ctx.createLinearGradient(x, y, x, h);
      grad.addColorStop(0, rgba(C, dark ? 1 : 0.95));
      grad.addColorStop(1, rgba(C, 0.12));
      ctx.fillStyle = grad;
      ctx.fillRect(x, y, barW, barH);
    }
    ctx.shadowBlur = 0;
  }

  /* ── 流动波形（空闲态 ↔ 音频驱动态平滑过渡）── */
  function drawWave(freqData, C, dark) {
    const lineC = dark ? lighten(C, 0.35) : C;
    idlePhase += 0.008 * (1 + audioMix * 2);
    const cy = h / 2;
    const lines = 22;
    const mix = audioMix;

    if (dark) { ctx.shadowColor = rgba(lineC, 0.80); ctx.shadowBlur = 10 + mix * 8; }
    else { ctx.shadowColor = rgba(lineC, 0.35); ctx.shadowBlur = 4 + mix * 4; }

    for (let li = 0; li < lines; li++) {
      const off = li / lines - 0.5;
      const baseY = cy + off * (h * 0.72);

      // 基础振幅（空闲态），播放时压缩为音频腾出空间
      const idleAmp = (14 + (li % 7)) * (1 - Math.abs(off) * 1.4) * (1 - mix * 0.8);
      // 音频驱动：从频谱取对应 bin 的能量，映射为额外振幅
      const binIdx = Math.min(freqData.length - 1, Math.floor((li / lines) * freqData.length));
      const binVal = freqData[binIdx] / 255;
      // 混合振幅：空闲压缩保底 + 音频叠加
      const amp = idleAmp + mix * binVal * h * 0.22 * (1 - Math.abs(off) * 0.6);

      const freq = 0.007 + li * 0.00055;
      const alpha = (dark ? 0.18 : 0.16) + (1 - Math.abs(off)) * (dark ? 0.42 : 0.32) + mix * binVal * 0.2;

      ctx.beginPath();
      ctx.strokeStyle = rgba(lineC, Math.min(1, alpha));
      ctx.lineWidth = 1 + mix * binVal * 0.8;
      for (let x = 0; x <= w; x += 3) {
        // 始终使用同一组正弦叠加，保持视觉语言一致
        const n = Math.sin(freq * x + idlePhase + li * 0.75)
                + 0.33 * Math.sin(freq * 2.4 * x + idlePhase * 1.35 + li * 1.15);
        const y = Math.max(1, Math.min(h - 1, baseY + amp * n));
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // 中央主波
    ctx.shadowColor = rgba(lineC, dark ? 0.90 : 0.45);
    ctx.shadowBlur = dark ? 20 : 6;
    ctx.beginPath();
    ctx.strokeStyle = rgba(lineC, dark ? 1.0 : 0.70);
    const mainBin = Math.floor(freqData.length * 0.25);
    const mainVal = freqData[mainBin] / 255;
    ctx.lineWidth = 2 + mix * mainVal * 1.5;
    const mainAmp = h * 0.2 * (1 - mix * 0.8) + mix * mainVal * h * 0.2;
    for (let x = 0; x <= w; x += 2) {
      const n = Math.sin(0.0105 * x + idlePhase * 0.58)
              + 0.30 * Math.sin(0.026 * x + idlePhase * 1.08)
              + 0.15 * Math.sin(0.052 * x + idlePhase * 1.85);
      const y = Math.max(1, Math.min(h - 1, cy + mainAmp * n));
      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  return { init, attachAudio, refresh, setVizMode };
})();

// 暴露给 HTML inline onclick（ES module 不自动挂全局）
window.savePluginConfig = savePluginConfig;

// 启动
init();
