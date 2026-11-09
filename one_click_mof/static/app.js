'use strict';

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const state = {
  settings: {}, manifests: [], projects: [], project: null,
  files: [], jobs: [], results: [],
  system: null, disk: null, outputDirs: {}, scanSeq: 0,
  selected: new Set(), perFile: {},
  selectedJobs: new Set(), selectedResults: new Set(), expandedManifests: new Set(),
  toolId: null, params: {},
  sort: { key: null, dir: 1 },
  filter: { key: '', op: 'lt', value: '' },
  logTimer: null,
  tutorial: { files: [], current: 'README.md', visible: true },
};

const TITLES = {
  projects: ['项目与文件', '选择一个输入目录，扫描 CIF，然后把文件交给工具。'],
  tools: ['工具与参数', '每个工具的参数来自 JSON 清单；在这里改默认值，或在文件上单独覆盖。'],
  runs: ['运行队列', '单机串行执行，避免多个 QE 同时抢内存。'],
  results: ['结果与筛选', '筛选只影响显示和导出；删除记录时可选择清理缓存/输出。'],
  tutorial: ['教程', '按章节阅读；先读第 0–2 章，再按需跳转。'],
  settings: ['路径设置', '每个工具一张卡片；查看版本、路径，自动检测或下载。'],
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { data = {}; }
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

function toast(msg, bad = false, ms = 3200) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast' + (bad ? ' bad' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('hidden'), ms);
}

const SKINS = {
  'simple-day': { label: '简约 · 白天', dynamic: false },
  'simple-night': { label: '简约 · 夜晚', dynamic: false },
  'dynamic-day': { label: '动态 · 白天', dynamic: true },
  'dynamic-night': { label: '动态 · 夜晚', dynamic: true },
};

state.skin = document.documentElement.dataset.skin || 'simple-night';

