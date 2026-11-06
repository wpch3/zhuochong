/* Approximate, static authoring view; the C engine remains the rendering authority. */
(function (global) {
  'use strict';
  function safePath(path) {
    if (typeof path !== 'string' || !path || path.startsWith('/') || path.includes('\\') ||
        path.split('/').some(p => p === '..' || p === '.' || !p)) throw new Error('不安全的素材相对路径');
    return path;
  }
  function geometry(part, image, rig, override) {
    const anchor = Array.isArray(part.anchor) ? part.anchor : [.5, .5];
    const scale = Array.isArray(part.scale) ? part.scale : [part.scale ?? 1, part.scale ?? 1];
    const pos = override || part.pos || rig.origin || [0, 0];
    const w = image.width * scale[0], h = image.height * scale[1];
    if (![...anchor, ...scale, ...pos, w, h, part.rot_deg ?? 0].every(Number.isFinite) || w <= 0 || h <= 0) return null;
    return {x: pos[0], y: pos[1], w, h, ax: anchor[0] * w, ay: anchor[1] * h,
            angle: (part.rot_deg || 0) * Math.PI / 180};
  }
  function visible(rig) {
    const hidden = new Set();
    for (const p of rig.parts) if ((p.tags || []).includes('eye_closed')) hidden.add(p.id);
    for (const fade of rig.xfades || []) {
      const q = (rig.params || []).find(p => p.id === fade.param);
      const val = q && Number.isFinite(q.default) ? q.default : 0;
      if (Array.isArray(fade.in) && fade.in[0] === val) hidden.add(fade.to);
      else if (Array.isArray(fade.in) && fade.in[1] === val) hidden.add(fade.from);
    }
    return rig.parts.map((p, i) => ({p, i})).filter(({p}) => !hidden.has(p.id))
      .sort((a, b) => (a.p.layer || 0) - (b.p.layer || 0) || a.i - b.i).map(({p}) => p);
  }
  function contains(g, x, y) {
    const c = Math.cos(g.angle), s = Math.sin(g.angle), dx = x - g.x, dy = y - g.y;
    const lx = dx*c + dy*s + g.ax, ly = -dx*s + dy*c + g.ay;
    return lx >= 0 && ly >= 0 && lx <= g.w && ly <= g.h;
  }
  class Viewport {
    constructor(canvas, onMove, onStatus) {
      this.canvas = canvas; this.ctx = canvas.getContext('2d');
      this.onMove = onMove; this.onStatus = onStatus; this.images = new Map(); this.rig = null; this.drag = null;
      this.loadToken = 0;
      canvas.addEventListener('pointerdown', e => this.start(e));
      canvas.addEventListener('pointermove', e => this.move(e));
      canvas.addEventListener('pointerup', e => this.finish(e));
      canvas.addEventListener('pointercancel', () => { this.drag = null; this.draw(); });
    }
    setRig(rig, clearImages) {
      const w = rig.canvas?.w, h = rig.canvas?.h;
      if (!Number.isInteger(w) || !Number.isInteger(h) || w < 1 || h < 1 || w > 4096 || h > 4096) throw new Error('画布宽高须为 1 至 4096 的整数');
      this.rig = rig; this.drag = null;
      if (clearImages) { this.loadToken++; this.images.clear(); }
      if (this.canvas.width !== w) this.canvas.width = w;
      if (this.canvas.height !== h) this.canvas.height = h;
      this.draw();
    }
    setSelection(id) { this.selected = id; this.draw(); }
    async loadFiles(files) {
      if (!this.rig) throw new Error('请先载入 rig');
      const token = ++this.loadToken;
      const candidate = new Map();
      for (const part of this.rig.parts) {
        const path = safePath(part.file);
        const matches = Array.from(files).filter(f => {
          const relative = (f.webkitRelativePath || f.name).replace(/\\/g, '/');
          return relative === path || relative.endsWith('/' + path);
        });
        if (matches.length > 1) throw new Error('素材路径有多个匹配：' + path);
        if (!matches.length) continue;
        const url = URL.createObjectURL(matches[0]);
        try { candidate.set(path, await this.decode(url)); } finally { URL.revokeObjectURL(url); }
      }
      if (token !== this.loadToken) return;
      this.images = candidate; this.draw();
      this.onStatus('本地素材已载入 ' + candidate.size + ' 项；缺少 ' + this.missing() + ' 项。');
    }
    async loadDemo() {
      if (!this.rig) throw new Error('请先载入示例');
      const token = ++this.loadToken;
      const candidate = new Map();
      for (const part of this.rig.parts) {
        const path = safePath(part.file);
        if (!candidate.has(path)) candidate.set(path, await this.decode('demo/' + path));
      }
      if (token !== this.loadToken) return;
      this.images = candidate; this.draw();
      this.onStatus('示例贴图已载入；这是静态近似预览，不是 C 引擎帧。');
    }
    decode(url) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('贴图读取失败')); image.src = url; }); }
    missing() { return new Set(this.rig.parts.map(p => p.file).filter(f => !this.images.has(f))).size; }
    position(e) {
      const r = this.canvas.getBoundingClientRect();
      return [(e.clientX-r.left)*this.canvas.width/r.width, (e.clientY-r.top)*this.canvas.height/r.height];
    }
    draw() {
      if (!this.rig) return;
      const c = this.ctx; c.clearRect(0, 0, this.canvas.width, this.canvas.height);
      let selection = null;
      for (const p of visible(this.rig)) {
        const image = this.images.get(p.file); if (!image) continue;
        const override = this.drag && this.drag.id === p.id ? this.drag.pos : null;
        const g = geometry(p, image, this.rig, override); if (!g) continue;
        c.save(); c.translate(g.x, g.y); c.rotate(g.angle); c.globalAlpha = Math.max(0, Math.min(1, p.opacity ?? 1));
        c.drawImage(image, -g.ax, -g.ay, g.w, g.h); c.restore();
        if (p.id === this.selected) selection = g;
      }
      if (selection) {
        c.save(); c.translate(selection.x, selection.y); c.rotate(selection.angle);
        c.lineWidth = Math.max(2, this.canvas.width/500); c.strokeStyle = '#ff6f4c';
        c.setLineDash([10, 7]); c.strokeRect(-selection.ax, -selection.ay, selection.w, selection.h);
        c.setLineDash([]); c.beginPath(); c.arc(0, 0, 5, 0, 2*Math.PI); c.fillStyle = '#ff6f4c'; c.fill(); c.restore();
      }
    }
    start(e) {
      if (!this.rig || e.button !== 0) return;
      const p = this.rig.parts.find(p => p.id === this.selected);
      const image = p && this.images.get(p.file);
      if (!p || !image || p.socket) return;
      const g = geometry(p, image, this.rig); const point = this.position(e);
      if (!g || !contains(g, ...point)) return;
      this.drag = {id: p.id, from: point, initial: [g.x, g.y], pos: [g.x, g.y], layer: p.layer || 0};
      this.canvas.setPointerCapture(e.pointerId); e.preventDefault();
    }
    move(e) {
      if (!this.drag) return;
      const p = this.position(e);
      this.drag.pos = [this.drag.initial[0] + p[0] - this.drag.from[0], this.drag.initial[1] + p[1] - this.drag.from[1]];
      this.draw();
    }
    finish() {
      if (!this.drag) return;
      const d = this.drag; this.drag = null;
      if (Math.hypot(d.pos[0]-d.initial[0], d.pos[1]-d.initial[1]) > .25) this.onMove(d.id, d.pos, d.layer);
      this.draw();
    }
  }
  const api = {safePath, geometry, visible, contains, Viewport};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.ZRigViewport = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
