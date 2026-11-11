(() => {
  const dataRoot = '/media/characters/xiaoxun/design/loli_live2d_v1/cubism_source/face_pass_01/';
  const canvas = document.querySelector('#artboard');
  const ctx = canvas.getContext('2d');
  const loader = document.querySelector('#canvas-loader');
  const list = document.querySelector('#layer-list');
  const state = { layers: [], selected: 'Base_Face_Underpaint_WIP', reference: null, referenceOn: false, opacity: .45, isolate: false, checker: true };
  const images = new Map();
  const offsets = new Map();
  const visible = new Map();
  let base = null;
  let dragging = null;
  let dragStart = null;

  const loadImage = (url) => new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`无法读取图像：${url}`));
    img.src = url;
  });

  async function init() {
    try {
      const res = await fetch(`${dataRoot}layer_manifest.json`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`图层清单读取失败（HTTP ${res.status}）`);
      const manifest = await res.json();
      base = await loadImage(dataRoot + manifest.base_layer.file);
      state.reference = await loadImage(dataRoot + 'reference_front_848x1360.png');
      state.layers = manifest.parts.map(x => ({...x, image: null}));
      for (const layer of state.layers) {
        layer.image = await loadImage(dataRoot + layer.file);
        images.set(layer.name, layer.image);
        visible.set(layer.name, true);
        offsets.set(layer.name, {x: 0, y: 0});
      }
      renderLayerList();
      draw();
      loader.classList.add('hidden');
      document.querySelector('#selected-label').textContent = '选中：Base + 面部补色';
    } catch (err) {
      loader.textContent = `读取失败：${err.message}`;
      loader.style.color = '#efb4ad';
    }
  }

  function renderLayerList() {
    list.replaceChildren();
    const baseRow = document.createElement('div');
    baseRow.className = 'layer-row base selected';
    baseRow.dataset.name = 'Base_Face_Underpaint_WIP';
    baseRow.innerHTML = '<span class="icon">B</span><span class="name">Base + 面部补色<span class="kind">WIP 底层 · 其余角色仍扁平</span></span><button class="eye-toggle on" aria-label="显示底层">◉</button>';
    baseRow.addEventListener('click', e => { if (e.target.closest('.eye-toggle')) return; select('Base_Face_Underpaint_WIP'); });
    baseRow.querySelector('.eye-toggle').addEventListener('click', e => { e.stopPropagation(); baseRow.classList.toggle('hidden-layer'); baseRow.querySelector('.eye-toggle').classList.toggle('on'); baseRow.dataset.visible = baseRow.dataset.visible === 'false' ? 'true' : 'false'; draw(); });
    list.append(baseRow);
    state.layers.forEach((layer, i) => {
      const row = document.createElement('div');
      row.className = 'layer-row'; row.dataset.name = layer.name; row.dataset.kind = 'face';
      const short = layer.name.replaceAll('_', ' ');
      row.innerHTML = `<span class="icon">${String(i+1).padStart(2,'0')}</span><span class="name">${short}<span class="kind">${layer.name === 'Whale_Clip' ? '配饰拆件' : '脸部拆件'}</span></span><button class="eye-toggle on" aria-label="切换可见">◉</button>`;
      row.addEventListener('click', e => { if (e.target.closest('.eye-toggle')) return; select(layer.name); });
      row.querySelector('.eye-toggle').addEventListener('click', e => { e.stopPropagation(); const on = !visible.get(layer.name); visible.set(layer.name, on); e.currentTarget.classList.toggle('on', on); draw(); });
      list.append(row);
    });
  }

  function select(name) {
    state.selected = name;
    document.querySelectorAll('.layer-row').forEach(row => row.classList.toggle('selected', row.dataset.name === name));
    const label = name === 'Base_Face_Underpaint_WIP' ? 'Base + 面部补色' : name.replaceAll('_', ' ');
    document.querySelector('#selected-label').textContent = `选中：${label}`;
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const baseRow = list.querySelector('.layer-row.base');
    const baseVisible = !baseRow || baseRow.dataset.visible !== 'false';
    const showBaseAlone = state.isolate && state.selected === 'Base_Face_Underpaint_WIP';
    if (baseVisible && base && (!state.isolate || showBaseAlone)) ctx.drawImage(base, 0, 0);
    const selectedPart = state.layers.find(x => x.name === state.selected);
    for (const layer of state.layers) {
      const isVisible = visible.get(layer.name) && (!state.isolate || layer.name === state.selected);
      if (!isVisible) continue;
      const off = offsets.get(layer.name);
      ctx.drawImage(layer.image, off.x, off.y);
    }
    if (state.referenceOn && state.reference) {
      ctx.save(); ctx.globalAlpha = state.opacity; ctx.drawImage(state.reference, 0, 0); ctx.restore();
    }
    if (selectedPart && state.selected !== 'Base_Face_Underpaint_WIP') {
      const off = offsets.get(selectedPart.name);
      ctx.save(); ctx.strokeStyle = '#bca8f1'; ctx.lineWidth = 1; ctx.setLineDash([5,4]);
      ctx.strokeRect(off.x + 1, off.y + 49, canvas.width - 2, canvas.height - 50); ctx.restore();
    }
  }

  function nudge(dx, dy) {
    const off = offsets.get(state.selected);
    if (!off) return;
    off.x += dx; off.y += dy; draw();
  }

  document.querySelector('#show-ref').addEventListener('change', e => { state.referenceOn = e.target.checked; draw(); });
  document.querySelector('#ref-opacity').addEventListener('input', e => { state.opacity = Number(e.target.value)/100; document.querySelector('#opacity-out').value = `${e.target.value}%`; draw(); });
  document.querySelector('#isolate').addEventListener('click', e => { state.isolate = !state.isolate; e.currentTarget.classList.toggle('active', state.isolate); e.currentTarget.textContent = state.isolate ? '显示完整合成' : '单独显示所选部件'; draw(); });
  document.querySelector('#checker').addEventListener('click', e => { state.checker = !state.checker; e.currentTarget.classList.toggle('active', state.checker); document.querySelector('#viewport').classList.toggle('no-checker', !state.checker); });
  document.querySelector('#fit').addEventListener('click', () => canvas.scrollIntoView({block:'nearest'}));
  document.querySelector('#reset').addEventListener('click', () => { for (const name of offsets.keys()) offsets.set(name,{x:0,y:0}); state.isolate = false; document.querySelector('#isolate').classList.remove('active'); document.querySelector('#isolate').textContent = '单独显示所选部件'; draw(); });
  document.querySelector('#clear-offset').addEventListener('click', () => { if (offsets.has(state.selected)) offsets.set(state.selected,{x:0,y:0}); draw(); });
  document.querySelectorAll('.nudge-grid button').forEach(btn => btn.addEventListener('click', () => nudge(Number(btn.dataset.dx), Number(btn.dataset.dy))));
  document.querySelector('#save-png').addEventListener('click', () => { draw(); const a=document.createElement('a'); a.href=canvas.toDataURL('image/png'); a.download='xiaoxun-loli-face-pass-01-review.png'; a.click(); });
  window.addEventListener('keydown', e => { if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key) && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); nudge(e.key==='ArrowLeft'?-1:e.key==='ArrowRight'?1:0,e.key==='ArrowUp'?-1:e.key==='ArrowDown'?1:0); } });
  canvas.addEventListener('pointerdown', e => {
    const hit = [...state.layers].reverse().find(layer => visible.get(layer.name) && e.target === canvas);
    if (!hit || state.selected === 'Base_Face_Underpaint_WIP') return;
    const r=canvas.getBoundingClientRect(); const scaleX=canvas.width/r.width, scaleY=canvas.height/r.height;
    dragging=state.layers.find(x=>x.name===state.selected); dragStart={px:e.clientX,py:e.clientY,ox:offsets.get(dragging.name).x,oy:offsets.get(dragging.name).y,sx:scaleX,sy:scaleY}; canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => { if(!dragging)return; const off=offsets.get(dragging.name); off.x=dragStart.ox+(e.clientX-dragStart.px)*dragStart.sx; off.y=dragStart.oy+(e.clientY-dragStart.py)*dragStart.sy; draw(); });
  canvas.addEventListener('pointerup', () => { dragging=null; dragStart=null; });
  init();
})();