function closeSkinMenu() {
  const menu = $('#skin-menu');
  const btn = $('#skin-toggle');
  if (menu) menu.classList.add('hidden');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

function applySkin(id, persist = true) {
  if (!SKINS[id]) id = 'simple-night';
  state.skin = id;
  document.documentElement.dataset.skin = id;
  if (persist) {
    try { localStorage.setItem('mofui.skin', id); } catch (e) {}
  }
  const cur = $('#skin-current');
  if (cur) cur.textContent = SKINS[id].label;
  const sw = $('#skin-swatch');
  if (sw) sw.className = 'skin-swatch skin-swatch-' + id;
  $$('.skin-option').forEach(b => b.classList.toggle('active', b.dataset.skin === id));
  if (SKINS[id].dynamic) ambient.start(id);
  else ambient.stop();
  closeSkinMenu();
}

/* Neon / pastel light-point background for the dynamic skins. */
const ambient = {
  canvas: null, ctx: null, raf: 0, mode: null,
  points: [], lastBg: 0, nextBg: 0, lastFrame: 0, lastDraw: 0, boostUntil: 0,
  spriteCache: {},
  mouse: { x: 0, y: 0, inside: false },

  init() {
    this.canvas = $('#ambient-canvas');
    this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
    if (this.ctx) this.resize();
  },

  resize() {
    if (!this.canvas || !this.ctx) return;
    // The ambient layer is intentionally soft; 1 CSS pixel backing store is
    // indistinguishable from 2x here and cuts fill/blur work by up to 4x.
    const w = window.innerWidth, h = window.innerHeight;
    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.w = w; this.h = h;
  },

  palette() {
    return this.mode === 'dynamic-night'
      ? [188, 320, 96, 24, 266, 54]
      : [18, 164, 205, 42, 276, 338];
  },

  lightSprite(hue, mode) {
    // Pre-bake the 1.3x blur and pure-colour falloff once. Drawing this small
    // image is far cheaper than a full-screen canvas filter every frame.
    const h = ((Math.round(hue / 10) * 10) % 360 + 360) % 360;
    const key = mode + ':' + h;
    if (this.spriteCache[key]) return this.spriteCache[key];
    const size = 256;
    const cv = document.createElement('canvas');
    cv.width = cv.height = size;
    const c = size / 2;
    const g = cv.getContext('2d');
    const night = mode === 'dynamic-night';
    const sat = night ? 100 : 88;
    const light = night ? 62 : 60;
    const grd = g.createRadialGradient(c, c, 0, c, c, c);
    grd.addColorStop(0, 'hsla(' + h + ',' + sat + '%,' + light + '%,1)');
    grd.addColorStop(0.22, 'hsla(' + h + ',' + sat + '%,' + light + '%,.86)');
    grd.addColorStop(0.48, 'hsla(' + h + ',' + sat + '%,' + light + '%,.34)');
    grd.addColorStop(0.74, 'hsla(' + h + ',' + sat + '%,' + light + '%,.09)');
    grd.addColorStop(1, 'hsla(' + h + ',' + sat + '%,' + light + '%,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, size, size);
    this.spriteCache[key] = cv;
    return cv;
  },

  start(mode) {
    this.init();
    if (!this.ctx) return;
    if (this.mode === mode && this.raf) return;
    this.stop(true);
    this.mode = mode;
    this.resize();
    this.canvas.style.display = 'block';
    this.points = [];
    this.spriteCache = {};
    this.lastFrame = performance.now();
    this.lastDraw = 0;
    this.boostUntil = 0;
    const now = this.lastFrame;
    this.nextBg = now + 1500;
    this.lastBg = now - 12000;
    this.spawnBg(now);
    this.spawnBg(now);
    this.raf = requestAnimationFrame((t) => this.tick(t));
  },

  stop(hard = false) {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.mode = null;
    this.points = [];
    if (this.ctx && this.canvas) this.ctx.clearRect(0, 0, this.w || 0, this.h || 0);
    if (this.canvas) this.canvas.style.display = 'none';
  },

  spawnBg(now) {
    const w = this.w || window.innerWidth;
    const h = this.h || window.innerHeight;
    const base = Math.min(w, h);
    const hues = this.palette();
    // Background lights are 2x the previous size; mouse light stays compact.
    const r = base * (0.20 + Math.random() * 0.24);
    this.points.push({
      type: 'bg',
      x: r * 0.35 + Math.random() * Math.max(1, w - r * 0.7),
      y: r * 0.35 + Math.random() * Math.max(1, h - r * 0.7),
      r, baseAlpha: 0.34 + Math.random() * 0.20,
      hue: hues[Math.floor(Math.random() * hues.length)],
      born: now, life: 50000 + Math.random() * 50000,
      phase: Math.random() * Math.PI * 2,
      period: 120000,
      vx: (Math.random() - 0.5) * 4,
      vy: (Math.random() - 0.5) * 4,
    });
  },

  spawnMouse(x, y, now) {
    const base = Math.min(this.w || window.innerWidth, this.h || window.innerHeight);
    const existing = this.points.find(p => p.type === 'mouse');
    if (existing) {
      // One cursor light only. Update its centre immediately; no lerp/throttle.
      existing.mx = x;
      existing.my = y;
      existing.x = x + Math.cos(existing.angle) * existing.orbit;
      existing.y = y + Math.sin(existing.angle * 0.82) * existing.orbit * 0.66;
      existing.life = Math.min(120000, Math.max(existing.life, now - existing.born + 6000));
      return;
    }
    const hue = Math.random() * 360;
    this.points.push({
      type: 'mouse', x, y, mx: x, my: y,
      r: base * (0.070 + Math.random() * 0.090),
      baseAlpha: 0.40 + Math.random() * 0.18,
      hue,
      hueSpeed: 8 + Math.random() * 14,
      born: now, life: 24000 + Math.random() * 18000,
      phase: Math.random() * Math.PI * 2,
      period: 60000,
      angle: Math.random() * Math.PI * 2,
      spin: (Math.random() < 0.5 ? -1 : 1) * (0.12 + Math.random() * 0.32),
      orbit: 18 + Math.random() * (base * 0.055),
      vx: 0, vy: 0,
    });
  },

  tick(now) {
    if (!this.ctx || !this.mode) return;
    this.raf = requestAnimationFrame((t) => this.tick(t));
    if (document.hidden) return;
    // 60 fps only while the cursor is moving; the slow breathing background
    // needs ~30 fps, so idle cost is halved.
    const interval = now < this.boostUntil ? 1000 / 60 : 1000 / 30;
    if (now - this.lastDraw < interval) return;
    const dt = Math.min(0.05, Math.max(0.001, (now - this.lastFrame) / 1000));
    this.lastFrame = now;
    this.lastDraw = now;
    const w = this.w, h = this.h;
    this.ctx.clearRect(0, 0, w, h);
    this.ctx.globalCompositeOperation = this.mode === 'dynamic-night' ? 'lighter' : 'source-over';

    const bgCount = this.points.filter(p => p.type === 'bg').length;
    if (bgCount < 5 && now >= this.nextBg) {
      this.spawnBg(now);
      this.nextBg = now + 7000 + Math.random() * 7000;
    }
    this.points = this.points.filter(p => now - p.born < p.life);
    for (const p of this.points) {
      const age = now - p.born;
      let fade = Math.min(1, age / 4500);
      if (age > p.life - 14000) fade = Math.max(0, (p.life - age) / 14000);
      const breathe = 1 + 0.30 * Math.sin(p.phase + (now / p.period) * Math.PI * 2);
      let hue = p.hue;
      if (p.type === 'mouse') {
        p.hue = (p.hue + p.hueSpeed * dt) % 360;
        hue = p.hue;
        const targetX = this.mouse.inside ? this.mouse.x : p.mx;
        const targetY = this.mouse.inside ? this.mouse.y : p.my;
        // Directly follow the cursor; the old 3.5/s lerp was the visible lag.
        p.mx = targetX;
        p.my = targetY;
        p.angle += p.spin * dt;
        p.x = p.mx + Math.cos(p.angle) * p.orbit;
        p.y = p.my + Math.sin(p.angle * 0.82) * p.orbit * 0.66;
      } else {
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        if (p.x < -p.r) p.x = w + p.r;
        if (p.x > w + p.r) p.x = -p.r;
        if (p.y < -p.r) p.y = h + p.r;
        if (p.y > h + p.r) p.y = -p.r;
      }
      const r = Math.max(8, p.r * breathe);
      const day = this.mode === 'dynamic-day';
      const a = Math.min(1, p.baseAlpha * fade * (day ? 1.55 : 1));
      // Each light keeps one hue; overlapping lights still blend through the
      // canvas composite mode (lighter at night, alpha mixing in daylight).
      this.ctx.globalAlpha = a;
      this.ctx.drawImage(this.lightSprite(hue, this.mode), p.x - r, p.y - r, r * 2, r * 2);
      this.ctx.globalAlpha = 1;
    }
  },
};

function fmt(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') {
    if (!isFinite(v)) return String(v);
    if (v !== 0 && (Math.abs(v) >= 1e5 || Math.abs(v) < 1e-3)) return v.toExponential(3);
    return String(Math.round(v * 10000) / 10000);
  }
  if (typeof v === 'boolean') return v ? '是' : '否';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function statusText(s) {
  return ({ staged: '待启动', queued: '排队', running: '运行中', done: '完成', failed: '失败', cancelled: '已取消', cancelling: '取消中' })[s] || s || '—';
}
function statusHtml(s) {
  return '<span class="status ' + esc(s || '') + '">' + esc(statusText(s)) + '</span>';
}

function switchView(name) {
  $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
  const t = TITLES[name] || TITLES.projects;
  $('#page-title').textContent = t[0];
  $('#page-sub').textContent = t[1];
  if (name === 'runs') refreshJobs();
  if (name === 'results') refreshResults();
  if (name === 'tools') renderTools();
  document.body.classList.toggle('tutorial-mode', name === 'tutorial');
  if (name === 'tutorial') loadTutorial(state.tutorial.current || 'README.md').catch(err => toast(err.message, true));
  if (name === 'settings') renderSettings();
}

async function loadTutorial(name = 'README.md') {
  const data = await api('/api/tutorial?file=' + encodeURIComponent(name));
  state.tutorial.files = data.files || [];
  state.tutorial.current = data.name || name;
  const sel = $('#tutorial-select');
  sel.innerHTML = state.tutorial.files.map(f => '<option value="' + esc(f.name) + '">' + esc(f.title) + '</option>').join('');
  sel.value = state.tutorial.current;
  $('#tutorial-body').innerHTML = data.html || '<p>教程为空。</p>';
}

function outputDirFor(m) {
  return (m && state.outputDirs[m.id]) || (state.settings && state.settings.work_root) || '';
}

function durationText(min) {
  if (!min || min <= 0) return '不到 1 分钟';
  if (min < 1) return Math.max(1, Math.round(min * 60)) + ' 秒';
  if (min < 60) return Math.ceil(min) + ' 分钟';
  if (min < 240) {
    const h = Math.ceil(min / 30) / 2;
    return (h % 1 === 0 ? h.toFixed(0) : h.toFixed(1)) + ' 小时';
  }
  return Math.ceil(min / 60) + ' 小时';
}

function estimateLabel(min) {
  if (min >= 60) return '长时耗，至少需要 ' + durationText(min);
  return '约 ' + durationText(min);
}

function estimateFor(m, file, params) {
  const e = m && m.estimate;
  if (!e) return null;
  const p = Object.assign({}, state.params, params || {});
  const atoms = Number(file && file.natoms) || Number(e.atoms_ref) || 306;
  const ar = Number(e.atoms_ref) || 306;
  let minutes = Number(e.minutes_ref) || 1;
  let diskMb = Number(e.disk_mb_ref) || 10;
  const kind = e.kind || '';
  if (kind === 'mace') {
    const sites = Number(p.n_sites) || Number(e.sites_ref) || 24;
    const sr = Number(e.sites_ref) || 24;
    const f = (atoms / ar) * (sites / sr);
    minutes *= f;
    diskMb *= f;
    if (state.system) {
      if (!state.system.gpu_ok) minutes *= 8;
      else if (state.system.gpu_score && state.system.gpu_score < 3060) minutes *= 2;
      if (state.system.ram_gb && state.system.ram_gb < 16) minutes *= 1.2;
    }
  } else if (kind === 'qe_from_in' && file && file.calculation === 'relax') {
    const steps = Number(file.nstep) || 1;
    minutes = 40 * Math.pow(atoms / ar, 2.0) * steps;
    diskMb *= atoms / ar;
  } else if (kind === 'qe_relax') {
    const steps = Number(p.nstep) || Number(e.steps_ref) || 1;
    minutes *= Math.pow(atoms / ar, Number(e.scaling) || 2.0) * steps;
    diskMb *= atoms / ar;
  } else if (kind.indexOf('qe_') === 0) {
    minutes *= Math.pow(atoms / ar, Number(e.scaling) || 2.5);
    diskMb *= atoms / ar;
  } else if (kind === 'md' || kind === 'structure' || kind === 'converter') {
    minutes *= atoms / ar;
    diskMb *= atoms / ar;
  }
  if (kind.indexOf('qe_') === 0 && state.system) {
    if (state.system.cpu_count && state.system.cpu_count < 6) minutes *= 6 / state.system.cpu_count;
    if (state.system.ram_gb && state.system.ram_gb < 16) minutes *= 1.5;
  }
  return { minutes: Math.max(0.05, minutes), disk_mb: Math.max(1, diskMb), atoms: atoms };
}

function estimateChip(est) {
  if (!est) return '<span class="hint">无预估</span>';
  const long = est.minutes >= 60;
  const cls = long ? 'est-long' : (est.minutes >= 10 ? 'est-mid' : 'est-short');
  return '<span class="est ' + cls + '">' + esc(estimateLabel(est.minutes)) + '</span>' +
    '<div class="est-disk">磁盘约 ' + esc((est.disk_mb / 1024).toFixed(2)) + ' GB</div>';
}

async function refreshDisk() {
  const m = manifest();
  const dir = outputDirFor(m);
  if (!dir) { state.disk = null; renderEstimateBar(); return; }
  try {
    state.disk = await api('/api/disk?path=' + encodeURIComponent(dir));
  } catch (e) { state.disk = null; }
  renderEstimateBar();
}

function renderEstimateBar() {
  const bar = $('#estimate-bar');
  if (!bar) return;
  const m = manifest();
  const sys = state.system;
  const hw = sys
    ? '<b>本机：</b>' + esc(sys.gpu_name || '无 NVIDIA GPU') +
      (sys.vram_gb ? ' ' + esc(sys.vram_gb) + 'GB' : '') +
      ' · ' + esc(sys.ram_gb || '?') + 'GB RAM · ' + esc(sys.cpu_count || '?') + ' 核' +
      '<span class="ref-badge ' + (sys.reference_ok ? 'ok' : 'warn') + '">参考档：' + esc(sys.reference) + (sys.reference_ok ? '（达标）' : '（低于参考档，实际更慢）') + '</span>'
    : '<b>本机：</b>检测中…';
  if (!m) { bar.innerHTML = '<div class="hw-line">' + hw + '</div>'; return; }
  const selected = state.files.filter(f => state.selected.has(f.rel));
  const files = selected.length ? selected : state.files;
  let totalMin = 0, totalDisk = 0, n = 0;
  files.forEach(f => {
    const est = estimateFor(m, f, state.perFile[f.rel]);
    if (est) { totalMin += est.minutes; totalDisk += est.disk_mb; n += 1; }
  });
  const out = outputDirFor(m);
  let diskText = '';
  if (state.disk && state.disk.free_gb !== undefined) {
    diskText = ' · 剩余 ' + state.disk.free_gb + ' GB';
  }
  let summary = '当前工具：<b>' + esc(m.name) + '</b>';
  if (n) summary += ' · ' + (selected.length ? '已选 ' : '共 ') + n + ' 个文件 · 总预估 <b>' + esc(estimateLabel(totalMin)) + '</b> · 预计磁盘 <b>' + esc((totalDisk / 1024).toFixed(2)) + ' GB</b>';
  summary += diskText;
  if (totalDisk > 0 && state.disk && state.disk.free_gb !== undefined && totalDisk / 1024 > state.disk.free_gb * 0.8) {
    summary += ' <span class="est-warn">空间偏紧，建议换输出目录</span>';
  }
  bar.innerHTML = '<div class="hw-line">' + hw + '</div><div class="est-line">' + summary + '</div>' +
    (out ? '<div class="out-line">输出目录：<code>' + esc(out) + '</code></div>' : '');
}

async function chooseDir(inputEl, title) {
  try {
    toast('已打开系统选择框，请在弹出的窗口里选择…');
    const d = await api('/api/pick-path', { method: 'POST', body: { kind: 'dir', title } });
    if (d.cancelled) { toast('已取消选择'); return; }
    inputEl.value = d.path;
    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    toast('已选择：' + d.path);
  } catch (e) { toast(e.message, true); }
}

function manifest() {
  return state.manifests.find(m => m.id === state.toolId) || null;
}

function defaultsFor(m) {
  const d = {};
  (m.params || []).forEach(p => { d[p.key] = p.default; });
  try {
    const saved = JSON.parse(localStorage.getItem('mofui.tool.' + m.id) || '{}');
    Object.assign(d, saved);
  } catch (e) {}
  return d;
}

function loadOutputDirs() {
  state.outputDirs = {};
  state.manifests.forEach(m => {
    const saved = localStorage.getItem('mofui.output.' + m.id);
    if (saved) state.outputDirs[m.id] = saved;
  });
}

function paramField(spec, value, attr) {
  const key = esc(spec.key);
  const label = esc(spec.label || spec.key);
  const helpText = spec.help || spec.note;
  const note = helpText ? '<span class="param-note">' + esc(helpText) + '</span>' : '';
  let input = '';
  if (spec.type === 'select') {
    input = '<select data-' + attr + '="' + key + '">' +
      (spec.options || []).map(o => '<option value="' + esc(o) + '"' + (String(o) === String(value) ? ' selected' : '') + '>' + esc(o) + '</option>').join('') +
      '</select>';
  } else if (spec.type === 'bool') {
    input = '<label class="check"><input type="checkbox" data-' + attr + '="' + key + '"' + (value ? ' checked' : '') + '> 启用</label>';
  } else {
    const type = spec.type === 'int' ? 'number' : (spec.type === 'float' ? 'number' : 'text');
    const step = spec.type === 'int' ? '1' : 'any';
    input = '<input type="' + type + '" step="' + step + '" data-' + attr + '="' + key + '" value="' + esc(value == null ? '' : value) + '">';
  }
  return '<label>' + label + input + note + '</label>';
}

function paramFields(m, values, attr) {
  if (!m) return '';
  return (m.params || []).map(p => paramField(p, values[p.key], attr)).join('');
}

function detailHtml(m, open) {
  const d = m && m.details;
  if (!d) return '';
  let h = '<details class="tool-detail"' + (open ? ' open' : '') + '>' +
    '<summary>详细说明：这个工具在做什么、参数怎么改、这次计算的例子</summary>' +
    '<div class="detail-body">';
  if (d.what) h += '<p>' + esc(d.what) + '</p>';
  if (m.estimate && m.estimate.reference) h += '<h4>参考耗时 / 机器</h4><p>' + esc(m.estimate.reference) + '</p>';
  if (d.how && d.how.length) h += '<h4>它怎么做</h4><ol>' + d.how.map(x => '<li>' + esc(x) + '</li>').join('') + '</ol>';
  if (d.params && Object.keys(d.params).length) {
    h += '<h4>参数作用</h4><dl>' + Object.entries(d.params).map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>';
  }
  if (d.example) h += '<h4>这次计算的例子</h4><div class="example">' + esc(d.example) + '</div>';
  if (d.warnings && d.warnings.length) h += '<h4>容易踩的坑</h4><ul class="warn-list">' + d.warnings.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>';
  h += '</div></details>';
  return h;
}

function readFields(container, attr) {
  const out = {};
  $$('[data-' + attr + ']', container).forEach(el => {
    const key = el.dataset[attr];
    if (el.type === 'checkbox') out[key] = el.checked;
    else if (el.type === 'number') out[key] = el.value === '' ? null : Number(el.value);
    else out[key] = el.value;
  });
  return out;
}

function renderToolSelect() {
  const sel = $('#tool-select');
  sel.innerHTML = state.manifests.map(m => '<option value="' + esc(m.id) + '">' + esc(m.name) + '</option>').join('');
  if (!state.manifests.some(m => m.id === state.toolId)) state.toolId = state.manifests[0] ? state.manifests[0].id : null;
  if (state.toolId) sel.value = state.toolId;
  sel.disabled = !state.project || !state.manifests.length;
  $('#tool-params-btn').disabled = !state.toolId;
}

function renderToolParams() {
  const m = manifest();
  const panel = $('#tool-params');
  const help = $('#tool-help');
  if (!m) { panel.innerHTML = ''; if (help) help.innerHTML = ''; return; }
  const out = outputDirFor(m);
  panel.innerHTML =
    '<div class="params-grid">' + paramFields(m, state.params, 'param') + '</div>' +
    '<div class="output-row"><label>输出目录' +
      '<div class="path-row"><input id="tool-output-dir" value="' + esc(out) + '">' +
      '<button type="button" class="btn pick" id="pick-tool-output">选择…</button></div></label>' +
      '<span class="hint">' + esc(m.output_note || '这个工具单独保存；点“选择…”可换目录。') + '</span></div>' +
    '<div class="form-actions"><button class="btn small ghost" id="save-tool-default">保存为这个工具的默认值</button>' +
    '<span class="hint">这些值会用在批量任务；单个文件可以在行内“参数”里覆盖。</span></div>';
  panel.oninput = () => {
    state.params = readFields(panel, 'param');
    const o = $('#tool-output-dir');
    if (o) state.outputDirs[m.id] = o.value.trim();
  };
  const pick = $('#pick-tool-output');
  if (pick) pick.onclick = () => chooseDir($('#tool-output-dir'), '选择输出目录');
  const outInput = $('#tool-output-dir');
  if (outInput) outInput.onchange = () => {
    state.outputDirs[m.id] = outInput.value.trim();
    localStorage.setItem('mofui.output.' + m.id, outInput.value.trim());
    refreshDisk();
  };
  const b = $('#save-tool-default', panel);
  if (b) b.onclick = () => {
    state.params = readFields(panel, 'param');
    state.outputDirs[m.id] = ($('#tool-output-dir') || {}).value || outputDirFor(m);
    localStorage.setItem('mofui.tool.' + m.id, JSON.stringify(state.params));
    localStorage.setItem('mofui.output.' + m.id, state.outputDirs[m.id]);
    toast('已保存 ' + m.name + ' 的默认参数和输出目录');
  };
  if (help) help.innerHTML = detailHtml(m, false);
  refreshDisk();
}

function renderProjects() {
  const box = $('#projects-list');
  if (!state.projects.length) { box.innerHTML = '<div class="empty" style="padding:18px;color:#8a999c">还没有项目。</div>'; return; }
  box.innerHTML = state.projects.map(p =>
    '<div class="project-item ' + (state.project && state.project.id === p.id ? 'active' : '') + '" data-pid="' + p.id + '">' +
      '<div style="min-width:0"><b>' + esc(p.name) + '</b><small>' + esc(p.input_dir) + '</small></div>' +
      '<button class="del" data-del="' + p.id + '" title="删除项目">×</button>' +
    '</div>'
  ).join('');
  $$('.project-item', box).forEach(el => {
    el.onclick = (ev) => {
      if (ev.target.dataset.del) return;
      selectProject(Number(el.dataset.pid));
    };
  });
  $$('[data-del]', box).forEach(b => {
    b.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm('删除这个项目？只会删除界面记录，不会删除文件或运行结果。')) return;
      await api('/api/projects/' + b.dataset.del, { method: 'DELETE' });
      state.projects = state.projects.filter(p => p.id !== Number(b.dataset.del));
      if (state.project && state.project.id === Number(b.dataset.del)) {
        state.project = null; state.files = []; state.selected.clear();
        $('#project-pill').textContent = '未选择项目';
        renderFiles();
      }
      renderProjects();
    };
  });
}

