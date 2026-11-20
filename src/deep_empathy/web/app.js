'use strict';
const $ = id => document.getElementById(id);
const state = { config: null, session: null, sessions: [], messages: [], view: 'chat', busy: false,
  cursor: null, pending: null, mode: 'cloud', toastTimer: null, opening: false, submitting: false };
const layers = [ ['behavior', '日常习惯', 'BEHAVIOR', '从你分享的小事里，了解你的习惯。'],
  ['identity', '生活背景', 'IDENTITY', '只记录你愿意分享的生活与关系。'],
  ['cognition', '思考方式', 'COGNITION', '多一些相处，再慢慢了解你。'],
  ['regulation', '应对方式', 'REGULATION', '需要跨情境的证据，不急着下结论。'],
  ['core', '内在关切', 'CORE', '你的价值与内心，需要更长久的理解。'] ];
const headings = {chat:['JUST BETWEEN US','此刻，想聊点什么？'],records:['LITTLE MOMENTS','把心事，轻轻收藏。'],
  profile:['YOUR INNER WORLD','关于你，慢慢了解。'],settings:['MAKE YOURSELF AT HOME','这是你的陪伴空间。']};

function node(tag, className, text) { const n = document.createElement(tag); if (className) n.className = className;
  if (text !== undefined) n.textContent = text; return n; }
function toast(text) { clearTimeout(state.toastTimer); $('toast').textContent=text; $('toast').classList.remove('hidden');
  state.toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),5000); }
