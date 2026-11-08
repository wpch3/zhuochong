/* Experimental local-only transparent underpaint editor; not a C renderer. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const canvas = $('canvas'), ctx = canvas.getContext('2d', {willReadFrequently:true});
  const overlay = document.createElement('canvas'), mask = document.createElement('canvas'), highlight = document.createElement('canvas');
  const reference = document.createElement('canvas');
  const octx = overlay.getContext('2d', {willReadFrequently:true});
  const mctx = mask.getContext('2d', {willReadFrequently:true});
  let images = null, loaded = false, loading = false, mode = 'brush', gesture = null, serial = 0;
  let undo = [], redo = [];
  const LIMIT = 25;
  function message(text) { $('status').textContent = text; }
  function state() {
    $('undo').disabled = !loaded || !undo.length || !!gesture || loading;
    $('redo').disabled = !loaded || !redo.length || !!gesture || loading;
    $('clear').disabled = !loaded || !!gesture || loading;
    $('download').disabled = !loaded || !!gesture || loading;
    $('demo').disabled = $('loadFiles').disabled = !!gesture || loading;
    $('brush').classList.toggle('active', mode === 'brush');
    $('picker').classList.toggle('active', mode === 'picker');
  }
  function snap() { return octx.getImageData(0,0,overlay.width,overlay.height); }
  function restore(image) { octx.putImageData(image,0,0); }
  function same(a,b) {
    for (let i=0; i<a.data.length; i++) if (a.data[i] !== b.data[i]) return false;
    return true;
  }
  function keep(stack, image) { stack.push(image); if (stack.length > LIMIT) stack.shift(); }
  async function png(blob) {
    if (blob.size > 10000000) throw Error('PNG 文件超过 10 MB');
    const bytes = new Uint8Array(await blob.slice(0,24).arrayBuffer());
    if (bytes.length !== 24 || [137,80,78,71,13,10,26,10].some((n,i) => bytes[i] !== n) ||
        bytes[12] !== 73 || bytes[13] !== 72 || bytes[14] !== 68 || bytes[15] !== 82) throw Error('只接受有效的 PNG 文件');
    const header = new DataView(bytes.buffer);
    if (header.getUint32(16) !== 480 || header.getUint32(20) !== 512) throw Error('当前工作台只支持 480×512 的三张对齐素材');
    const url = URL.createObjectURL(blob);
    try {
      const img = new Image();
      await new Promise((ok,fail) => { img.onload=ok; img.onerror=()=>fail(Error('PNG 解码失败')); img.src=url; });
      return img;
    } finally { URL.revokeObjectURL(url); }
  }
  function beginLoad() {
    if (gesture || loading) return null;
    const hasPaint = loaded && snap().data.some((v,i) => i%4===3 && v!==0);
    if (hasPaint && !window.confirm('重新载入会丢弃当前补画和撤销记录。请先下载补画层，确定继续？')) return null;
    loading=true; state();
    return ++serial;
  }
  async function load(blobs, current) {
    try {
      if (blobs.some(x => !x)) throw Error('请选择身体、左袖手和右袖手三张 PNG');
      const imgs = await Promise.all(blobs.map(png));
      if (current !== serial) return;
      if (imgs.some(img => img.naturalWidth !== 480 || img.naturalHeight !== 512)) throw Error('当前工作台只支持 480×512 的三张对齐素材');
      // Build a binary mask from truly opaque arm pixels; anti-aliased edge
      // pixels are excluded to preserve the default composite exactly.
      const test = document.createElement('canvas'); test.width=480; test.height=512;
      const t = test.getContext('2d', {willReadFrequently:true});
      const alpha = [];
      for (const img of imgs.slice(1)) { t.clearRect(0,0,480,512); t.drawImage(img,0,0); alpha.push(t.getImageData(0,0,480,512).data); }
      const md = t.createImageData(480,512); let count=0;
      for (let i=0;i<md.data.length;i+=4) if (alpha[0][i+3]===255 || alpha[1][i+3]===255) {
        md.data[i]=md.data[i+1]=md.data[i+2]=md.data[i+3]=255; count++;
      }
      if (!count) throw Error('袖手中没有完全不透明像素，不能补画');
      if (gesture) cancel();
      for (const c of [canvas,overlay,mask,highlight,reference]) { c.width=480; c.height=512; }
      mctx.putImageData(md,0,0);
      const hctx=highlight.getContext('2d'); hctx.drawImage(mask,0,0); hctx.globalCompositeOperation='source-in'; hctx.fillStyle='#ce4bad'; hctx.fillRect(0,0,480,512); hctx.globalCompositeOperation='source-over';
      const rctx = reference.getContext('2d'); rctx.drawImage(imgs[0],0,0); rctx.drawImage(imgs[1],0,0); rctx.drawImage(imgs[2],0,0);
      images=imgs; loaded=true; undo=[]; redo=[];
      message('已载入：允许在 '+count+' 个被袖手完全遮住的像素内补画'); state(); render();
    } catch(e) { if (current === serial) message('载入失败：'+e.message); }
    finally { if(current===serial){loading=false;state();} }
  }
  function drawArm(img, px, py, degrees) {
    ctx.save(); ctx.translate(px,py); ctx.rotate(degrees*Math.PI/180); ctx.translate(-px,-py); ctx.drawImage(img,0,0); ctx.restore();
  }
  function render() {
    const w=canvas.width,h=canvas.height;
    ctx.clearRect(0,0,w,h);
    const bg=$('background').value;
    ctx.fillStyle=bg==='dark'?'#262b31':'#f1f1f1'; ctx.fillRect(0,0,w,h);
    if(bg==='checker') {ctx.fillStyle='#dcd9df';for(let y=0;y<h;y+=24)for(let x=0;x<w;x+=24)if((x/24+y/24)%2===0)ctx.fillRect(x,y,24,24);}
    if(!loaded)return;
    ctx.drawImage(images[0],0,0); ctx.drawImage(overlay,0,0);
    if($('showArms').checked){drawArm(images[1],140,35,Number($('leftAngle').value));drawArm(images[2],315,35,Number($('rightAngle').value));}
    if($('showMask').checked){ctx.save();ctx.globalAlpha=.38;ctx.drawImage(highlight,0,0);ctx.restore();}
  }
  function point(event) {
    const r=canvas.getBoundingClientRect();
    return {x:(event.clientX-r.left)*canvas.width/r.width, y:(event.clientY-r.top)*canvas.height/r.height};
  }
  function paint(a,b) {
    octx.save(); octx.globalCompositeOperation='source-over'; octx.strokeStyle=$('color').value;
    octx.fillStyle=$('color').value; octx.lineWidth=Number($('size').value); octx.lineCap='round'; octx.lineJoin='round';
    octx.beginPath(); octx.moveTo(a.x,a.y); octx.lineTo(b.x,b.y); octx.stroke();
    octx.beginPath(); octx.arc(b.x,b.y,octx.lineWidth/2,0,Math.PI*2); octx.fill();
    octx.globalCompositeOperation='destination-in'; octx.drawImage(mask,0,0); octx.restore(); render();
  }
  function cancel() { if(!gesture)return; restore(gesture.before); gesture=null; state(); render(); message('手势已取消'); }
  canvas.addEventListener('pointerdown', e => {
    if(!loaded || loading || gesture || e.button!==0)return;
    const p=point(e); if(p.x<0||p.y<0||p.x>=480||p.y>=512)return;
    if(mode==='picker') {
      const pixel=reference.getContext('2d').getImageData(Math.floor(p.x),Math.floor(p.y),1,1).data;
      if(pixel[3]===0){message('该位置透明，不能取色');return;}
      $('color').value='#'+Array.from(pixel.slice(0,3),n=>n.toString(16).padStart(2,'0')).join('');
      mode='brush';state();message('已取色，返回画笔');return;
    }
    e.preventDefault(); gesture={id:e.pointerId,before:snap(),last:p}; canvas.setPointerCapture(e.pointerId); paint(p,p); state();
  });
  canvas.addEventListener('pointermove', e => {if(!gesture||gesture.id!==e.pointerId)return; const p=point(e); paint(gesture.last,p);gesture.last=p;});
  canvas.addEventListener('pointerup', e => {
    if(!gesture||gesture.id!==e.pointerId)return;
    const before=gesture.before; gesture=null;
    if(!same(before,snap())){keep(undo,before);redo=[];message('已保存一笔，可撤销');} else message('该笔不在可补画区域');
    state(); render();
  });
  canvas.addEventListener('pointercancel', e => {if(gesture && gesture.id===e.pointerId)cancel();});
  canvas.addEventListener('lostpointercapture', e => {if(gesture && gesture.id===e.pointerId)cancel();});
  $('demo').onclick=async()=>{
    const current=beginLoad(); if(current===null)return;
    try { const paths=['body','arm_l','arm_r'].map(n=>'../../experiments/live2d_chibi_dynamic/sprites/'+n+'.png');
      const responses=await Promise.all(paths.map(p=>fetch(p))); if(responses.some(r=>!r.ok))throw Error('无法读取示例，请使用项目预览脚本');
      if(current!==serial)return;
      await load(await Promise.all(responses.map(r=>r.blob())),current);
    } catch(e){if(current===serial){loading=false;state();message('载入失败：'+e.message);}}
  };
  $('loadFiles').onclick=()=>{const current=beginLoad();if(current!==null)load(['bodyFile','leftFile','rightFile'].map(id=>$(id).files[0]),current);};
  $('brush').onclick=()=>{mode='brush';state();}; $('picker').onclick=()=>{mode='picker';state();};
  $('undo').onclick=()=>{if(!undo.length||gesture)return;keep(redo,snap());restore(undo.pop());state();render();message('已撤销');};
  $('redo').onclick=()=>{if(!redo.length||gesture)return;keep(undo,snap());restore(redo.pop());state();render();message('已重做');};
  $('clear').onclick=()=>{if(!loaded||gesture)return;const before=snap();octx.clearRect(0,0,480,512);if(!same(before,snap())){keep(undo,before);redo=[];}state();render();message('已清空补画，可撤销');};
  $('download').onclick=()=>{if(!loaded||gesture)return; overlay.toBlob(blob=>{
    if(!blob){message('导出失败');return;} const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='underpaint-patch.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('已下载透明补画层；原素材未修改');
  },'image/png');};
  for(const id of ['leftAngle','rightAngle','background','showArms','showMask']) $(id).addEventListener('input',()=>{
    $('leftOut').textContent=$('leftAngle').value+'°';$('rightOut').textContent=$('rightAngle').value+'°';render();
  });
  $('size').oninput=()=>{$('sizeOut').textContent=$('size').value;};
  $('zoom').onchange=()=>{canvas.style.width=(480*Number($('zoom').value))+'px';canvas.style.height=(512*Number($('zoom').value))+'px';};
  canvas.style.width='480px';canvas.style.height='512px';state();render();
})();