function selectProject(id) {
  const p = state.projects.find(x => x.id === id);
  if (!p) return;
  state.project = p;
  state.files = [];
  state.selected.clear();
  state.perFile = {};
  $('#project-pill').textContent = p.name + ' · ' + p.input_dir;
  renderProjects();
  renderToolSelect();
  renderFiles();
  $('#scan-btn').disabled = false;
  $('#run-selected').disabled = false;
  $('#files-hint').textContent = '自动扫描中…';
  switchView('projects');
  scanProject();
}

async function scanProject() {
  if (!state.project) return;
  const seq = ++state.scanSeq;
  $('#scan-btn').disabled = true;
  $('#files-hint').textContent = '扫描中…';
  try {
    const rec = $('#recursive').checked ? '1' : '0';
    const files = await api('/api/projects/scan?id=' + state.project.id + '&recursive=' + rec);
    if (seq !== state.scanSeq) return;
    state.files = files;
    state.selected.clear();
    $('#files-hint').textContent = state.files.length + ' 个可识别文件';
    renderFiles();
  } catch (e) {
    if (seq === state.scanSeq) {
      toast(e.message, true);
      $('#files-hint').textContent = '扫描失败';
    }
  } finally {
    if (seq === state.scanSeq) $('#scan-btn').disabled = false;
  }
}

