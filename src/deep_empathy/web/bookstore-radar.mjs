// Frontend display proxies only; no backend metric or psychological score is implied.
export const AXES=['core','regulation','cognition','identity','behavior'];
export const LABELS=['Core','Regulation','Cognition','Identity','Behavior'];
export function profileMetrics(claims=[]){
  return AXES.map(layer=>{
    const items=claims.filter(c=>c.layer===layer&&!['retracted','contradicted','superseded'].includes(c.status));
    const weight=items.reduce((sum,c)=>sum+(c.evidence?.length?Math.max(0,Math.min(1,Number(c.confidence)||0)) : 0),0);
    const clarity=1-Math.exp(-weight/3);
    const confirmed=items.filter(c=>c.status==='user_confirmed').length;
    return {clarity,stability:items.length?clarity*confirmed/items.length:0};
  });
}
export class RadarSnapshot {
  constructor(){this.baseline=null;this.current=null;this.deltas=AXES.map(()=>0);}
  beginRound(){this.baseline=this.current?.map(v=>({...v}))||null;this.deltas=AXES.map(()=>0);}
  update(claims){const next=profileMetrics(claims);if(!this.baseline)this.baseline=next.map(v=>({...v}));this.current=next;this.deltas=next.map((v,i)=>v.clarity-this.baseline[i].clarity);return next;}
}
const NS='http://www.w3.org/2000/svg';
function svgNode(tag,attrs={}){const node=document.createElementNS(NS,tag);for(const [key,value]of Object.entries(attrs))node.setAttribute(key,String(value));return node;}
export function renderRadar(container,rows,model){
  const values=model.current||profileMetrics(),delta=model.deltas,changes=values.map((v,i)=>Math.max(Math.abs(delta[i]),Math.abs(v.stability-(model.baseline?.[i].stability??v.stability)))),max=Math.max(...changes);
  const point=(i,r)=>{const a=-Math.PI/2+i*2*Math.PI/5;return [150+Math.cos(a)*r,126+Math.sin(a)*r];};
  const polygon=r=>AXES.map((_,i)=>point(i,typeof r==='number'?r:r[i]).join(',')).join(' ');
  const svg=svgNode('svg',{viewBox:'0 0 300 254',role:'img','aria-label':'五层画像雷达图。清晰度基于有依据条目的置信度累计，稳定度为用户确认比例的展示代理，范围零到一。'});
  const title=svgNode('title');title.textContent='Clarity / Stability · 前端展示指标';svg.append(title);
  for(const level of [.25,.5,.75,1])svg.append(svgNode('polygon',{points:polygon(84*level),class:'radar-grid'}));
  AXES.forEach((_,i)=>{const end=point(i,84);svg.append(svgNode('line',{x1:150,y1:126,x2:end[0],y2:end[1],class:'radar-spoke'}));const p=point(i,111),text=svgNode('text',{x:p[0],y:p[1]+4,'text-anchor':'middle',class:'radar-axis'});text.textContent=LABELS[i];svg.append(text);});
  for(const [key,cls]of [['clarity','radar-clarity'],['stability','radar-stability']])svg.append(svgNode('polygon',{points:polygon(values.map(v=>v[key]*84)),class:cls}));
  values.forEach((v,i)=>{const hot=max>.00001&&changes[i]>=max-.00001,p=point(i,v.clarity*84),dot=svgNode('circle',{cx:p[0],cy:p[1],r:hot?4.5:2.5,class:hot?'radar-hot':'radar-dot'});const tip=svgNode('title');tip.textContent=`${LABELS[i]} · Clarity ${v.clarity.toFixed(2)} · Stability ${v.stability.toFixed(2)}`;dot.append(tip);svg.append(dot);});
  container.replaceChildren(svg);rows.replaceChildren();
  AXES.forEach((_,i)=>{const row=document.createElement('div');row.className='radar-change'+(max>.00001&&changes[i]>=max-.00001?' latest':'');const name=document.createElement('span');name.textContent=LABELS[i];const value=document.createElement('span');value.className='change-value';const d=Math.abs(delta[i])<.005?0:delta[i];value.textContent=`${d>=0?'+':''}${d.toFixed(2)}`;row.append(name,value);rows.append(row);});
}