async function api(path, method='GET', body) {
  const controller = new AbortController(); const timer = setTimeout(()=>controller.abort(),195000);
  try {
    const response = await fetch(path, {method, credentials:'same-origin', signal:controller.signal,
      headers:{'Content-Type':'application/json','X-Deep-Empathy':'1'}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
    const data = await response.json();
    if (!response.ok) { const error=new Error(data.error?.message || '暂时无法完成，请稍后再试。');
      error.code=data.error?.code; throw error; }
    return data;
  } catch(error) { if(error.name === 'AbortError') throw new Error('本轮等待超时，可以点击重试。'); throw error; }
  finally { clearTimeout(timer); }
}
// SSE over POST: renders real cloud deltas, not a client-side typing animation.
async function streamMessage(path, body, onEvent) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),195000);
  let reader;
  try {
    const response=await fetch(path,{method:'POST',credentials:'same-origin',signal:controller.signal,
      headers:{'Content-Type':'application/json','X-Deep-Empathy':'1','Accept':'text/event-stream'},body:JSON.stringify(body)});
    if(!response.ok){const data=await response.json();throw new Error(data.error?.message||'暂时无法发送，请重试。');}
    if(!response.headers.get('content-type')?.includes('text/event-stream')||!response.body)throw new Error('流式连接未能建立，请重试。');
    reader=response.body.getReader();const decoder=new TextDecoder();let buffer='',result=null;
    function consume(block){
      let type='message';const lines=[];
      for(const line of block.split('\n')){if(line.startsWith('event:'))type=line.slice(6).trim();if(line.startsWith('data:'))lines.push(line.slice(5).trimStart());}
      if(!lines.length||type==='ping')return;
      const data=JSON.parse(lines.join('\n'));
      if(type==='error')throw new Error(data.message||'回复中断，请重试。');
      onEvent(type,data);if(type==='done')result=data;
    }
    while(true){
      const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});buffer=buffer.replace(/\r\n/g,'\n');
      let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){consume(buffer.slice(0,boundary));buffer=buffer.slice(boundary+2);}
      if(buffer.length>30000)throw new Error('流式数据格式异常，请重试。');
      if(done)break;
    }
    if(!result)throw new Error('连接已中断，回复未确认保存。请重试。');
    return result;
  } catch(error) {if(error.name==='AbortError')throw new Error('等待超时，回复未确认保存，可以重试。');throw error;}
  finally{clearTimeout(timer);if(reader){await reader.cancel().catch(()=>{});reader.releaseLock();}}
}
function safeAction(action) { return async (...args)=>{try{await action(...args);}catch(error){toast(error.message || '连接出现问题，请重试。');}}; }
function ensureIdle() { if (state.busy || state.opening) {toast('这段话正在被认真处理，请稍等片刻。');return false;}return true; }
function formatDate(value) {return new Date(value).toLocaleDateString('zh-CN',{month:'long',day:'numeric'});}
function time(value) {return new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}
function updateChrome() {
  const mode=state.session?.mode || state.mode;
  $('mode-label').textContent=mode==='demo'?'固定脚本演示 · 不分析自由输入':state.config?.cloud_configured?'云端已就绪 · 可以慢慢说':'云端尚未配置 · 点击查看陪伴方式';
  $('mode-banner').classList.toggle('cloud',mode==='cloud' && !!state.config?.cloud_configured);
  $('composer-note').textContent=mode==='demo'?'界面演示 · 零模型调用 · 不建立用户画像':'AI 陪伴 · 理解可以被你随时纠正';
  $('cloud-status').textContent=state.config?.cloud_configured?'已连接服务端配置的云端模型':'尚未配置 · 在服务端 .env 填写 API';
  $('choose-demo').disabled=!state.config?.demo_enabled;
  $('cloud-radio').classList.toggle('selected',mode==='cloud'); $('demo-radio').classList.toggle('selected',mode==='demo');
  $('memory-toggle').setAttribute('aria-checked',String(!!state.config?.memory_enabled));
  $('suggestion-label').textContent=mode==='demo'?'试试固定示例话题':'从一句小事开始';
  const items=mode==='demo'?(state.config?.demo_inputs || []):['今天有点累，只想说说。','最近总觉得自己做得不够好。','有件开心的小事想分享。'];
  const labels=mode==='demo'?['总忍不住和别人比较','我想先被听见','其实，我更在意自己的节奏']:items;
  $('suggestion-list').replaceChildren();
  items.forEach((text,i)=>{const b=node('button','suggestion',labels[i]); b.type='button';b.disabled=state.busy;
    b.addEventListener('click',()=>{if(!state.busy){$('message-input').value=text;resizeInput();$('message-input').focus();}});$('suggestion-list').append(b);});
}
async function switchView(view) {
  state.view=view;document.querySelectorAll('.view').forEach(n=>n.classList.toggle('active',n.id===`${view}-view`));
  document.querySelectorAll('.tab').forEach(n=>{n.classList.toggle('active',n.dataset.view===view);n.setAttribute('aria-current',n.dataset.view===view?'page':'false');});
  $('section-kicker').textContent=headings[view][0];$('page-title').textContent=headings[view][1];
  $('new-chat').classList.toggle('hidden',!['chat','records'].includes(view));
  if(view==='records') await loadSessions();
  if(view==='profile') await loadProfile();
}
async function loadSessions() {
  state.sessions=await api('/v1/sessions'); const container=$('sessions-list');container.replaceChildren();
  $('records-empty').classList.toggle('hidden',state.sessions.length>0);
  state.sessions.forEach(session=>{const card=node('div','session-card'),open=node('button','session-open'),del=node('button','session-delete','删除');
    open.append(node('strong','',session.title),node('small','',`${formatDate(session.updated_at)} · ${session.mode==='demo'?'演示对话':'云端对话'}`));
    open.addEventListener('click',safeAction(async()=>{if(ensureIdle()){await selectSession(session);await switchView('chat');}}));
    del.setAttribute('aria-label',`删除对话：${session.title}`);
    del.addEventListener('click',safeAction(async()=>{if(!ensureIdle())return;
      if(!await ask('让这段对话离开？','这段对话及依赖它的记忆会一并删除，无法恢复。','删除对话'))return;
      await api(`/v1/sessions/${session.id}`,'DELETE');
      if(state.session?.id===session.id){state.session=null;state.messages=[];state.cursor=null;localStorage.removeItem('deep-empathy-session');renderMessages();updateChrome();}
      await loadSessions();toast('这段对话已删除。');}));card.append(open,del);container.append(card);});
}
async function newSession(mode) {
  if(!ensureIdle())return;
  state.opening=true;
  try {
    if(state.session?.mode==='cloud')await api(`/v1/sessions/${state.session.id}/consolidate`,'POST');
    const session=await api('/v1/sessions','POST',{mode:mode || state.session?.mode || state.mode});
    state.pending=null;$('message-input').value='';resizeInput();await selectSession(session);await switchView('chat');
  } finally { state.opening=false; }
}
async function selectSession(session) {
  const data=await api(`/v1/sessions/${session.id}/messages`);
  state.session=session;state.mode=session.mode;state.messages=data.items;state.cursor=data.next_cursor;state.pending=null;
  localStorage.setItem('deep-empathy-session',session.id);renderMessages();updateChrome();scrollBottom();
}
function renderMessages() {
  $('welcome').classList.toggle('hidden',state.messages.length>0);$('messages').replaceChildren();
  $('load-older').classList.toggle('hidden',!state.cursor);
  state.messages.forEach(message=>{
    const row=node('div',`message ${message.role}${message.pending?' pending':''}${message.failed?' failed':''}`);row.dataset.messageId=message.id;
    if(message.role==='assistant'){const img=node('img','message-avatar');img.src='/static/mark.svg';img.alt='深予';row.append(img);}
    const wrap=node('div','bubble-wrap');wrap.append(node('div','bubble',message.content));
    wrap.append(node('div','message-meta',message.streaming?(message.interrupted?'回复中断 · 未确认保存':'正在回应…'):message.pending?'发送中…':message.failed?'未确认保存':time(message.created_at)));
    if(message.role==='assistant'&&!message.streaming){
      const feedback=node('div','feedback-row');[['helpful','有被理解'],['missed','还差一点']].forEach(([rating,label])=>{
        const b=node('button',`feedback-button ${message.feedback===rating?'selected':''}`,label);
        b.setAttribute('aria-pressed',String(message.feedback===rating));
        b.addEventListener('click',safeAction(async()=>{await api(`/v1/turns/${message.turn_id}/feedback`,'POST',{rating});message.feedback=rating;renderMessages();toast('谢谢你告诉我你的感受。');}));feedback.append(b);});wrap.append(feedback);
    }
    if(message.failed){const retry=node('button','retry-button','重新发送 ↗');retry.addEventListener('click',safeAction(()=>sendPending()));wrap.append(retry);}
    row.append(wrap);$('messages').append(row);
  });
}
function scrollBottom(smooth=true){requestAnimationFrame(()=>$('message-scroll').scrollTo({top:$('message-scroll').scrollHeight,behavior:smooth?'smooth':'instant'}));}
function resizeInput(){$('message-input').style.height='auto';$('message-input').style.height=Math.min($('message-input').scrollHeight,112)+'px';}
async function sendPending() {
  if(!state.pending || state.busy)return;
  const pending=state.pending;state.busy=true;pending.message.pending=true;pending.message.failed=false;
  if(pending.partial)state.messages=state.messages.filter(m=>m!==pending.partial);
  pending.partial=null;
  renderMessages();$('typing').classList.remove('hidden');$('send-button').disabled=true;$('message-input').disabled=true;updateChrome();scrollBottom();
  try{
    const result=await streamMessage(`/v1/sessions/${state.session.id}/messages/stream`,pending.request,(type,data)=>{
      if(type==='meta')$('typing-label').textContent=data.path==='deep'?'在认真梳理你的关切':'正在回应你';
      if(type==='delta'){
        if(!pending.partial){pending.partial={id:'draft-assistant',role:'assistant',content:'',streaming:true,created_at:new Date().toISOString()};state.messages.push(pending.partial);renderMessages();}
        pending.partial.content+=data.text;
        const bubble=$('messages').querySelector('[data-message-id="draft-assistant"] .bubble');if(bubble)bubble.textContent=pending.partial.content;
        $('typing').classList.add('hidden');scrollBottom(false);
      }
    });
    state.messages=state.messages.filter(m=>m!==pending.message&&m!==pending.partial);state.messages.push(...result.messages);state.pending=null;
  }catch(error){pending.message.pending=false;pending.message.failed=true;if(pending.partial)pending.partial.interrupted=true;toast(error.message);}
  finally{state.busy=false;$('typing').classList.add('hidden');$('send-button').disabled=false;$('message-input').disabled=false;
    $('typing-label').textContent='正在认真听你说';renderMessages();updateChrome();scrollBottom();}
}
async function submitMessage(event) {
  event.preventDefault();if(state.busy || state.opening || state.submitting)return;const content=$('message-input').value.trim();if(!content)return;
  if(state.pending){toast('上一条还未发送成功，请先重试，或开启新对话。');return;}
  state.submitting=true;
  try {
  if(!state.session)await newSession(state.mode);
  if(!state.session)return;
  const message={id:'pending',role:'user',content,created_at:new Date().toISOString(),pending:true};
  state.pending={request:{content,request_id:crypto.randomUUID(),processing_mode:$('deep-mode').getAttribute('aria-pressed')==='true'?'deep':'auto'},message};state.messages.push(message);
  $('message-input').value='';$('deep-mode').setAttribute('aria-pressed','false');resizeInput();await sendPending();
  } finally { state.submitting=false; }
}
async function loadProfile(){
  const data=await api('/v1/me/profile'),isDemo=(state.session?.mode||state.mode)==='demo';
  $('profile-demo-note').classList.toggle('hidden',!isDemo);$('profile-memory-note').classList.toggle('hidden',data.memory_enabled);
  const container=$('profile-list');container.replaceChildren();
  layers.forEach(([key,label,en,empty])=>{
    const section=node('div','layer-section'),header=node('div','layer-header');header.append(node('strong','',label),node('span','',en));section.append(header);
    const claims=isDemo?[]:data.claims.filter(c=>c.layer===key);
    if(isDemo && key==='behavior'){
      const demo=node('div','claim');demo.append(node('p','','示例：希望先被倾听，再一起讨论办法。'),node('span','claim-status','仅为展示示例'));section.append(demo);
    }else if(!claims.length)section.append(node('p','layer-empty',empty));
    claims.forEach(claim=>{const card=node('div','claim');card.append(node('p','',claim.statement),node('span','claim-status',claim.status==='user_confirmed'?'你已确认':claim.status==='supported'?'多次表达支持 · 仍可纠正':'待你确认 · 暂时理解'));
      const details=node('details'),summary=node('summary','','来自这些表达');details.append(summary);
      claim.evidence.forEach(e=>{details.append(node('blockquote','',`“${e.quote}”${e.source_type==='user_correction'?' · 你的纠正':''}`));});card.append(details);
      const actions=node('div','claim-actions');[['confirm','符合我'],['correct','想纠正'],['retract','不再保留']].forEach(([action,label])=>{
        const b=node('button','',label);b.disabled=state.busy;
        b.addEventListener('click',safeAction(async()=>{if(!ensureIdle())return;let statement='';
          if(action==='correct'){const answer=await ask('你更希望怎样描述自己？','你的解释会优先于模型推断。','保存纠正',claim.statement);if(answer===null)return;statement=answer;}
          if(action==='retract' && !await ask('不再保留这项理解？','它会从后续的活跃记忆中撤回。','撤回理解'))return;
          await api(`/v1/me/profile/claims/${claim.id}`,'PATCH',{action,statement});await loadProfile();toast('已更新对你的理解。');}));actions.append(b);});card.append(actions);section.append(card);});container.append(section);
  });
}
function ask(title,description,confirm,initial){
  return new Promise(resolve=>{
    const modal=$('modal');$('modal-title').textContent=title;$('modal-description').textContent=description;$('modal-confirm').textContent=confirm;
    const editing=initial!==undefined;$('modal-input').classList.toggle('hidden',!editing);$('modal-input').value=initial||'';
    const finish=value=>{modal.close();$('modal-form').onsubmit=null;$('modal-cancel').onclick=null;modal.oncancel=null;resolve(value);};
    $('modal-form').onsubmit=event=>{event.preventDefault();if(editing && !$('modal-input').value.trim())return;finish(editing?$('modal-input').value.trim():true);};
    $('modal-cancel').onclick=()=>finish(editing?null:false);modal.oncancel=event=>{event.preventDefault();finish(editing?null:false);};modal.showModal();
  });
}
async function chooseMode(mode){
  if(!ensureIdle())return;
  if(mode==='cloud'&&!state.config.cloud_configured){toast('请在项目 .env 中配置云端 API 后重启服务。');return;}
  if(mode==='demo'&&!state.config.demo_enabled)return;
  if(state.session?.mode===mode){await switchView('chat');return;}
  await newSession(mode);
}
async function init(){
  void api('/v1/bookstore/weather').catch(()=>{});
  state.config=await api('/v1/bootstrap?reset_for_test=1','POST');if(state.config.test_reset_on_reload){localStorage.removeItem('deep-empathy-session');localStorage.removeItem('deep-empathy-store-session');state.pending=null;}state.mode=state.config.cloud_configured?'cloud':state.config.demo_enabled?'demo':'cloud';
  state.sessions=await api('/v1/sessions');const last=localStorage.getItem('deep-empathy-session');const session=state.sessions.find(s=>s.id===last);
  if(session)await selectSession(session);else{state.session=null;state.messages=[];state.cursor=null;renderMessages();}
  updateChrome();
}
$('deep-mode').addEventListener('click',()=>{if(!state.busy)$('deep-mode').setAttribute('aria-pressed',String($('deep-mode').getAttribute('aria-pressed')!=='true'));});
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',safeAction(()=>switchView(b.dataset.view))));
$('new-chat').addEventListener('click',safeAction(()=>newSession()));
$('mode-banner').addEventListener('click',safeAction(()=>switchView('settings')));
$('composer').addEventListener('submit',safeAction(submitMessage));
$('message-input').addEventListener('input',resizeInput);
$('message-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('composer').requestSubmit();}});
$('choose-cloud').addEventListener('click',safeAction(()=>chooseMode('cloud')));
$('choose-demo').addEventListener('click',safeAction(()=>chooseMode('demo')));
$('load-older').addEventListener('click',safeAction(async()=>{if(!state.cursor||!state.session)return;
  const data=await api(`/v1/sessions/${state.session.id}/messages?before=${encodeURIComponent(state.cursor)}`);
  state.messages=[...data.items,...state.messages];state.cursor=data.next_cursor;renderMessages();}));
$('memory-toggle').addEventListener('click',safeAction(async()=>{if(!ensureIdle())return;
  const enabled=!state.config.memory_enabled;await api('/v1/me/memory-settings','PATCH',{enabled});state.config.memory_enabled=enabled;updateChrome();toast(enabled?'长期记忆已开启。':'已暂停长期记忆，仅使用当前会话。');}));
$('delete-all').addEventListener('click',safeAction(async()=>{if(!ensureIdle())return;
  if(!await ask('删除全部对话与记忆？','你的对话、理解、反馈和本地身份将被永久删除，无法恢复。','删除全部'))return;
  await api('/v1/me/data','DELETE');localStorage.removeItem('deep-empathy-session');state.pending=null;await init();await switchView('chat');toast('全部数据已删除，新的空间已准备好。');}));
function updateClock(){$('clock').textContent=new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}updateClock();setInterval(updateClock,60000);
safeAction(init)();