function accepted(file) {
  const m = manifest();
  return !!m && (m.accepts || []).includes(file.suffix);
}

function renderFiles() {
  const tbody = $('#files-table tbody');
  if (!state.project) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">先建立或选择项目。</td></tr>';
    renderEstimateBar();
    return;
  }
  if (!state.files.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">还没有文件。点“扫描目录”。</td></tr>';
    renderEstimateBar();
    return;
  }
  const m = manifest();
  tbody.innerHTML = state.files.map(f => {
    const ok = accepted(f);
    const checked = state.selected.has(f.rel);
    const last = f.last_job ? statusHtml(f.last_job.status) : '<span class="hint">未运行</span>';
    const big = f.size > 50 * 1024 * 1024;
    const sizeTxt = f.size > 1048576 ? (f.size / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(f.size / 1024)) + ' KB';
    const est = estimateFor(m, f, state.perFile[f.rel]);
    return '<tr data-rel="' + esc(f.rel) + '">' +
      '<td><input type="checkbox" data-check="' + esc(f.rel) + '"' + (checked ? ' checked' : '') + (ok ? '' : ' disabled title="当前工具不接受该后缀"') + '></td>' +
      '<td><div class="file-name">' + esc(f.name) + '</div><div class="file-path">' + esc(f.rel) + '</div></td>' +
      '<td>' + (f.natoms ? esc(f.natoms) + ' · ' + esc(f.formula || '') : (f.error ? '<span class="hint">读取失败</span>' : '—')) + '</td>' +
      '<td>' + sizeTxt + (big ? ' <span class="file-warn">大文件</span>' : '') + '</td>' +
      '<td>' + (est ? estimateChip(est) : '—') + '</td>' +
      '<td>' + last + '</td>' +
      '<td>' +
        '<button class="btn small ghost" data-params="' + esc(f.rel) + '">参数</button> ' +
        '<button class="btn small primary" data-run="' + esc(f.rel) + '"' + (ok ? '' : ' disabled') + '>加入队列</button>' +
      '</td>' +
    '</tr>';
  }).join('');
  renderEstimateBar();
}

function toggleAll(checked) {
  state.selected.clear();
  if (checked) state.files.forEach(f => { if (accepted(f)) state.selected.add(f.rel); });
  renderFiles();
}

async function createProject(ev) {
  ev.preventDefault();
  const name = $('#project-name').value.trim();
  const dir = $('#project-dir').value.trim();
  try {
    const p = await api('/api/projects', { method: 'POST', body: { name, input_dir: dir } });
    state.projects.unshift(p);
    $('#project-name').value = '';
    $('#project-dir').value = '';
    renderProjects();
    selectProject(p.id);
  } catch (e) { toast(e.message, true); }
}

function showModal(title, body, foot) {
  $('#modal-title').textContent = title;
  $('#modal-body').innerHTML = body;
  $('#modal-foot').innerHTML = foot || '<button class="btn ghost" id="modal-close-2">关闭</button>';
  $('#modal').classList.remove('hidden');
  const c = $('#modal-close-2');
  if (c) c.onclick = closeModal;
}

function closeModal() {
  $('#modal').classList.add('hidden');
  if (state.logTimer) { clearInterval(state.logTimer); state.logTimer = null; }
}

function openParams(rel) {
  const f = state.files.find(x => x.rel === rel);
  const m = manifest();
  if (!f || !m) return;
  const vals = Object.assign({}, state.params, state.perFile[rel] || {});
  showModal('参数 · ' + f.name,
    '<div class="modal-note">只对这个文件覆盖参数。点“保存参数”后，批量运行时也会用它。</div>' +
    '<div class="params-grid" id="modal-params">' + paramFields(m, vals, 'mparam') + '</div>',
    '<button class="btn ghost" id="mp-cancel">取消</button>' +
    '<button class="btn" id="mp-save">保存参数</button>' +
    '<button class="btn primary" id="mp-run">仅运行此文件</button>');
  $('#mp-cancel').onclick = closeModal;
  $('#mp-save').onclick = () => {
    state.perFile[rel] = readFields($('#modal-params'), 'mparam');
    toast('已保存该文件的参数覆盖');
    closeModal();
  };
  $('#mp-run').onclick = () => {
    const vals = readFields($('#modal-params'), 'mparam');
    closeModal();
    runFiles([f], vals);
  };
}

async function openQueueConfirm(files, paramsOverride) {
  if (!state.project) { toast('先选择项目', true); return; }
  const m = manifest();
  if (!m) { toast('先选择工具', true); return; }
  const usable = files.filter(accepted);
  if (!usable.length) { toast('没有当前工具能处理的文件', true); return; }
  const out = outputDirFor(m);
  const rows = usable.map(f => {
    const params = paramsOverride || state.perFile[f.rel] || state.params || {};
    return { f, params, est: estimateFor(m, f, params) };
  });
  let totalMin = 0, totalDisk = 0;
  rows.forEach(r => { if (r.est) { totalMin += r.est.minutes; totalDisk += r.est.disk_mb; } });
  let disk = null;
  try { disk = await api('/api/disk?path=' + encodeURIComponent(out)); } catch (e) {}
  const freeGb = disk && disk.free_gb !== undefined ? disk.free_gb : null;
  const warnings = [];
  rows.forEach(r => {
    if (r.f.size > 50 * 1024 * 1024) warnings.push('输入文件 ' + r.f.name + ' 较大（' + (r.f.size / 1048576).toFixed(1) + ' MB），复制会占空间。');
  });
  if (freeGb !== null && totalDisk / 1024 > freeGb) {
    warnings.push('预计需要 ' + (totalDisk / 1024).toFixed(2) + ' GB，但输出目录只剩 ' + freeGb + ' GB。请换到空间更大的目录。');
  } else if (freeGb !== null && totalDisk / 1024 > freeGb * 0.8) {
    warnings.push('预计需要 ' + (totalDisk / 1024).toFixed(2) + ' GB，剩余 ' + freeGb + ' GB，空间偏紧。');
  }
  const blocked = freeGb !== null && totalDisk / 1024 > freeGb * 0.98;
  const long = rows.some(r => r.est && r.est.minutes >= 60);
  const checkpointOK = long && m.estimate && m.estimate.checkpoint_supported;
  let body = '<div class="modal-note"><b>加入队列后不会自动运行。</b>请到“运行队列”点“启动队列”。</div>' +
    '<div class="confirm-summary">' +
      '<div><span>工具</span><b>' + esc(m.name) + '</b></div>' +
      '<div><span>输出目录</span><code>' + esc(out) + '</code></div>' +
      '<div><span>合计</span><b>' + rows.length + ' 个文件 · ' + esc(estimateLabel(totalMin)) + ' · 磁盘约 ' + esc((totalDisk / 1024).toFixed(2)) + ' GB</b></div>' +
      (freeGb !== null ? '<div><span>剩余空间</span><b class="' + (blocked ? 'bad' : '') + '">' + esc(freeGb) + ' GB</b></div>' : '') +
    '</div>' +
    '<div class="confirm-list">' + rows.map(r =>
      '<div><span>' + esc(r.f.name) + '</span><span>' + (r.est ? esc(estimateLabel(r.est.minutes)) + ' · ' + (r.est.disk_mb / 1024).toFixed(2) + ' GB' : '无预估') + '</span></div>'
    ).join('') + '</div>';
  if (warnings.length) body += '<div class="confirm-warn">' + warnings.map(x => '<div>⚠ ' + esc(x) + '</div>').join('') + '</div>';
  if (checkpointOK) {
    body += '<label class="check-line"><input type="checkbox" id="chk-checkpoint"> 开启保存点（默认关闭）</label>' +
      '<div class="hint">开启后 QE 会保留 tmp/wavefunction，磁盘占用更大；中断后可在运行队列点“继续”。</div>';
  } else if (long) {
    body += '<div class="hint">这个工具不支持保存点；长任务中断后只能重跑。</div>';
  }
  showModal('确认加入队列', body,
    '<button class="btn ghost" id="confirm-cancel">返回修改</button>' +
    '<button class="btn primary" id="confirm-queue"' + (blocked ? ' disabled' : '') + '>加入队列（不启动）</button>');
  $('#confirm-cancel').onclick = closeModal;
  $('#confirm-queue').onclick = async () => {
    const checkpoint = !!($('#chk-checkpoint') && $('#chk-checkpoint').checked);
    closeModal();
    await createStagedJobs(rows, checkpoint, out);
  };
}

