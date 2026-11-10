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
  // Coordinates are a static authoring approximation: keyframe offsets are
  // in source-image pixels, before the part's scale and rotation.
  function meshPoints(part, image, rig, mesh, value, preview) {
    if (!part || !image || !mesh || mesh.part !== part.id || part.socket || part.deformer || part.inherit_from ||
        mesh.parent || mesh.w || mesh.chain_w || !Number.isInteger(mesh.cols) || !Number.isInteger(mesh.rows) ||
        mesh.cols < 1 || mesh.rows < 1 || mesh.cols > 16 || mesh.rows > 16 || !Array.isArray(mesh.keys)) return null;
    const key = mesh.keys.find(k => k && k.v === value);
    const g = geometry(part, image, rig);
    if (!key || !Array.isArray(key.points) || !g) return null;
    const scaleX = g.w / image.width, scaleY = g.h / image.height;
    const cos = Math.cos(g.angle), sin = Math.sin(g.angle), result = [];
    for (let row = 0; row <= mesh.rows; row++) for (let col = 0; col <= mesh.cols; col++) {
      const stored = key.points.find(p => p && p.c === col && p.r === row) || {};
      const offset = preview && preview.c === col && preview.r === row ? preview : stored;
      const dx = offset.dx ?? 0, dy = offset.dy ?? 0;
      if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null;
      const x = (image.width * col / mesh.cols + dx) * scaleX - g.ax;
      const y = (image.height * row / mesh.rows + dy) * scaleY - g.ay;
      result.push({c:col, r:row, dx, dy, x:g.x + x*cos - y*sin, y:g.y + x*sin + y*cos});
    }
    return result;
  }
  function sourceDelta(g, image, dx, dy) {
    const cos = Math.cos(g.angle), sin = Math.sin(g.angle);
    return [(dx*cos + dy*sin) / (g.w / image.width), (-dx*sin + dy*cos) / (g.h / image.height)];
  }
  class Viewport {
    constructor(canvas, onMove, onStatus, onMeshMove = () => {}, onGroupMove = () => {}) {
      this.canvas = canvas; this.ctx = canvas.getContext('2d');
      this.onMove = onMove; this.onStatus = onStatus; this.onMeshMove = onMeshMove; this.onGroupMove = onGroupMove;
      this.images = new Map(); this.rig = null; this.drag = null; this.meshMode = false;
      this.loadToken = 0;
      canvas.addEventListener('pointerdown', e => this.start(e));
      canvas.addEventListener('pointermove', e => this.move(e));
      canvas.addEventListener('pointerup', e => this.finish(e));
      canvas.addEventListener('pointercancel', e => {
        if (this.drag && this.drag.pointerId === e.pointerId) { this.drag = null; this.draw(); }
      });
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
    setMesh(id, value, enabled) {
      this.meshId = id; this.meshValue = value; this.meshMode = enabled;
      this.drag = null; this.draw();
    }
    setGroup(id, enabled) { this.groupId = id; this.groupMode = enabled; this.drag = null; this.draw(); }
    groupPoints() {
      const origin = this.rig.origin || [this.rig.canvas.w * .5, this.rig.canvas.h];
      const groups = {root: {pivot: origin}, ...this.rig.groups};
      const points = {};
      for (const [id, g] of Object.entries(groups)) {
        if (!g || typeof g !== 'object') continue;
        const p = g.pivot || origin;
        if (!Array.isArray(p) || p.length !== 2 || !p.every(Number.isFinite)) continue;
        points[id] = this.drag && this.drag.kind === 'group' && this.drag.id === id ? this.drag.pos : p;
      }
      return {groups, points};
    }
    meshContext() {
      if (!this.rig || !this.meshMode || !Number.isFinite(this.meshValue)) return null;
      const mesh = (this.rig.deformers || []).find(d => d && d.id === this.meshId);
      const part = this.rig.parts.find(p => p.id === this.selected);
      const image = part && this.images.get(part.file);
      const preview = this.drag && this.drag.kind === 'mesh' ? this.drag.offset : null;
      const points = meshPoints(part, image, this.rig, mesh, this.meshValue, preview);
      return points ? {mesh, part, image, points} : null;
    }
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
        const override = this.drag && this.drag.kind === 'part' && this.drag.id === p.id ? this.drag.pos : null;
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
      if (this.groupMode) {
        const {groups, points} = this.groupPoints();
        c.save(); c.lineWidth = Math.max(2, this.canvas.width / 500); c.strokeStyle = '#007b86';
        c.beginPath();
        for (const [id, group] of Object.entries(groups)) {
          if (group && points[id] && points[group.parent]) { c.moveTo(...points[id]); c.lineTo(...points[group.parent]); }
        }
        c.stroke();
        for (const [id, point] of Object.entries(points)) {
          c.beginPath(); c.arc(point[0], point[1], id === this.groupId ? 9 : 5, 0, 2*Math.PI);
          c.fillStyle = id === this.groupId ? '#ef704b' : '#007b86'; c.fill();
        }
        c.restore();
      }
      const grid = this.meshContext();
      if (grid) {
        const {mesh, points} = grid, at = (c, r) => points[r * (mesh.cols + 1) + c];
        c.save(); c.lineWidth = Math.max(2, this.canvas.width / 500); c.strokeStyle = '#008d80';
        c.beginPath();
        for (let row = 0; row <= mesh.rows; row++) for (let col = 0; col < mesh.cols; col++) {
          const a = at(col, row), b = at(col + 1, row); c.moveTo(a.x, a.y); c.lineTo(b.x, b.y);
        }
        for (let col = 0; col <= mesh.cols; col++) for (let row = 0; row < mesh.rows; row++) {
          const a = at(col, row), b = at(col, row + 1); c.moveTo(a.x, a.y); c.lineTo(b.x, b.y);
        }
        c.stroke(); c.fillStyle = '#ed7549';
        for (const point of points) { c.beginPath(); c.arc(point.x, point.y, Math.max(5, this.canvas.width / 180), 0, 2*Math.PI); c.fill(); }
        c.restore();
      }
    }
    start(e) {
      if (!this.rig || this.drag || e.button !== 0) return;
      if (this.groupMode) {
        const point = this.position(e), pos = this.groupPoints().points[this.groupId];
        if (!pos || this.groupId === 'root') return;
        const rect = this.canvas.getBoundingClientRect();
        const radius = Math.max(this.canvas.width / rect.width, this.canvas.height / rect.height) * 12;
        if (Math.hypot(point[0]-pos[0], point[1]-pos[1]) > radius) return;
        this.drag = {kind:'group', pointerId:e.pointerId, id:this.groupId, from:point, initial:[...pos], pos:[...pos]};
        this.canvas.setPointerCapture(e.pointerId); e.preventDefault(); return;
      }
      if (this.meshMode) {
        const context = this.meshContext();
        if (!context) { this.onStatus('网格不可编辑：请选择匹配部件、有效关键值和已加载素材；复杂权重/链/挂点不支持。'); return; }
        const p = this.position(e), rect = this.canvas.getBoundingClientRect();
        const radius = Math.max(this.canvas.width / rect.width, this.canvas.height / rect.height) * 12;
        const hit = context.points.reduce((best, point) => {
          const dist = Math.hypot(point.x - p[0], point.y - p[1]);
          return dist <= radius && (!best || dist < best.dist) ? {point, dist} : best;
        }, null);
        if (!hit) return;
        this.drag = {kind:'mesh', pointerId:e.pointerId, from:p, mesh:context.mesh.id, value:this.meshValue,
                     part:context.part, image:context.image, offset:{c:hit.point.c, r:hit.point.r, dx:hit.point.dx, dy:hit.point.dy},
                     initial:[hit.point.dx, hit.point.dy]};
        this.canvas.setPointerCapture(e.pointerId); e.preventDefault(); return;
      }
      const p = this.rig.parts.find(p => p.id === this.selected);
      const image = p && this.images.get(p.file);
      if (!p || !image || p.socket) return;
      const g = geometry(p, image, this.rig); const point = this.position(e);
      if (!g || !contains(g, ...point)) return;
      this.drag = {kind:'part', pointerId:e.pointerId, id: p.id, from: point, initial: [g.x, g.y], pos: [g.x, g.y], layer: p.layer || 0};
      this.canvas.setPointerCapture(e.pointerId); e.preventDefault();
    }
    move(e) {
      if (!this.drag) return;
      if (e.pointerId !== this.drag.pointerId) return;
      const p = this.position(e);
      if (this.drag.kind === 'mesh') {
        const d = this.drag, g = geometry(d.part, d.image, this.rig);
        const delta = sourceDelta(g, d.image, p[0] - d.from[0], p[1] - d.from[1]);
        d.offset.dx = d.initial[0] + delta[0]; d.offset.dy = d.initial[1] + delta[1];
      } else {
        this.drag.pos = [this.drag.initial[0] + p[0] - this.drag.from[0], this.drag.initial[1] + p[1] - this.drag.from[1]];
      }
      this.draw();
    }
    finish(e) {
      if (!this.drag || e.pointerId !== this.drag.pointerId) return;
      const d = this.drag; this.drag = null;
      if (d.kind === 'mesh') {
        if (Math.hypot(d.offset.dx-d.initial[0], d.offset.dy-d.initial[1]) > .01)
          this.onMeshMove(d.mesh, d.value, d.offset.c, d.offset.r, d.offset.dx, d.offset.dy);
      } else if (Math.hypot(d.pos[0]-d.initial[0], d.pos[1]-d.initial[1]) > .25) {
        if (d.kind === 'group') this.onGroupMove(d.id, d.pos);
        else this.onMove(d.id, d.pos, d.layer);
      }
      this.draw();
    }
  }
  const api = {safePath, geometry, visible, contains, meshPoints, sourceDelta, Viewport};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.ZRigViewport = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
