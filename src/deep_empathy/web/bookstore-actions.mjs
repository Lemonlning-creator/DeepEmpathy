/** Restricted spoken commitments, parsed only from a successfully saved assistant turn. */
export function spokenActions(text,{mode,present,catalog=[],userContent=''}={}){
  if(mode!=='in_person'||!present)return [];
  const actions=[];
  // An affirmative "好，稍等" accepts a concrete request/coffee choice, never a question or refusal.
  if(/^(?:好(?:的)?|行|可以|没问题)[，,。\s]*(?:稍等|等我一下|我这就来)/.test(text.trim())&&!/[？?]|不行|不能|没法|无法|下次|以后/.test(text)){
    if(/咖啡|意式|手冲|拿铁|美式|卡布奇诺/.test(userContent)&&/帮我|给我|来(?:一|杯)|做|准备|冲|煮|泡|(?:意式|手冲|拿铁|美式).*(?:就好|就行|吧|谢谢)/.test(userContent)&&!/(?:不要|不喝|不用|别做)/.test(userContent))actions.push({type:'serve_coffee'});
    const book=catalog.find(b=>userContent.includes(b.title));
    if(book&&/(?:拿|取|找|挑|选)/.test(userContent))actions.push({type:'bring_book',bookId:book.id});
  }
  for(const sentence of text.match(/[^。！？!?\n；;]+[。！？!?]?/g)||[]){
    const s=sentence.trim().replace(/^(?:好(?:的)?|行|可以|没问题|稍等)[，,、\s]*/, '');
    // Questions, suggestions, hypotheticals, refusals, quoted speech and completed acts are not commitments.
    if(/[？?]$/.test(sentence.trim()))continue;
    if(/如果|要是|假如|等你|等会|待会|下次|以后|等下|不想|不做|不拿|不能|不了|不用|不要|不必|没法|无法|已经|刚才|刚刚|拿过|做过|[“”「」]/.test(s))continue;
    if(/^我(?:这就|现在|马上)?(?:来|去|帮你|给你|替你)/.test(s)&&/^(?:我.{0,10})(?:做|冲|煮|泡|准备).{0,8}(?:咖啡|拿铁|美式|意式|手冲|卡布奇诺)/.test(s))actions.push({type:'serve_coffee'});
    if(/^我(?:这就|现在|马上)?(?:来|去|帮你|给你|替你)/.test(s)&&/(?:拿|取|找|挑|选).{0,20}(?:书|《)/.test(s)){
      const named=s.match(/《([^》]+)》/);
      const wanted=named?.[1]||catalog.find(b=>userContent.includes(b.title))?.title;
      const book=wanted?catalog.find(b=>b.title===wanted):catalog.find(b=>!b.holder||b.holder==='boss');
      if(book)actions.push({type:'bring_book',bookId:book.id});
    }
  }
  return actions.filter((a,i)=>actions.findIndex(b=>a.type===b.type&&(a.bookId||'')===(b.bookId||''))===i);
}
export function userSpokenActions(text,{mode,present,catalog=[]}={}){
  if(mode!=='in_person'||!present)return [];
  const actions=[];
  for(const sentence of text.replace(/然后|接着|随后/g,'。').match(/[^。！？!?\n；;]+[。！？!?]?/g)||[]){
    if(/不想|不喝|不看|不读|别|不要|不用|不能|没喝|没看|没读|还没|已经|刚才|刚刚|如果|要是|假如|等会|待会|下次|以后|[“”「」？?]/.test(sentence))continue;
    const s=sentence.trim().replace(/^那[，,]?/, '');
    if(/你|林予|老板|他|她|他们|她们/.test(s))continue;
    if(/^(?:我(?:先|想|要|来|就|再|现在|这就|试着|准备)*[，,\s]*)?(?:先|再|现在)?(?:喝|抿|尝)(?:一|两|几|小)?(?:口|点|下)?(?:这杯|一口|一点|一下|杯|一杯|桌上(?:的)?)?咖啡/.test(s))actions.push({type:'drink_coffee'});
    if(/^(?:我(?:先|想|要|来|就|再|现在|这就|试着|准备)*[，,\s]*)?(?:先|再|现在)?(?:翻开|翻翻|打开|读|看看|看|翻)(?:.{0,12})(?:书|《)/.test(s)){
      const named=s.match(/《([^》]+)》/),book=named?catalog.find(b=>b.title===named[1]):catalog.find(b=>b.location?.startsWith('table')||b.holder==='user');
      if(!named||book)actions.push({type:'read_book',...(book?{bookId:book.id}:{})});
    }
  }
  return actions.filter((a,i)=>actions.findIndex(b=>a.type===b.type)===i);
}
export class SceneActionQueue{
  constructor({waitSafe,execute,canRun,onError}){this.waitSafe=waitSafe;this.execute=execute;this.canRun=canRun;this.onError=onError;this.pending=[];this.seen=new Set();this.running=false;}
  enqueue(turnId,actions){if(this.seen.has(turnId))return;this.seen.add(turnId);this.pending.push(...actions.filter(a=>!this.pending.some(b=>a.type===b.type&&(a.bookId||'')===(b.bookId||''))));void this.drain();}
  async drain(){if(this.running)return;this.running=true;try{while(this.pending.length){const action=this.pending[0];try{await this.waitSafe();if(this.canRun())await this.execute(action);}catch(e){this.onError(e,action);}finally{this.pending.shift();}}}finally{this.running=false;}}
}