async function createStagedJobs(rows, checkpoint, out) {
  const m = manifest();
  let n = 0;
  try {
    for (const r of rows) {
      const res = await api('/api/jobs', { method: 'POST', body: {
        project_id: state.project.id, tool_id: m.id, files: [r.f.rel],
        params: r.params || {}, output_dir: out, checkpoint: !!checkpoint,
      }});
      n += (res.created || []).length;
    }
    toast('已加入队列（未启动）：' + n + ' 个。请在“运行队列”里点“启动队列”。');
    switchView('runs');
    await refreshJobs();
  } catch (e) { toast(e.message, true); }
}

async function runFiles(files, paramsOverride) {
  return openQueueConfirm(files, paramsOverride);
}

async function runSelected() {
  const files = state.files.filter(f => state.selected.has(f.rel));
  if (!files.length) { toast('先勾选文件', true); return; }
  await runFiles(files);
}

async function refreshJobs() {
  try {
    const q = state.project ? ('?project_id=' + state.project.id) : '';
    state.jobs = await api('/api/jobs' + q);
    renderJobs();
    updateServer(true);
  } catch (e) { updateServer(false); }
}

function shortMetrics(metrics) {
  if (!metrics) return '—';
  const keys = ['total_energy_eV', 'best_eads_eV', 'D_m2_s', 'min_distance_A', 'natoms'];
  const bits = [];
  keys.forEach(k => { if (metrics[k] !== undefined && metrics[k] !== null) bits.push(k.replace(/_/g, ' ') + '=' + fmt(metrics[k])); });
  if (!bits.length) Object.keys(metrics).slice(0, 3).forEach(k => bits.push(k + '=' + fmt(metrics[k])));
  return bits.map(x => '<span>' + esc(x) + '</span>').join('');
}

function canDeleteJob(j) {
  return j && j.status !== 'running' && j.status !== 'cancelling';
}

function renderJobs() {
  const tbody = $('#jobs-table tbody');
  const staged = state.jobs.filter(j => j.status === 'staged').length;
  const running = state.jobs.filter(j => j.status === 'running' || j.status === 'queued' || j.status === 'cancelling').length;
  const startBtn = $('#start-queue');
  if (startBtn) startBtn.disabled = staged === 0;
  const deletable = new Set(state.jobs.filter(canDeleteJob).map(j => j.id));
  state.selectedJobs = new Set(Array.from(state.selectedJobs).filter(id => deletable.has(id)));
  if (!state.jobs.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">还没有任务。去“项目与文件”加入队列。</td></tr>';
    $('#runs-hint').textContent = '没有任务';
    const all = $('#check-all-jobs');
    if (all) { all.checked = false; all.indeterminate = false; all.disabled = true; }
    const bulk = $('#delete-selected-jobs');
    if (bulk) { bulk.disabled = true; bulk.textContent = '删除选中'; }
    return;
  }
  const selectedCount = state.selectedJobs.size;
  $('#runs-hint').textContent = '待启动 ' + staged + ' 个 · 进行中 ' + running + ' 个' + (selectedCount ? ' · 已选 ' + selectedCount + ' 个' : '');
  const eligible = state.jobs.filter(canDeleteJob);
  const all = $('#check-all-jobs');
  if (all) {
    all.disabled = eligible.length === 0;
    all.checked = eligible.length > 0 && selectedCount === eligible.length;
    all.indeterminate = selectedCount > 0 && selectedCount < eligible.length;
  }
  const bulk = $('#delete-selected-jobs');
  if (bulk) {
    bulk.disabled = selectedCount === 0;
    bulk.textContent = selectedCount ? '删除选中 (' + selectedCount + ')' : '删除选中';
  }
  tbody.innerHTML = state.jobs.map((j, idx) => {
    const canCancel = j.status === 'staged' || j.status === 'queued' || j.status === 'running' || j.status === 'cancelling';
    const canRerun = j.status === 'done' || j.status === 'failed' || j.status === 'cancelled';
    const canMove = j.status === 'staged';
    const canResume = !!j.checkpoint && (j.status === 'failed' || j.status === 'cancelled') && j.workdir;
    const canDelete = canDeleteJob(j);
    const selected = state.selectedJobs.has(j.id);
    const cancelLabel = j.status === 'running' ? '终止' : (j.status === 'staged' ? '移除' : '取消');
    return '<tr' + (selected ? ' class="row-selected"' : '') + '>' +
      '<td><input type="checkbox" class="row-check" data-job-check="' + j.id + '"' + (selected ? ' checked' : '') + (canDelete ? '' : ' disabled title="运行中的任务不能删除"') + '></td>' +
      '<td>' + j.id + '</td>' +
      '<td><div class="file-name">' + esc(j.input_rel.split('/').pop()) + '</div><div class="file-path">' + esc(j.input_rel) + '</div></td>' +
      '<td>' + esc(j.tool_id) + (j.checkpoint ? ' <span class="ckpt" title="已开启保存点">保存点</span>' : '') + '</td>' +
      '<td>' + statusHtml(j.status) + '</td>' +
      '<td>' + esc(j.started_at || j.created_at) + '</td>' +
      '<td><div class="metrics-mini">' + shortMetrics(j.metrics) + (j.error ? '<span style="color:#b6493f">' + esc(j.error) + '</span>' : '') + '</div></td>' +
      '<td class="job-actions">' +
        (canMove ? '<button class="btn tiny" data-move="' + j.id + '" data-dir="up" title="上移">↑</button><button class="btn tiny" data-move="' + j.id + '" data-dir="down" title="下移">↓</button> ' : '') +
        '<button class="btn small ghost" data-log="' + j.id + '">日志</button> ' +
        (canCancel ? '<button class="btn small danger" data-cancel="' + j.id + '" data-status="' + esc(j.status) + '">' + cancelLabel + '</button> ' : '') +
        (canResume ? '<button class="btn small" data-resume="' + j.id + '">继续</button> ' : '') +
        (canRerun ? '<button class="btn small" data-rerun="' + j.id + '">重跑</button> ' : '') +
        (canDelete ? '<button class="btn small danger" data-delete-job="' + j.id + '">删除</button>' : '') +
      '</td>' +
    '</tr>';
  }).join('');
}

async function startQueue() {
  try {
    const d = await api('/api/queue/start', { method: 'POST', body: { project_id: state.project ? state.project.id : null } });
    toast('已启动队列：' + (d.started || 0) + ' 个任务');
    await refreshJobs();
  } catch (e) { toast(e.message, true); }
}

async function moveJob(id, dir) {
  try {
    await api('/api/jobs/' + id + '/move', { method: 'POST', body: { direction: dir } });
    await refreshJobs();
  } catch (e) { toast(e.message, true); }
}

async function openLog(id, source = 'runs') {
  if (state.logTimer) { clearInterval(state.logTimer); state.logTimer = null; }
  showModal('运行日志 · #' + id, '<pre class="log-box" id="log-pre">加载中…</pre>',
    '<button class="btn ghost" id="log-close">关闭</button>' +
    '<button class="btn danger" id="log-delete">删除记录</button>');
  $('#log-close').onclick = closeModal;
  $('#log-delete').onclick = () => {
    if (state.logTimer) { clearInterval(state.logTimer); state.logTimer = null; }
    openDeleteJobs([id], source);
  };
  const tick = async () => {
    try {
      const d = await api('/api/jobs/' + id + '/log');
      const pre = $('#log-pre');
      if (pre) {
        pre.textContent = d.log || '(空)';
        pre.scrollTop = pre.scrollHeight;
      }
      if (!['running', 'queued', 'cancelling'].includes(d.status) && state.logTimer) {
        clearInterval(state.logTimer);
        state.logTimer = null;
      }
    } catch (e) {
      const pre = $('#log-pre');
      if (pre) pre.textContent = e.message;
    }
  };
  await tick();
  state.logTimer = setInterval(tick, 2000);
}

async function cancelJob(id, status) {
  const msg = status === 'running'
    ? '这个任务正在运行。确定终止进程？未保存的进度会丢失。'
    : (status === 'staged' ? '把这个任务从待启动队列移除？' : '确定取消这个任务？');
  if (!confirm(msg)) return;
  try {
    await api('/api/jobs/' + id + '/cancel', { method: 'POST', body: {} });
    toast(status === 'running' ? '已发送终止请求' : '已取消');
    refreshJobs();
  } catch (e) { toast(e.message, true); }
}

