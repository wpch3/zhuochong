/* zrig editor/binder prototype: pure local data operations, not Cubism. */
(function (global) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const finite = (value, label) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(label + '必须是有限数字');
    return value;
  };
  // Group alpha is silently ignored by the C engine; do not offer dead binds.
  const channels = new Set(['dx', 'dy', 'sx', 'sy', 'rot_deg']);
  // Built-ins are created before loading JSON and cannot be redeclared.
  const builtin = new Set(['ParamAngleX', 'ParamAngleY', 'ParamEyeOpen', 'ParamEyeLOpen', 'ParamEyeROpen',
    'ParamEyeLSmile', 'ParamEyeRSmile', 'ParamEyeLPain', 'ParamEyeRPain', 'ParamEyeLWide', 'ParamEyeRWide',
    'ParamEyeBallX', 'ParamEyeBallY']);
  class Session {
    constructor(rig) {
      if (!rig || typeof rig !== 'object' || Array.isArray(rig) ||
          !Array.isArray(rig.parts) || !rig.groups || typeof rig.groups !== 'object' || Array.isArray(rig.groups) ||
          !Array.isArray(rig.params)) throw new Error('需要含 parts、groups、params 的 zrig JSON');
      if (rig.parts.some(p => !p || typeof p !== 'object' || typeof p.id !== 'string' || typeof p.file !== 'string' ||
          (p.tags !== undefined && !Array.isArray(p.tags))) ||
          rig.params.some(p => !p || typeof p !== 'object' || typeof p.id !== 'string') ||
          (rig.deformers !== undefined && (!Array.isArray(rig.deformers) || rig.deformers.some(d => !d || typeof d !== 'object' || Array.isArray(d)))) ||
          (rig.xfades !== undefined && (!Array.isArray(rig.xfades) || rig.xfades.some(f => !f || typeof f !== 'object')))) {
        throw new Error('部件、参数、形变器或交叉淡化结构有误');
      }
      this.rig = clone(rig);
      this.history = [];
      this.future = [];
    }
    change(fn) {
      const next = clone(this.rig);
      fn(next); // transaction: no mutation on validation error
      this.history.push(this.rig);
      if (this.history.length > 100) this.history.shift();
      this.rig = next;
      this.future = [];
    }
    undo() {
      if (!this.history.length) return false;
      this.future.push(this.rig); this.rig = this.history.pop(); return true;
    }
    redo() {
      if (!this.future.length) return false;
      this.history.push(this.rig); this.rig = this.future.pop(); return true;
    }
    setPart(id, x, y, layer) {
      finite(x, 'X'); finite(y, 'Y'); finite(layer, '层号');
      if (!Number.isInteger(layer)) throw new Error('层号必须为整数');
      this.change(r => {
        const p = r.parts.find(item => item.id === id);
        if (!p) throw new Error('部件不存在');
        if (p.socket) throw new Error('挂点部件的位置由 socket 决定，当前工具不能编辑');
        p.pos = [x, y]; p.layer = layer;
      });
    }
    addParameter(id, label, min, max, value) {
      if (typeof id !== 'string' || !/^Param[A-Za-z0-9_]{1,34}$/.test(id)) throw new Error('参数 ID 须为 Param 开头的英文、数字或下划线');
      if (builtin.has(id)) throw new Error('参数 ID 已由 C 引擎内建，不能重复声明');
      if (typeof label !== 'string') throw new Error('标签必须是文本');
      finite(min, '最小值'); finite(max, '最大值'); finite(value, '默认值');
      if (min >= max || value < min || value > max) throw new Error('需要最小值 < 最大值，默认值在范围内');
      this.change(r => {
        if (r.params.some(p => p.id === id)) throw new Error('参数 ID 已存在');
        r.params.push({id, label, min, max, default: value, binds: []});
      });
    }
    addGroupBind(id, group, channel, scale, offset) {
      finite(scale, '倍率'); finite(offset, '偏移');
      if (!channels.has(channel)) throw new Error('不支持的组通道');
      this.change(r => {
        const param = r.params.find(p => p.id === id);
        if (!param) throw new Error('参数不存在');
        if (!Object.prototype.hasOwnProperty.call(r.groups, group)) throw new Error('组不存在');
        if (param.binds !== undefined && !Array.isArray(param.binds)) throw new Error('参数 binds 不是数组');
        if (!param.binds) param.binds = [];
        param.binds.push({group, param: channel, scale, offset});
      });
    }
    addKeyform(id, partId, paramId, cols, rows) {
      if (typeof id !== 'string' || !/^[A-Za-z][A-Za-z0-9_]{0,46}$/.test(id)) throw new Error('形变器 ID 须为不超过 47 位英文、数字或下划线');
      if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols < 1 || rows < 1 || cols > 16 || rows > 16) throw new Error('网格行列必须为 1 至 16 的整数');
      this.change(r => {
        const part = r.parts.find(p => p.id === partId);
        const param = r.params.find(p => p.id === paramId);
        if (!part) throw new Error('部件不存在');
        if (part.deformer) throw new Error('部件已挂接形变器；当前工具不支持叠加');
        if (!param || ![param.min, param.max, param.default].every(Number.isFinite) || param.min >= param.max || param.default < param.min || param.default > param.max) throw new Error('参数不存在或范围无效');
        if (r.deformers !== undefined && !Array.isArray(r.deformers)) throw new Error('形变器不是数组');
        if (!r.deformers) r.deformers = [];
        if (r.deformers.length >= 80) throw new Error('达到 C 引擎形变器上限');
        if (r.parts.some(p => p.id === id) || Object.prototype.hasOwnProperty.call(r.groups, id) || r.deformers.some(d => d.id === id)) throw new Error('形变器 ID 与已有对象重复');
        // Conservatively avoid combining with existing weighted or differently
        // sized meshes; advanced multi-mesh editing is not supported here.
        if (r.deformers.some(d => d.part === partId)) throw new Error('该部件已有网格；当前工具不支持叠加');
        const values = [...new Set([param.min, param.default, param.max])].sort((a, b) => a - b);
        r.deformers.push({id, part: partId, cols, rows, param: paramId, keys: values.map(v => ({v, points: []}))});
      });
    }
    setKeyformPoint(id, value, column, row, dx, dy) {
      finite(value, '关键值'); finite(dx, 'X 位移'); finite(dy, 'Y 位移');
      if (!Number.isInteger(column) || !Number.isInteger(row)) throw new Error('控制点行列须为整数');
      this.change(r => {
        const d = (r.deformers || []).find(item => item.id === id);
        if (!d || !Array.isArray(d.keys) || !Number.isInteger(d.cols) || !Number.isInteger(d.rows)) throw new Error('关键形态网格不存在');
        if (column < 0 || column > d.cols || row < 0 || row > d.rows) throw new Error('控制点越界');
        const key = d.keys.find(k => k.v === value);
        if (!key || !Array.isArray(key.points)) throw new Error('关键值不存在或不是可编辑形态');
        key.points = key.points.filter(p => !(p.c === column && p.r === row));
        if (dx !== 0 || dy !== 0) key.points.push({c: column, r: row, dx, dy});
      });
    }
    removeBind(id, index) {
      this.change(r => {
        const p = r.params.find(item => item.id === id);
        if (!p || !Array.isArray(p.binds) || !Number.isInteger(index) || index < 0 || index >= p.binds.length) throw new Error('绑定不存在');
        p.binds.splice(index, 1);
      });
    }
    serialize() { return JSON.stringify(this.rig, null, 2) + '\n'; }
  }
  const api = { Session };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.ZRigEditor = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
