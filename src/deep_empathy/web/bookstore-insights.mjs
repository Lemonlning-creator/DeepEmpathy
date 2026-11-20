import {AXES,LABELS,profileMetrics} from './bookstore-radar.mjs?v=20261113-radar2';
export const READING_CAPS=[['book_recommendation','书籍推荐'],['literary_discussion','文学讨论'],['reading_feelings','阅读感受交流'],['reading_experience','阅读经验分享']];
export const EMOTIONAL_CAPS=[['emotion_understanding','情感理解'],['empathetic_response','共情回应'],['user_memory','用户记忆'],['relationship_care','持续关怀与关系维护']];
const needs={autonomy:'自主与选择',competence:'胜任与成长',relatedness:'联结与接纳'};
const goals={mastery:'掌握与进步',performance:'表现与认可',avoidance:'避免受挫'};
const clean=s=>s&&!['尚需了解','未知','尚不明确','不明确','暂无'].includes(s)?s:'';
export function psychologyParts(p){
  if(!p?.citations?.length)return {needs:'',goals:'',self_view:''};
  const interpretation=clean(p.interpretation);
  return {
    needs:p.needs?.length?[p.needs.map(n=>needs[n]||n).join('、'),interpretation].filter(Boolean).join('：'):'',
    goals:p.goals?.length?[p.goals.map(g=>goals[g]||g).join('、'),interpretation].filter(Boolean).join('：'):'',
    self_view:[['现实',p.actual_self],['理想',p.ideal_self],['期待',p.ought_self]].filter(([,v])=>clean(v)).map(([k,v])=>`${k}：${v}`).join('；'),
  };
}
export class InsightPanel{
  constructor(){this.data={claims:[]};this.activeTurn=null;this.baselinePsych=psychologyParts(null);}
  observe(data){this.data=data;}
  beginRound(){this.baselinePsych=psychologyParts(this.data.current_turn?.psychology);this.activeTurn=null;}
  completeRound(turnId){this.activeTurn=turnId;}
  view(){
    const current=this.data.current_turn;
    const aligned=!!this.activeTurn&&current?.id===this.activeTurn&&this.data.mode!=='demo';
    const activeClaims=new Map(this.data.claims.map(c=>[c.id,c]));
    const updates=aligned?(current.profile_updates||[]).filter(u=>activeClaims.has(u.id)&&activeClaims.get(u.id).version===u.version&&!['retracted','contradicted','superseded'].includes(activeClaims.get(u.id).status)):[];
    const latent=aligned?current.latent_psychology:null;
    const valid=latent&&['needs','goals','self_view'].includes(latent.part)&&latent.state?.trim()&&latent.quote?.trim();
    const psychology=Object.fromEntries(['needs','goals','self_view'].map(k=>[k,{active:!!valid&&k===latent.part,text:valid&&k===latent.part?latent.state:''}]));
    const modelingStatus=this.data.mode!=='demo'?current?.modeling_status:'not_requested';
    return {modelingStatus,metrics:profileMetrics(this.data.claims),updates,psychology,capabilities:aligned?current.capabilities||[]:[]};
  }
}
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
function capabilityCard(id,definitions,records){
  const root=document.getElementById(id),active=new Map(records.map(r=>[r.id,r]));
  root.replaceChildren();
  for(const [key,label]of definitions){const proof=active.get(key),item=node('div',`capability-item${proof?' used':''}`);item.append(node('span','capability-check',proof?'✓':'○'),node('span','',label));item.title=proof?`本轮依据：${proof.evidence}`:'可用，本轮未使用';item.setAttribute('aria-label',`${label}，${proof?'本轮已使用':'本轮未使用'}`);root.append(item);}
  const card=root.closest('.companion-capability');card.classList.toggle('used',definitions.some(([key])=>active.has(key)));card.querySelector('.capability-state').textContent=definitions.some(([key])=>active.has(key))?'本轮已使用':'可用';
}
export function renderInsights(model){
  const view=model.view(),rows=document.getElementById('explicit-profile-layers');rows.replaceChildren();
  AXES.forEach((axis,i)=>{
    const changed=view.updates.some(u=>u.layer===axis),row=node('div',`explicit-row${changed?' updated':''}`),track=node('div','clarity-track'),bar=node('span','clarity-fill');
    bar.style.width=`${view.metrics[i].clarity*100}%`;track.append(bar);track.setAttribute('role','progressbar');track.setAttribute('aria-label',`${LABELS[i]} Clarity`);track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax','100');track.setAttribute('aria-valuenow',String(Math.round(view.metrics[i].clarity*100)));
    row.append(node('span','explicit-name',LABELS[i]),track,node('span','clarity-value',`${Math.round(view.metrics[i].clarity*100)}%`),node('span','profile-spark',changed?'✧':''));rows.append(row);
  });
  const latent=document.getElementById('latent-psychology');latent.replaceChildren();
  for(const [key,label]of [['needs','Needs'],['goals','Goals'],['self_view','Self-view']]){
    const state=view.psychology[key],card=node('div',`latent-item${state.active?' activated':''}`);card.append(node('strong','',`${state.active?'◉':'○'} ${label}`),node('p','',state.active?state.text:'未激活'));if(state.active)card.title=`暂时心理假设：${state.text}\n本轮依据：${model.data.current_turn.latent_psychology.quote}`;latent.append(card);
  }
  const updates=document.getElementById('round-profile-update-content'),box=updates.closest('.round-profile-updates');updates.replaceChildren();box.hidden=false;
  const pending=['pending','running'].includes(view.modelingStatus);
  box.setAttribute('aria-busy',String(pending));
  if(pending)updates.append(node('p','','正在整理本轮画像…'));
  else if(view.modelingStatus==='failed')updates.append(node('p','','本轮画像整理失败，暂无更新结果'));
  else if(view.modelingStatus==='cancelled')updates.append(node('p','','本轮画像整理已取消'));
  else if(!view.updates.length)updates.append(node('p','','本轮暂无画像更新'));
  for(const u of view.updates){const label=LABELS[AXES.indexOf(u.layer)]||u.layer;const text=String(u.statement||'').replace(/\s+/g,' ').trim();const brief=Array.from(text).length>48?Array.from(text).slice(0,48).join('')+'…':text;const line=node('p','',`${label}【${brief}】`);line.title=`${u.change||'更新'}：${text}`;updates.append(line);}
  capabilityCard('reading-capabilities',READING_CAPS,view.capabilities);capabilityCard('emotional-capabilities',EMOTIONAL_CAPS,view.capabilities);
  document.getElementById('round-capability-summary').parentElement.hidden=!view.capabilities.length;
  const labels=new Map([...READING_CAPS,...EMOTIONAL_CAPS]);document.getElementById('round-capability-summary').textContent=view.capabilities.map(r=>labels.get(r.id)).filter(Boolean).join(' · ')||'本轮尚无使用记录';
}