async function resumeJob(id) {
  if (!confirm('从保存点继续会新建一个任务，并复制上一次的 tmp；确定继续？')) return;
  try {
    const d = await api('/api/jobs/' + id + '/resume', { method: 'POST', body: {} });
    toast('已从保存点加入队列（待启动）');
    await refreshJobs();
  } catch (e) { toast(e.message, true); }
}

async function rerunJob(id) {
  try {
    await api('/api/jobs/' + id + '/rerun', { method: 'POST', body: {} });
    toast('已重新加入队列（待启动）');
    refreshJobs();
  } catch (e) { toast(e.message, true); }
}

function openDeleteJobs(ids, source) {
  const pool = source === 'results' ? state.results : state.jobs;
  const wanted = new Set(ids.map(Number));
  const jobs = pool.filter(j => wanted.has(j.id) && canDeleteJob(j));
  if (!jobs.length) { toast('没有可删除的任务（运行中的任务请先终止）', true); return; }
  const cleanable = jobs.filter(j => j.workdir && j.output_root);
  const roots = Array.from(new Set(cleanable.map(j => j.output_root)));
  const dirs = Array.from(new Set(cleanable.map(j => j.workdir)));
  const hasPaths = dirs.length > 0;
  const previewDirs = dirs.slice(0, 3).map(p => '<code>' + esc(p) + '</code>').join('<br>');
  const more = dirs.length > 3 ? '<div class="hint">另有 ' + (dirs.length - 3) + ' 个任务目录…</div>' : '';
  const body = '<div class="modal-note"><b>将删除 ' + jobs.length + ' 条任务/日志记录。</b>记录删除后不再显示在“运行队列”和“结果与筛选”里。</div>' +
    '<div class="confirm-summary">' +
      '<div><span>任务编号</span><b>' + jobs.map(j => '#' + j.id).join('、') + '</b></div>' +
      '<div><span>输出根目录</span><code>' + esc(roots.length ? roots.join('；') : '（记录里没有）') + '</code></div>' +
      (dirs.length ? '<div><span>任务目录</span><div>' + previewDirs + more + '</div></div>' : '') +
    '</div>' +
    '<div class="delete-options">' +
      '<label class="delete-option"><input type="checkbox" id="del-cache"' + (hasPaths ? '' : ' disabled') + '>' +
        '<span><b>是否清除本地缓存</b><small>删除任务目录里的 tmp/、*.wfc*、*.mix*、*.save/、__pycache__ 等临时文件；保留 run.log、metrics 和最终输出。</small></span></label>' +
      '<label class="delete-option"><input type="checkbox" id="del-output"' + (hasPaths ? '' : ' disabled') + '>' +
        '<span><b>是否清除输出文件</b><small>删除每个任务自己的任务目录（含日志、输入副本、结构、图和指标）。不会动项目输入目录；勾选后缓存也会一起清除。</small></span></label>' +
    '</div>' +
    '<div class="notice">清理范围严格按任务记录里的 <code>output_root</code> 和 <code>workdir</code> 匹配，因此会遵守你在工具/文件里自定义的输出目录，不会改用当前全局目录误删。</div>' +
    (hasPaths ? (cleanable.length < jobs.length ? '<div class="hint">有 ' + (jobs.length - cleanable.length) + ' 条任务缺少 output_root 或 workdir，只能删除界面记录。</div>' : '') : '<div class="hint">这些任务没有完整目录记录，只能删除界面记录。</div>');
  showModal('删除任务 / 日志记录', body,
    '<button class="btn ghost" id="del-cancel">取消</button>' +
    '<button class="btn danger" id="del-confirm">确认删除</button>');
  $('#del-cancel').onclick = closeModal;
  $('#del-confirm').onclick = async () => {
    const clearCache = !!($('#del-cache') && $('#del-cache').checked);
    const clearOutput = !!($('#del-output') && $('#del-output').checked);
    const btn = $('#del-confirm');
    btn.disabled = true;
    btn.textContent = '删除中…';
    try {
      const d = await api('/api/jobs/delete', { method: 'POST', body: {
        ids: jobs.map(j => j.id), clear_cache: clearCache, clear_outputs: clearOutput,
      }});
      jobs.forEach(j => { state.selectedJobs.delete(j.id); state.selectedResults.delete(j.id); });
      closeModal();
      await refreshJobs();
      await refreshResults();
      const bits = ['已删除 ' + (d.deleted || []).length + ' 条记录'];
      if (d.cache_removed) bits.push('缓存 ' + d.cache_removed + ' 项');
      if (d.outputs_removed) bits.push('输出目录 ' + d.outputs_removed + ' 个');
      if ((d.skipped || []).length) bits.push('跳过 ' + d.skipped.length + ' 条');
      if ((d.errors || []).length) bits.push('失败 ' + d.errors.length + ' 条');
      toast(bits.join(' · '), (d.errors || []).length > 0);
      if ((d.errors || []).length) console.warn('删除任务时的问题', d.errors);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = '确认删除';
      toast(e.message, true);
    }
  };
}

function flatten(obj, prefix = '') {
  const out = {};
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? prefix + '.' + k : k;
    if (v === null || v === undefined) { out[key] = null; continue; }
    if (typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flatten(v, key));
    else if (Array.isArray(v)) out[key] = JSON.stringify(v);
    else out[key] = v;
  }
  return out;
}

async function refreshResults() {
  try {
    const q = state.project ? ('?project_id=' + state.project.id) : '';
    state.results = await api('/api/results' + q);
    renderResults();
  } catch (e) { toast(e.message, true); }
}

function resultRows() {
  return state.results.map(r => ({ ...r, flat: flatten(r.metrics || {}) }));
}

function metricKeys(rows) {
  const keys = new Set();
  rows.forEach(r => Object.keys(r.flat).forEach(k => keys.add(k)));
  return Array.from(keys);
}

function applyFilter(rows) {
  const { key, op, value } = state.filter;
  if (!key || value === '') return rows;
  return rows.filter(r => {
    if (key === 'input_rel') {
      const v = r.input_rel;
      return op === 'contains' ? String(v).includes(value) : String(v) === value;
    }
    const v = r.flat[key];
    if (op === 'contains') return String(v == null ? '' : v).includes(value);
    const n = Number(value);
    if (!isFinite(n) || typeof v !== 'number') return false;
    if (op === 'lt') return v < n;
    if (op === 'le') return v <= n;
    if (op === 'gt') return v > n;
    if (op === 'ge') return v >= n;
    if (op === 'eq') return v === n;
    return true;
  });
}

function renderResults() {
  const all = resultRows();
  const keys = metricKeys(all);
  const sel = $('#filter-key');
  const prev = sel.value;
  sel.innerHTML = '<option value="">选择指标…</option>' +
    '<option value="input_rel">文件名</option>' +
    keys.map(k => '<option value="' + esc(k) + '">' + esc(k) + '</option>').join('');
  if (keys.includes(prev) || prev === 'input_rel') sel.value = prev;
  else if (state.filter.key) sel.value = state.filter.key;

  let rows = applyFilter(all);
  if (state.sort.key) {
    rows = rows.slice().sort((a, b) => {
      const av = state.sort.key === 'input_rel' ? a.input_rel : a.flat[state.sort.key];
      const bv = state.sort.key === 'input_rel' ? b.input_rel : b.flat[state.sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * state.sort.dir;
      return String(av).localeCompare(String(bv)) * state.sort.dir;
    });
  }

  const allIds = new Set(all.map(r => r.id));
  state.selectedResults = new Set(Array.from(state.selectedResults).filter(id => allIds.has(id)));
  const selectedOnPage = rows.filter(r => state.selectedResults.has(r.id)).length;
  const tbody = $('#results-table tbody');
  const thead = $('#results-table thead');
  thead.innerHTML = '<tr>' +
    '<th class="w-check"><input type="checkbox" id="check-all-results" title="全选当前筛选结果"></th>' +
    '<th data-sort="id">#</th>' +
    '<th data-sort="input_rel">文件</th>' +
    '<th data-sort="tool_id">工具</th>' +
    '<th data-sort="status">状态</th>' +
    keys.map(k => '<th data-sort="' + esc(k) + '">' + esc(k) + '</th>').join('') +
    '<th class="w-actions">操作</th>' +
  '</tr>';
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="' + (6 + keys.length) + '" class="empty">还没有完成的任务，或筛选没有命中。</td></tr>';
  } else {
    tbody.innerHTML = rows.map(r => {
      const checked = state.selectedResults.has(r.id);
      return '<tr' + (checked ? ' class="row-selected"' : '') + '>' +
        '<td><input type="checkbox" class="row-check" data-result-check="' + r.id + '"' + (checked ? ' checked' : '') + '></td>' +
        '<td>' + r.id + '</td>' +
        '<td><div class="file-name">' + esc(r.input_rel.split('/').pop()) + '</div></td>' +
        '<td>' + esc(r.tool_id) + '</td>' +
        '<td>' + statusHtml(r.status) + '</td>' +
        keys.map(k => '<td>' + esc(fmt(r.flat[k])) + '</td>').join('') +
        '<td class="job-actions"><button class="btn small ghost" data-result-log="' + r.id + '">日志</button> ' +
          '<button class="btn small danger" data-result-delete="' + r.id + '">删除</button></td>' +
      '</tr>';
    }).join('');
  }
  const checkAll = $('#check-all-results');
  if (checkAll) {
    checkAll.disabled = rows.length === 0;
    checkAll.checked = rows.length > 0 && selectedOnPage === rows.length;
    checkAll.indeterminate = selectedOnPage > 0 && selectedOnPage < rows.length;
    checkAll.onchange = () => {
      if (checkAll.checked) rows.forEach(r => state.selectedResults.add(r.id));
      else rows.forEach(r => state.selectedResults.delete(r.id));
      renderResults();
    };
  }
  const bulk = $('#delete-selected-results');
  if (bulk) {
    bulk.disabled = state.selectedResults.size === 0;
    bulk.textContent = state.selectedResults.size ? '删除选中 (' + state.selectedResults.size + ')' : '删除选中';
  }
  $$('#results-table th[data-sort]').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.sort;
      if (state.sort.key === k) state.sort.dir *= -1;
      else { state.sort.key = k; state.sort.dir = 1; }
      renderResults();
    };
  });
  $('#runs-hint') && ($('#runs-hint').textContent = '共 ' + state.jobs.length + ' 个任务');
}

