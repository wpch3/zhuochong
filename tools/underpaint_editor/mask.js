/* A conservative geometric margin, not a C-rendering equality guarantee. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object' && module.exports)module.exports=api;
  else root.UnderpaintMask=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function safeMask(alphas,width,height,margin){
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||
       !Number.isInteger(margin)||margin<0||margin>8||!Array.isArray(alphas)||!alphas.length||
       alphas.some(a=>a.length!==width*height))throw new Error('invalid mask arguments');
    const out=new Uint8Array(width*height),stride=width+1;
    for(const alpha of alphas){
      // Integral image of non-opaque pixels gives an O(width*height) erosion.
      const integral=new Uint32Array((width+1)*(height+1));
      for(let y=0;y<height;y++){
        let row=0;
        for(let x=0;x<width;x++){
          row+=alpha[y*width+x]===255?0:1;
          integral[(y+1)*stride+x+1]=integral[y*stride+x+1]+row;
        }
      }
      for(let y=margin;y<height-margin;y++)for(let x=margin;x<width-margin;x++){
        const x0=x-margin,y0=y-margin,x1=x+margin+1,y1=y+margin+1;
        const invalid=integral[y1*stride+x1]-integral[y0*stride+x1]-integral[y1*stride+x0]+integral[y0*stride+x0];
        if(invalid===0)out[y*width+x]=1;
      }
    }
    return out;
  }
  return {safeMask};
});
