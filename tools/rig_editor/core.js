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