function exportCsv() {
  const all = resultRows();
  const rows = applyFilter(all);
  const keys = metricKeys(all);
  const header = ['id', 'input_rel', 'tool_id', 'status', ...keys];
  const lines = [header.map(csvCell).join(',')];
  rows.forEach(r => {
    const vals = [r.id, r.input_rel, r.tool_id, r.status, ...keys.map(k => r.flat[k])];
    lines.push(vals.map(csvCell).join(','));
  });
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'mof_results_' + new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-') + '.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function csvCell(v) {
  if (v === null || v === undefined) return '';
  const s = String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function renderTools() {
  const box = $('#tools-grid');
  if (!state.manifests.length) { box.innerHTML = '<div class="empty">没有工具清单。</div>'; return; }
  box.innerHTML = state.manifests.map(m => {
    const vals = defaultsFor(m);
    const out = outputDirFor(m);
    const open = state.expandedManifests.has(m.id);
    return '<div class="tool-card manifest-card" data-tool="' + esc(m.id) + '">' +
      '<button type="button" class="manifest-head" data-manifest-toggle="' + esc(m.id) + '" aria-expanded="' + (open ? 'true' : 'false') + '">' +
        '<div class="tool-top"><div><h3>' + esc(m.name) + '</h3>' +
          '<div class="manifest-sub">' + esc(m.category || 'tool') + ' · 点标题展开参数</div></div>' +
          '<span class="tag">' + esc(m.category || 'tool') + '</span></div>' +
        '<span class="manifest-chev">' + (open ? '▴' : '▾') + '</span>' +
      '</button>' +
      '<div class="manifest-body' + (open ? '' : ' hidden') + '">' +
        '<p class="tool-desc">' + esc(m.description || '') + '</p>' +
        '<div class="tool-meta">接受：' + esc((m.accepts || []).join(' ')) + '</div>' +
        '<div class="tool-meta">参考：' + esc((m.estimate && m.estimate.reference) || '—') + '</div>' +
        '<div class="tool-params-preview">' + paramFields(m, vals, 'tparam') + '</div>' +
        '<div class="output-row small"><label>输出目录' +
          '<div class="path-row"><input data-output-dir="' + esc(m.id) + '" value="' + esc(out) + '">' +
          '<button type="button" class="btn pick" data-pick-output="' + esc(m.id) + '">选择…</button></div></label>' +
          '<span class="hint">' + esc(m.output_note || '这个工具单独保存；点“选择…”可换目录。') + '</span></div>' +
        detailHtml(m) +
        '<div class="tool-actions">' +
          '<button class="btn small ghost" data-save-tool="' + esc(m.id) + '">保存默认</button>' +
          '<button class="btn small primary" data-use-tool="' + esc(m.id) + '">在项目中使用</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
  $$('[data-manifest-toggle]', box).forEach(b => b.onclick = () => {
    const id = b.dataset.manifestToggle;
    const card = b.closest('.tool-card');
    const body = card && card.querySelector('.manifest-body');
    if (!body) return;
    const open = body.classList.toggle('hidden') === false;
    if (open) state.expandedManifests.add(id); else state.expandedManifests.delete(id);
    b.setAttribute('aria-expanded', open ? 'true' : 'false');
    const chev = b.querySelector('.manifest-chev');
    if (chev) chev.textContent = open ? '▴' : '▾';
  });
  $$('[data-save-tool]', box).forEach(b => b.onclick = () => {
    const card = b.closest('.tool-card');
    const vals = readFields(card, 'tparam');
    const outEl = card.querySelector('[data-output-dir]');
    const outVal = outEl ? outEl.value.trim() : '';
    localStorage.setItem('mofui.tool.' + b.dataset.saveTool, JSON.stringify(vals));
    if (outVal) state.outputDirs[b.dataset.saveTool] = outVal;
    localStorage.setItem('mofui.output.' + b.dataset.saveTool, outVal);
    toast('已保存默认参数和输出目录');
  });
  $$('[data-pick-output]', box).forEach(b => b.onclick = () => {
    const card = b.closest('.tool-card');
    const input = card.querySelector('[data-output-dir]');
    chooseDir(input, '选择输出目录');
  });
  $$('[data-output-dir]', box).forEach(el => {
    el.oninput = () => {
      state.outputDirs[el.dataset.outputDir] = el.value.trim();
      localStorage.setItem('mofui.output.' + el.dataset.outputDir, el.value.trim());
    };
  });
  $$('[data-use-tool]', box).forEach(b => b.onclick = () => {
    const m = state.manifests.find(x => x.id === b.dataset.useTool);
    state.toolId = m.id;
    state.params = defaultsFor(m);
    localStorage.setItem('mofui.tool.' + m.id, JSON.stringify(state.params));
    renderToolSelect();
    renderToolParams();
    switchView('projects');
    if (!state.project) toast('这个工具已选中；再选择项目即可使用');
  });
}

async function renderSettings() {
  try {
    const d = await api('/api/tools');
    state.tools = d.items || [];
    $('#settings-test').innerHTML = '';
    $('#settings-cards').innerHTML = state.tools.map(t => {
      const open = state.expandedTools && state.expandedTools.has(t.id);
      const path = t.path || '未设置';
      const version = t.exists ? (t.version || '已找到') : (t.optional ? '未安装（可选）' : '未找到');
      const vclass = t.exists ? 'ok' : (t.optional ? 'optional' : 'bad');
      return '<div class="tool-card" data-tool-id="' + esc(t.id) + '">' +
        '<button type="button" class="tool-card-head" data-tool-toggle="' + esc(t.id) + '">' +
          '<span class="tool-card-name">' + esc(t.label) + '</span>' +
          '<span class="tool-card-version ' + vclass + '">' + esc(version) + '</span>' +
          '<span class="tool-card-chev">' + (open ? '▴' : '▾') + '</span>' +
        '</button>' +
        '<div class="tool-card-body ' + (open ? '' : 'hidden') + '">' +
          '<div class="tool-path-line"><span>本地路径</span><code>' + esc(path) + '</code></div>' +
          '<div class="path-row"><input data-setting="' + esc(t.key) + '" value="' + esc(t.path || '') + '">' +
            '<button type="button" class="btn pick" data-pick-kind="' + esc(t.pick) + '" data-pick-target="' + esc(t.key) + '" data-pick-title="选择' + esc(t.label) + '">更改路径</button></div>' +
          '<div class="tool-card-actions">' +
            '<button type="button" class="btn small" data-detect="' + esc(t.id) + '">自动检测</button>' +
            '<button type="button" class="btn small ghost" data-download="' + esc(t.id) + '"' + (t.download ? '' : ' disabled') + '>下载</button>' +
            (t.source ? '<span class="tool-source">' + esc(t.source) + '</span>' : '') +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');
    $$('[data-tool-toggle]').forEach(b => b.onclick = () => {
      const id = b.dataset.toolToggle;
      if (!state.expandedTools) state.expandedTools = new Set();
      const card = b.closest('.tool-card');
      const body = card && card.querySelector('.tool-card-body');
      if (!body) return;
      const open = body.classList.toggle('hidden') === false;
      if (open) state.expandedTools.add(id); else state.expandedTools.delete(id);
      const chev = b.querySelector('.tool-card-chev');
      if (chev) chev.textContent = open ? '▴' : '▾';
    });
    $$('[data-pick-kind]', $('#settings-cards')).forEach(b => b.onclick = () => pickPath(b.dataset.pickKind, b.dataset.pickTarget, b.dataset.pickTitle));
    $$('[data-detect]', $('#settings-cards')).forEach(b => b.onclick = () => detectTool(b.dataset.detect));
    $$('[data-download]', $('#settings-cards')).forEach(b => b.onclick = () => downloadTool(b.dataset.download));
  } catch (e) { toast(e.message, true); }
}

async function detectTool(id) {
  try {
    const d = await api('/api/tools/detect', { method: 'POST', body: { id } });
    toast(d.message || '已自动检测', false, 2000);
    await loadCore();
    await renderSettings();
  } catch (e) { toast(e.message, true, 2000); }
}

async function downloadTool(id) {
  try {
    const d = await api('/api/tools/download', { method: 'POST', body: { id } });
    toast(d.message || '已开始下载', !d.ok, 2000);
    if (d.url) window.open(d.url, '_blank', 'noopener');
  } catch (e) { toast(e.message, true, 2000); }
}

async function pickPath(kind, target, title) {
  try {
    toast('已打开系统选择框，请在弹出的窗口里选择…');
    const d = await api('/api/pick-path', { method: 'POST', body: { kind, title } });
    if (d.cancelled) { toast('已取消选择'); return; }
    const el = document.querySelector('[data-setting="' + target + '"]') || document.getElementById(target);
    if (!el) { toast('找不到要填入的输入框', true); return; }
    el.value = d.path;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    toast('已选择：' + d.path);
  } catch (e) { toast(e.message, true); }
}

async function saveSettings() {
  const body = {};
  $$('[data-setting]').forEach(el => { body[el.dataset.setting] = el.value.trim(); });
  try {
    state.settings = await api('/api/settings', { method: 'POST', body });
    toast('设置已保存');
  } catch (e) { toast(e.message, true); }
}

async function testSettings() {
  try {
    const d = await api('/api/settings/test', { method: 'POST', body: {} });
    $('#settings-test').innerHTML = d.results.map(r => {
      const cls = r.ok ? 'ok' : (r.optional ? 'optional' : 'bad');
      const mark = r.ok ? '✓' : (r.optional ? '–' : '×');
      return '<div class="test-row"><span class="mark ' + cls + '">' + mark + '</span>' +
        '<b>' + esc(r.label) + '</b><code>' + esc(r.path || '未设置') + '</code></div>';
    }).join('');
  } catch (e) { toast(e.message, true); }
}

async function loadCore() {
  const [settings, manifests, projects, system] = await Promise.all([
    api('/api/settings'), api('/api/manifests'), api('/api/projects'), api('/api/system'),
  ]);
  state.settings = settings;
  state.manifests = manifests;
  state.projects = projects;
  state.system = system;
  loadOutputDirs();
  if (!state.toolId && manifests.length) {
    state.toolId = manifests[0].id;
    state.params = defaultsFor(manifests[0]);
  }
  renderProjects();
  renderToolSelect();
  renderToolParams();
  renderSettings();
  if (!state.project && projects.length) selectProject(projects[0].id);
}

function updateServer(ok) {
  const dot = $('#server-dot');
  dot.className = 'dot ' + (ok ? 'ok' : 'bad');
  $('#server-text').textContent = ok ? '本地服务在线' : '服务断开';
}

function bind() {
  const skinBtn = $('#skin-toggle');
  if (skinBtn) skinBtn.onclick = (e) => {
    e.stopPropagation();
    const menu = $('#skin-menu');
    const open = menu.classList.toggle('hidden') === false;
    skinBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  $$('.skin-option').forEach(b => b.onclick = (e) => {
    e.stopPropagation();
    applySkin(b.dataset.skin);
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.skin-picker')) closeSkinMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSkinMenu();
  });
  window.addEventListener('pointermove', (e) => {
    ambient.mouse.x = e.clientX;
    ambient.mouse.y = e.clientY;
    ambient.mouse.inside = true;
    // Create/update immediately; don't wait for the frame budget throttle.
    if (ambient.mode) {
      ambient.boostUntil = performance.now() + 300;
      ambient.spawnMouse(e.clientX, e.clientY, performance.now());
    }
  }, { passive: true });
  document.documentElement.addEventListener('mouseleave', () => { ambient.mouse.inside = false; });
  window.addEventListener('resize', () => { if (ambient.mode) ambient.resize(); });
  $$('.nav-item').forEach(b => b.onclick = () => switchView(b.dataset.view));
  $$('[data-jump]').forEach(b => b.onclick = () => switchView(b.dataset.jump));
  $$('[data-pick-kind]').forEach(b => b.onclick = () => pickPath(b.dataset.pickKind, b.dataset.pickTarget, b.dataset.pickTitle));
  $('#project-form').onsubmit = createProject;
  $('#scan-btn').onclick = scanProject;
  $('#run-selected').onclick = runSelected;
  $('#check-all').onclick = (e) => toggleAll(e.target.checked);
  $('#tool-select').onchange = (e) => {
    state.toolId = e.target.value;
    const m = manifest();
    state.params = m ? defaultsFor(m) : {};
    renderToolParams();
    renderFiles();
  };
  $('#tool-params-btn').onclick = () => {
    const p = $('#tool-params');
    p.classList.toggle('hidden');
    if (!p.classList.contains('hidden')) renderToolParams();
  };
  $('#tutorial-select').onchange = (e) => loadTutorial(e.target.value).catch(err => toast(err.message, true));
  $('#refresh-all').onclick = async () => {
    try { await loadCore(); await refreshJobs(); await refreshResults(); toast('已刷新'); }
    catch (e) { toast(e.message, true); }
  };
  $('#modal-close').onclick = closeModal;
  $('#modal').onclick = (e) => { if (e.target.id === 'modal') closeModal(); };
  $('#save-settings').onclick = saveSettings;
  $('#test-settings').onclick = testSettings;
  $('#apply-filter').onclick = () => {
    state.filter = { key: $('#filter-key').value, op: $('#filter-op').value, value: $('#filter-value').value.trim() };
    renderResults();
  };
  $('#clear-filter').onclick = () => {
    state.filter = { key: '', op: 'lt', value: '' };
    $('#filter-value').value = '';
    $('#filter-key').value = '';
    renderResults();
  };
  $('#export-csv').onclick = exportCsv;
  $('#start-queue').onclick = startQueue;
  $('#check-all-jobs').onchange = (e) => {
    const ids = state.jobs.filter(canDeleteJob).map(j => j.id);
    state.selectedJobs = new Set(e.target.checked ? ids : []);
    renderJobs();
  };
  $('#delete-selected-jobs').onclick = () => openDeleteJobs(Array.from(state.selectedJobs), 'runs');
  $('#delete-selected-results').onclick = () => openDeleteJobs(Array.from(state.selectedResults), 'results');

  const tbody = $('#files-table tbody');
  tbody.onchange = (e) => {
    const rel = e.target.dataset.check;
    if (!rel) return;
    if (e.target.checked) state.selected.add(rel); else state.selected.delete(rel);
    renderEstimateBar();
  };
  tbody.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.params) openParams(b.dataset.params);
    if (b.dataset.run) {
      const f = state.files.find(x => x.rel === b.dataset.run);
      if (f) runFiles([f]);
    }
  };
  const jbody = $('#jobs-table tbody');
  jbody.onchange = (e) => {
    const id = Number(e.target.dataset.jobCheck);
    if (!id) return;
    if (e.target.checked) state.selectedJobs.add(id); else state.selectedJobs.delete(id);
    renderJobs();
  };
  jbody.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.log) openLog(Number(b.dataset.log));
    if (b.dataset.cancel) cancelJob(Number(b.dataset.cancel), b.dataset.status);
    if (b.dataset.rerun) rerunJob(Number(b.dataset.rerun));
    if (b.dataset.resume) resumeJob(Number(b.dataset.resume));
    if (b.dataset.move) moveJob(Number(b.dataset.move), b.dataset.dir);
    if (b.dataset.deleteJob) openDeleteJobs([Number(b.dataset.deleteJob)], 'runs');
  };
  const rbody = $('#results-table tbody');
  rbody.onchange = (e) => {
    const id = Number(e.target.dataset.resultCheck);
    if (!id) return;
    if (e.target.checked) state.selectedResults.add(id); else state.selectedResults.delete(id);
    renderResults();
  };
  rbody.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.resultLog) openLog(Number(b.dataset.resultLog), 'results');
    if (b.dataset.resultDelete) openDeleteJobs([Number(b.dataset.resultDelete)], 'results');
  };
}

async function boot() {
  applySkin(state.skin, false);
  bind();
  try {
    await loadCore();
    updateServer(true);
    await refreshJobs();
    await refreshResults();
    await loadTutorial('README.md');
  } catch (e) {
    updateServer(false);
    toast('初始化失败：' + e.message, true);
  }
  setInterval(async () => {
    try { await refreshJobs(); updateServer(true); } catch (e) { updateServer(false); }
  }, 2500);
}

document.addEventListener('DOMContentLoaded', boot);
