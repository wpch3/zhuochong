(() => {
  'use strict';
  const ROOT='/media/characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/authoring_pass_07/';
  const PREVIEW='/loli-authoring-preview-assets/pass_07/';
  const $=id=>document.getElementById(id);
  const canvas=$('stage'),ctx=canvas.getContext('2d');
  const wrap=$('canvasWrap'),review=$('reviewImage'),list=$('layerList');
  const labels={
    Hair_Back:'后发 / 头顶发片',Hair_Side_L:'左侧头发',Hair_Side_R:'右侧头发',Hair_Bangs:'刘海',Hair_Ahoge:'呆毛',
    Underpaint_FaceBehindHair_WIP:'头发下脸部估算填色',Underpaint_FaceBehindHair:'头发下脸部估算填色',
    Underpaint_Shirt_WIP:'上衣遮挡估算填色',Underpaint_Jacket_WIP:'外套遮挡估算填色',
    Underpaint_Hand_L_WIP:'左手腕遮挡估算填色',Underpaint_Hand_R_WIP:'右手腕遮挡估算填色',
    Jacket_Body_L:'左外套衣身',Jacket_Body_R:'右外套衣身',JacketSleeve_Teal_L:'左袖可见青色部分',JacketSleeve_Teal_R:'右袖可见青色部分',
    Shirt_Front:'上衣前片',Neck:'颈部可见部分',Cuff_L:'左袖口',Cuff_R:'右袖口',Hand_L:'左手可见部分',Hand_R:'右手可见部分',
    Leg_Skin_L:'左腿可见皮肤',Leg_Skin_R:'右腿可见皮肤',Skirt:'裙子',Sock_L:'左袜',Sock_R:'右袜',Shoe_L:'左鞋',Shoe_R:'右鞋',
    EyeWhite_L:'左眼白',EyeBall_L:'左眼球',Eyelash_L:'左睫毛',Brow_L:'左眉',EyeWhite_R:'右眼白',EyeBall_R:'右眼球',Eyelash_R:'右睫毛',Brow_R:'右眉',Nose:'鼻',Mouth_Closed:'闭嘴线稿',Whale_Clip:'鲸鱼发夹'
  };
  const state={parts:[],images:new Map(),offsets:new Map(),visible:new Map(),base:null,baseVisible:true,reference:null,referenceVisible:false,mode:'stack',solo:null,motion:{angleZ:0,hairSwing:0,blink:0},autoMotion:false,raf:0};
  function category(name){
    if(name.startsWith('Hair_'))return '头发';
    if(name.startsWith('Underpaint_'))return '遮挡估算';
    if(/^(Eye|Brow|Nose|Mouth|Whale)/.test(name))return '面部与饰品';
    if(/^(Jacket|Shirt|Neck|Cuff|Hand)/.test(name))return '上半身';
    return '下半身';
  }
  function loadImage(path){return new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(new Error('图片加载失败：'+path));im.src=path;});}
  function bg(){wrap.classList.remove('bg-dark','bg-light');const v=$('bgMode').value;if(v==='dark')wrap.classList.add('bg-dark');if(v==='light')wrap.classList.add('bg-light');}
  function draw(){
    ctx.clearRect(0,0,1280,1920);
    if(state.baseVisible&&state.base)ctx.drawImage(state.base,0,0,1280,1920);
    for(const p of state.parts){
      if(state.visible.get(p.name)===false)continue;
      const im=state.images.get(p.name),at=state.offsets.get(p.name)||[0,0],name=p.name;
      const head=/^(Hair_|Eye|Brow|Nose|Mouth|Whale)/.test(name);
      ctx.save();
      if(state.mode==='motion'&&head){
        ctx.translate(640,430);ctx.rotate(state.motion.angleZ*Math.PI/180);ctx.translate(-640,-430);
        let swing=0;if(name==='Hair_Side_L'||name==='Hair_Side_R')swing=state.motion.hairSwing*.8;else if(name==='Hair_Bangs')swing=state.motion.hairSwing*.48;else if(name==='Hair_Back')swing=state.motion.hairSwing*.16;else if(name==='Hair_Ahoge')swing=state.motion.hairSwing*.25;
        if(swing)ctx.translate(swing,0);
      }
      if(state.mode==='motion'&&state.motion.blink>0&&(name==='EyeWhite_L'||name==='EyeBall_L'||name==='EyeWhite_R'||name==='EyeBall_R')){
        const cx=name.endsWith('_L')?520:744,cy=412,sy=1-state.motion.blink;ctx.translate(cx,cy);ctx.scale(1,sy);ctx.translate(-cx,-cy);
      }
      ctx.drawImage(im,at[0],at[1]);ctx.restore();
    }
    if(state.referenceVisible&&state.reference){ctx.save();ctx.globalAlpha=.34;ctx.drawImage(state.reference,0,0,1280,1920);ctx.restore();}
  }
  function setMode(mode){
    state.mode=mode;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
    const staticImage=mode==='hair'||mode==='all';canvas.style.display=staticImage?'none':'block';review.style.display=staticImage?'block':'none';$('motionControls').hidden=mode!=='motion';
    if(mode==='hair'){review.src=ROOT+'hair_edge_review.jpg';$('viewCaption').textContent='头发独立层放大板：可检查刘海、侧发、后发与呆毛的透明边缘；未通过手工美术验收。';}
    else if(mode==='all'){review.src=ROOT+'layer_review_board.jpg';$('viewCaption').textContent='全 38 层检查板。透明棋盘用于查看选区；估算填色图层以金色标签标注。';}
    else if(mode==='motion'){$('viewCaption').textContent='非 Cubism 动态暴露测试：头发与五官只做刚体/缩放占位，出现的断边正是待补画清单；不能当作 Live2D 验收。';draw();}
    else{$('viewCaption').textContent='所有部件叠加：静态重组与 v1.1 参考一致；切换右侧图层以检查当前拆件。';draw();}
  }
  function buildRows(){
    list.textContent='';
    for(const p of state.parts){
      const name=p.name,estimated=name.startsWith('Underpaint_');
      const row=document.createElement('div');row.className='layer-row'+(estimated?' estimated':'');row.dataset.name=name;row.dataset.category=category(name);
      const check=document.createElement('input');check.type='checkbox';check.checked=true;check.setAttribute('aria-label','切换 '+(labels[name]||name));
      check.addEventListener('change',()=>{state.visible.set(name,check.checked);row.classList.toggle('hidden',!check.checked);state.solo=null;draw();});
      const meta=document.createElement('div');meta.className='layer-label';
      const title=document.createElement('strong');title.textContent=labels[name]||name;
      const sub=document.createElement('small');sub.textContent=name+(estimated?' · 平涂估算':' · 源图可见像素');
      meta.append(title,sub);
      const solo=document.createElement('button');solo.type='button';solo.textContent='独看';solo.title='仅显示该部件';
      solo.addEventListener('click',()=>{state.solo=name;state.parts.forEach(q=>{const on=q.name===name;state.visible.set(q.name,on);const r=list.querySelector(`[data-name="${CSS.escape(q.name)}"]`);if(r){r.querySelector('input').checked=on;r.classList.toggle('hidden',!on);}});$('baseToggle').checked=false;state.baseVisible=false;draw();});
      row.append(check,meta,solo);list.append(row);state.visible.set(name,true);
    }
    $('layerCount').textContent=state.parts.length+' 层';
    $('renderStatus').textContent=`已加载 ${state.parts.length} 层 · 静态原画预览`;
  }
  async function init(){
    try{
      const [res,previewRes]=await Promise.all([fetch(ROOT+'layer_manifest.json'),fetch(PREVIEW+'manifest.json')]);
      if(!res.ok)throw new Error('WIP 清单加载失败 '+res.status);if(!previewRes.ok)throw new Error('裁切预览资产加载失败 '+previewRes.status);
      const manifest=await res.json(),previewManifest=await previewRes.json();state.parts=manifest.parts;
      $('oraDownload').href=ROOT+manifest.ora_file;
      const cropByName=new Map(previewManifest.parts.map(p=>[p.name,p]));
      const basePath=ROOT+'Base_Figure_HairUnderpaint_WIP.png';
      const jobs=[loadImage(basePath).then(im=>state.base=im),loadImage(ROOT+'reference_v1_1_alpha_edge_connected.png').then(im=>state.reference=im)];
      for(const p of state.parts){const crop=cropByName.get(p.name);if(!crop)throw new Error('缺少裁切图层：'+p.name);jobs.push(loadImage(PREVIEW+crop.file).then(im=>{state.images.set(p.name,im);state.offsets.set(p.name,crop.offset_xy);}));}
      await Promise.all(jobs);buildRows();draw();
    }catch(err){$('renderStatus').textContent='加载失败：'+err.message;console.error(err);}
  }
  function refreshMotionUI(){
    $('angleZ').value=state.motion.angleZ;$('hairSwing').value=state.motion.hairSwing;$('blink').value=Math.round(state.motion.blink*100);
    $('angleValue').textContent=`${Math.round(state.motion.angleZ)}°`;$('hairValue').textContent=`${Math.round(state.motion.hairSwing)} px`;$('blinkValue').textContent=`${Math.round(state.motion.blink*100)}%`;
  }
  function stopAutoMotion(){state.autoMotion=false;if(state.raf)cancelAnimationFrame(state.raf);state.raf=0;$('autoMotion').setAttribute('aria-pressed','false');$('autoMotion').textContent='▶ 自动摆动';}
  function autoFrame(t){
    if(!state.autoMotion)return;
    const s=t/1000;state.motion.angleZ=Math.sin(s*.9)*6;state.motion.hairSwing=Math.sin(s*1.7)*14;
    const blinkPhase=(s%3.2)/3.2;state.motion.blink=blinkPhase<.07?Math.sin(blinkPhase/.07*Math.PI)*.72:0;
    refreshMotionUI();draw();state.raf=requestAnimationFrame(autoFrame);
  }
  document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));
  for(const [id,key] of [['angleZ','angleZ'],['hairSwing','hairSwing']])$(id).addEventListener('input',e=>{stopAutoMotion();state.motion[key]=Number(e.target.value);refreshMotionUI();setMode('motion');});
  $('blink').addEventListener('input',e=>{stopAutoMotion();state.motion.blink=Number(e.target.value)/100;refreshMotionUI();setMode('motion');});
  $('autoMotion').addEventListener('click',()=>{if(state.autoMotion){stopAutoMotion();return;}state.autoMotion=true;$('autoMotion').setAttribute('aria-pressed','true');$('autoMotion').textContent='■ 停止摆动';setMode('motion');state.raf=requestAnimationFrame(autoFrame);});
  $('bgMode').addEventListener('change',bg);
  $('baseToggle').addEventListener('change',e=>{state.baseVisible=e.target.checked;draw();});
  $('showAll').addEventListener('click',()=>{state.solo=null;state.baseVisible=true;$('baseToggle').checked=true;state.parts.forEach(p=>state.visible.set(p.name,true));list.querySelectorAll('.layer-row').forEach(r=>{r.querySelector('input').checked=true;r.classList.remove('hidden');});draw();});
  $('hideAll').addEventListener('click',()=>{state.solo=null;state.baseVisible=false;$('baseToggle').checked=false;state.parts.forEach(p=>state.visible.set(p.name,false));list.querySelectorAll('.layer-row').forEach(r=>{r.querySelector('input').checked=false;r.classList.add('hidden');});draw();});
  $('resetLayers').addEventListener('click',()=>{stopAutoMotion();state.motion={angleZ:0,hairSwing:0,blink:0};refreshMotionUI();$('showAll').click();$('bgMode').value='checker';bg();});
  $('layerSearch').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();list.querySelectorAll('.layer-row').forEach(r=>{r.hidden=!!q&&!(r.dataset.name.toLowerCase().includes(q)||r.dataset.category.toLowerCase().includes(q)||(labels[r.dataset.name]||'').toLowerCase().includes(q));});});
  $('viewCaption').insertAdjacentHTML('beforeend',' <label class="overlay-toggle"><input id="referenceOverlay" type="checkbox"> 叠加参考</label>');
  $('referenceOverlay').addEventListener('change',e=>{state.referenceVisible=e.target.checked;draw();});
  bg();init();
})();
