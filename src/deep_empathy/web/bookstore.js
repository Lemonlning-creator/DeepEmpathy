import {startLatency,publishLatency,firstVisibleText} from './bookstore-latency.mjs?v=20261117-timing1';
import {spokenActions,userSpokenActions,SceneActionQueue} from './bookstore-actions.mjs?v=20261120-four-sofas1';
import {InsightPanel,renderInsights} from './bookstore-insights.mjs?v=20261118-profile-status8';
import {BookstoreWorld,BOOKS,PLACES,SEATS,SOFAS,findPath,walkable} from './bookstore-state.mjs?v=20261120-indoor-mask6';
import {BookstoreScene} from './bookstore-scene.js?v=20261120-indoor-mask6';
import {interruption} from './bookstore-life.mjs?v=20261113-layout3';
import {api,streamChat} from './bookstore-api.js?v=20261117-timing1';
const $=id=>document.getElementById(id);
const latencyBenchmark=new URLSearchParams(location.search).get('benchmark')==='1';
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const world=new BookstoreWorld();
let stage,config,session,sessionPromise,actor='user',selection={type:'door',id:'door'},chatBusy=false,pendingChat=null,pendingEvents=[],flushTimer,pollTimer,insightBusy=false,activeLayer='behavior',lastInsight='',reading=null,readPage=0,editingClaim=null;
const actorBusy={boss:false,user:false};
const actionQueue=new SceneActionQueue({
  waitSafe:()=>new Promise(resolve=>{const check=()=>{if(!actorBusy.user&&!actorBusy.boss&&!lifeRunning&&!extraction()&&world.people.boss.pose!=='walking')resolve();else setTimeout(check,100);};check();}),
  canRun:()=>world.people.user.present&&channel()==='in_person'&&!!agendaState?.open,
  execute:async action=>{attentionUntil=Date.now()+60000;if(action.type==='serve_coffee'){await run('boss',settleHands);await serveCoffee();}else await bringBook(action.bookId);},
  onError:error=>{toast(error.message);chatLine('event',`场景动作未完成：${error.message}`);},
});
const userActionQueue=new SceneActionQueue({
  waitSafe:()=>new Promise(resolve=>{const check=()=>{if(!actorBusy.user&&!actionQueue.pending.length&&!actorBusy.boss)resolve();else setTimeout(check,100);};check();}),
  canRun:()=>world.people.user.present&&channel()==='in_person',
  execute:action=>run('user',async()=>{
    const p=world.people.user;
    if(!SEATS[p.seat]?.table)await near('user',world.tableFor('user'));
    world.startTableAction('user',action.type,action.bookId);
    try{await new Promise(resolve=>{const check=()=>{if(!p.tableAction)resolve();else setTimeout(check,100);};check();});}
    finally{world.finishTableAction('user');}
  }),
  onError:error=>{toast(error.message);chatLine('event',`用户动作未执行：${error.message}`);},
});
const layerLabels=[['behavior','习惯'],['identity','背景'],['cognition','思考'],['regulation','应对'],['core','内心']];
const names={autonomy:'自主与选择',competence:'能力与成长',relatedness:'联结与接纳',mastery:'自我进步',performance:'外部认可',avoidance:'避免受挫'};
let preparingChat=false;
let toastTimer,agendaState=null,lifeTimer,lastLifeStep='',attentionUntil=0,lifeRunning=false;
const channel=()=>$('interaction-mode').value;
const extraction=()=>world.coffee.phase==='brewing'&&world.coffee.maker==='boss';
let weatherState=null,weatherTimer;
function applyWeather(){
  const preview=$('weather-preview').value;
  const data=preview==='live'?weatherState:{kind:preview,label:({rain:'雨天',snow:'雪天',clear:'晴天',overcast:'阴天'})[preview],wind_ms:3};
  stage?.setWeather(data||{kind:'unknown'});
  document.querySelector('.sun-symbol').textContent=({rain:'☂',storm:'☂',snow:'❄',fog:'≋',cloudy:'☁',overcast:'☁'})[data?.kind]||(agendaState?.open?'☀':'☾');
  const label=$('shop-weather');
  if(preview!=='live'){label.textContent=`天气预览 · ${data.label}（非实时）`;label.title='手动测试预览，不代表当天实际天气';return;}
  label.textContent=data?`${data.location} · ${data.label}${data.temperature_c===undefined?'':` · ${Math.round(data.temperature_c)}°C`}${data.stale?'（上次数据）':''}`:'天气同步中';
  label.title=data?.observed_at?`Open-Meteo 当前天气估计 · ${data.observed_at.replace('T',' ')} · 每10分钟更新缓存`:'Open-Meteo · 天气未连接时不模拟实际降雨';
}
async function syncWeather(){
  try{const data=await api('/v1/bookstore/weather');if(chatBusy||preparingChat)return;weatherState=data;}catch{if(chatBusy||preparingChat)return;weatherState={kind:'unknown',location:'书屋',label:'天气暂不可用'};}applyWeather();
}
async function syncAgenda(){
  try{const wasOpen=agendaState?.open;agendaState=await api('/v1/bookstore/agenda');if(wasOpen&&!agendaState.open){$('interaction-mode').value='online';chatLine('event','18:00 闭店熄灯，聊天已切换线上；可以整理物品后离店。');attentionUntil=0;}world.setOwnerOpen(agendaState.open);stage?.setOpen(agendaState.lights_on);document.querySelector('.sun-symbol').textContent=agendaState.open?'☀':'☾';
    $('shop-clock').textContent=`${agendaState.now.slice(11,16)} 北京时间 · ${agendaState.open?'营业中':'已闭店'}`;
    $('daily-schedule').replaceChildren(...agendaState.schedule.map(s=>el('p','',`${s.start}–${s.end} ${s.activity}`)));
    updateControls();applyWeather();void liveDay();
  }catch(error){$('owner-life').textContent='日程连接中断，暂停自主行动';agendaState=null;updateControls();}
}
async function settleHands(){const held=world.people.boss.held;if(held?.kind==='book')await returnBook('boss');if(held?.kind==='cup')await putCup('boss','counter');}
async function liveDay(){
  if(!stage||!agendaState||lifeRunning)return;
  if(!agendaState.open){$('owner-life').textContent='林予 · 已离店，线上聊天可用';return;}
  const hold=(channel()==='in_person'&&(chatBusy||preparingChat))||Date.now()<attentionUntil;
  $('owner-life').textContent=`林予 · ${hold?(extraction()?'等待萃取安全点，再招呼朋友':'与朋友相处，稍后继续日程'):agendaState.activity}`;
  if(hold||actionQueue.pending.length||actorBusy.boss||world.people.boss.pose==='walking'||extraction()||lastLifeStep===agendaState.step)return;
  lastLifeStep=agendaState.step;lifeRunning=true;
  try{await run('boss',async()=>{
    await settleHands();if(Date.now()<attentionUntil||(chatBusy&&channel()==='in_person'))return;
    const target=agendaState.target;await near('boss',target);
    if(Date.now()<attentionUntil||(chatBusy&&channel()==='in_person'))return;
    if(!agendaState.open)return;
    if(target.startsWith('shelf')){const b=BOOKS.find(b=>b.shelf===target);if(b&&!world.books[b.id].holder&&world.books[b.id].location==='shelf'){world.takeBook('boss',b.id);world.read('boss');}}
    if(target==='chair'&&!Object.values(world.people).some(p=>p.seat==='chair')){const b=BOOKS.find(b=>!world.books[b.id].holder&&world.books[b.id].location==='shelf');if(b){await takeBook('boss',b.id);await near('boss','chair');world.sit('boss','chair');world.read('boss');}}
    if(target==='coffee'&&world.cup.full&&!world.cup.holder&&world.cup.location==='counter'){await takeCup('boss');world.drink('boss');await putCup('boss','counter');}
    if(target==='coffee'&&agendaState.phase==='coffee'&&!world.cup.holder&&!world.cup.full&&world.cup.location==='counter')world.brew('boss');
    if(['opening','closing'].includes(agendaState.phase))world.people.boss.gestureRemaining=3;
  });}catch(error){toast(`日程稍作调整：${error.message}`);}finally{lifeRunning=false;}
}
async function attend(inPerson){
  if(!inPerson||actionQueue.pending.length)return;
  attentionUntil=Date.now()+60000;
  if(interruption({brewing:extraction(),walking:world.people.boss.pose==='walking',busy:actorBusy.boss,inPerson})==='wait'){
    $('chat-status').textContent=extraction()?'萃取完成后再过来':'完成手边动作后过来';
    await new Promise(resolve=>{const timer=setInterval(()=>{if(!extraction()&&!actorBusy.boss&&world.people.boss.pose!=='walking'){clearInterval(timer);resolve();}},100);});
  }
  await run('boss',async()=>{await settleHands();const u=world.people.user;if(u.present){const point=[[u.position[0]+1,u.position[1]],[u.position[0]-1,u.position[1]],[u.position[0],u.position[1]-1]].find(p=>walkable(p));if(point)await walk('boss',point);}});
}

function toast(message){$('scene-toast').textContent=message;$('scene-toast').classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('scene-toast').classList.add('hidden'),4000);}
const safe=fn=>async(...args)=>{try{return await fn(...args);}catch(error){toast(error.message||'这次操作暂时没能完成。');}};
function chatLine(role,text,label){const line=el('div',`chat-line ${role}`);if(role!=='event')line.append(el('span','chat-speaker',label||(role==='user'?'你':'林予')));const bubble=el(role==='event'?'span':'div',role==='event'?'':'chat-bubble',text);line.append(bubble);$('store-chat-messages').append(line);scrollChat();return {line,bubble};}
function scrollChat(){requestAnimationFrame(()=>$('store-chat-messages').scrollTo({top:$('store-chat-messages').scrollHeight,behavior:'instant'}));}
function emptyWelcome(){$('store-chat-messages').querySelector('.chat-welcome')?.remove();}
async function ensureSession(){
  if(!config)throw new Error('正在连接后端，请稍等。');
  if(session)return session;if(sessionPromise)return sessionPromise;
  sessionPromise=(async()=>{session=await api('/v1/sessions','POST',{mode:$('connection-mode').value});if(!latencyBenchmark)localStorage.setItem('deep-empathy-store-session',session.id);await flushEvents();return session;})();
  try{return await sessionPromise;}finally{sessionPromise=null;}
}
async function flushEvents(){
  if(!session||chatBusy||!pendingEvents.length)return;const ownerSession=session.id,batch=pendingEvents.splice(0,30);
  try{await api(`/v1/sessions/${ownerSession}/scene-events`,'POST',{events:batch});if(pendingEvents.length)scheduleFlush();}
  catch{pendingEvents=[...batch,...pendingEvents].slice(-300);}
}
function scheduleFlush(){clearTimeout(flushTimer);flushTimer=setTimeout(()=>void flushEvents(),500);}
world.subscribe(event=>{
  pendingEvents.push(event);scheduleFlush();$('last-event').textContent=event.description;updateControls();renderActions();
  if(['enter','leave','coffee_ready','deliver_cup','deliver_book','put_book','put_cup'].includes(event.action)){emptyWelcome();chatLine('event',event.description);}
});
function select(target){selection=target;document.querySelectorAll('[data-place]').forEach(b=>b.classList.toggle('selected',b.dataset.place===target.type||(target.type==='book'&&b.dataset.place==='shelf')));renderActions();}
async function walk(id,point){const p=world.actor(id);if(p.seat)world.stand(id);if(Math.hypot(p.position[0]-point[0],p.position[1]-point[1])<.15)return;
  const path=p.position[1]>3.7?[point]:findPath(p.position,point);world.startWalk(id,path);await stage.waitWalk(id);
}
async function near(id,place){const target=PLACES[place];await walk(id,id==='boss'&&target.bossPoint?target.bossPoint:target.point);}
async function run(id,fn){if(id==='boss'&&extraction())throw new Error('萃取结束后才能离开咖啡机。');if(!stage)throw new Error('三维场景尚未就绪。');world.actor(id);if(actorBusy[id])throw new Error('这个角色还在完成上一个动作，请稍等。');actorBusy[id]=true;updateControls();renderActions();try{await fn();}finally{actorBusy[id]=false;updateControls();renderActions();}}
async function enter(){if(world.people.user.present)return leave();await syncAgenda();if(!agendaState?.open)throw new Error('书店已闭店（09:00–18:00 营业），可以随时选择线上聊天。');$('interaction-mode').value='in_person';await ensureSession();world.enter();actor='user';emptyWelcome();await run('user',async()=>{await walk('user',PLACES.door.point);const seat=['sofa-left','chair','sofa-front-left'].find(s=>!Object.values(world.people).some(p=>p.present&&p.seat===s));if(seat)await sit('user',seat);});await attend(true);chatLine('assistant','来了，先坐一会儿。今天想聊些什么？','林予 · 场景招呼');await refreshInsights();}
async function leave(){if(userActionQueue.pending.length)throw new Error('请等桌面动作完成再离店。');if(actionQueue.pending.length)throw new Error('林予正在完成约好的动作，请稍等再离店。');if(chatBusy)throw new Error('先等这句话说完，再慢慢出门吧。');if(actorBusy.user)throw new Error('等脚步停下来，再离店吧。');await run('user',async()=>{const p=world.people.user;if(p.held?.kind==='book'){await near('user',world.books[p.held.id].shelf);world.returnBook('user');}if(p.held?.kind==='cup'){await near('user','table');world.putCup('user','table');}await near('user','door');world.leave();actor='user';$('interaction-mode').value='online';attentionUntil=0;});await flushEvents();if(session)await api(`/v1/sessions/${session.id}/consolidate`,'POST');}
async function sit(id,seat){await near(id,SEATS[seat].place);world.sit(id,seat);}
async function takeBook(id,bookId){await near(id,world.books[bookId].location.startsWith('table')?world.books[bookId].location:world.books[bookId].shelf);world.takeBook(id,bookId);}
async function returnBook(id){const p=world.actor(id);if(p.held?.kind!=='book')throw new Error('先拿一本书吧。');await near(id,world.books[p.held.id].shelf);world.returnBook(id);}
async function takeCup(id){await near(id,world.cup.location.startsWith('table')?world.cup.location:'cup');world.takeCup(id);}
async function putCup(id,where){await near(id,where.startsWith('table')?where:'cup');world.putCup(id,where);}
async function deliver(id){const otherId=id==='boss'?'user':'boss',other=world.actor(otherId);if(other.held)throw new Error('对方手里还有物品，先放好再递杯。');const options=other.seat?[PLACES[SEATS[other.seat].place].point]:[[other.position[0],other.position[1]+1],[other.position[0]+1,other.position[1]],[other.position[0]-1,other.position[1]],[other.position[0],other.position[1]-1]];const point=options.find(p=>walkable(p)&&Math.hypot(p[0]-other.position[0],p[1]-other.position[1])<1.8);if(!point)throw new Error('这里递杯不太方便，请朋友先到空地。');await walk(id,point);world.deliver(id);}
async function bringBook(bookId){await run('boss',async()=>{const book=world.books[bookId];if(book.holder==='user'||book.location.startsWith('table'))return;if(world.people.boss.held?.id!==bookId){await settleHands();await takeBook('boss',bookId);}const table=world.tableFor('user');await near('boss',table);world.putBook('boss',table);});}
async function approachFriend(id){const other=world.people.user;const options=other.seat?[PLACES[SEATS[other.seat].place].point]:[[other.position[0]+1,other.position[1]],[other.position[0]-1,other.position[1]],[other.position[0],other.position[1]-1]];const target=options.find(p=>walkable(p)&&Math.hypot(p[0]-other.position[0],p[1]-other.position[1])<1.8);if(!target)throw new Error('朋友旁边没有合适的递书位置。');await walk(id,target);}
async function brew(id){await near(id,'coffee');world.brew(id);}
async function serveCoffee(){await run('boss',async()=>{if(world.people.boss.held)throw new Error('林予手里还有物品，先放好再做咖啡。');if(!world.cup.holder&&world.cup.location.startsWith('table')){await takeCup('boss');await putCup('boss','counter');}if(world.cup.holder)throw new Error('先把杯子放回吧台，林予才能准备咖啡。');if(!world.cup.full){await brew('boss');await new Promise(resolve=>{const off=world.subscribe(e=>{if(e.action==='coffee_ready'){off();resolve();}});});}await takeCup('boss');if(world.people.user.present)await putCup('boss',world.tableFor('user'));});}
function actionButton(label,handler,{disabled=false,primary=false}={}){const b=el('button',primary?'emphasized':'',label);b.disabled=disabled||actorBusy[actor];b.type='button';b.addEventListener('click',safe(handler));$('object-actions').append(b);}
function renderActions(){
  const actions=$('object-actions');actions.replaceChildren();const active=world.people[actor],available=active.present,type=selection.type;
  $('object-eyebrow').textContent=type==='door'?'A FRIEND IS ALWAYS WELCOME':'LITTLE THINGS, REAL MOMENTS';
  let title=PLACES[selection.id]?.name||'一本可以慢慢读的书',description='选中物件后，角色会先走近，再完成动作。';
  if(type==='shelf'||type==='book'){
    const book=type==='book'?world.books[selection.id]:BOOKS.find(b=>b.shelf===selection.id);title=type==='book'?`《${book.title}》`:PLACES[selection.id].name;description='从书架取书，找个位置阅读；读完后放回原来的书架。';
    actionButton('走近书架',()=>run(actor,()=>near(actor,book.shelf)),{disabled:!available});
    actionButton(`取《${book.title}》`,()=>run(actor,()=>takeBook(actor,book.id)),{disabled:!available||!!active.held||!!world.books[book.id].holder,primary:true});
    actionButton('翻开阅读',()=>{const b=world.read(actor);openReader(b,actor);},{disabled:!available||active.held?.kind!=='book'});
    actionButton('放到桌上',()=>run(actor,async()=>{await near(actor,'table');world.putBook(actor);}),{disabled:!available||active.held?.kind!=='book'});
    actionButton('归还书籍',()=>run(actor,()=>returnBook(actor)),{disabled:!available||active.held?.kind!=='book'});
  }else if(type==='sofa'||type==='chair'){
    description='窗边两张单人沙发面对面，共享圆桌；角落设独立阅读座与小圆桌，旁边留出绿植角。林予平时在窗边阅读。';const chosen=SEATS[selection.id];title=chosen?.name||'单人沙发';actionButton('走近',()=>run(actor,()=>near(actor,chosen?.place||selection.id)),{disabled:!available});
    const seats=type==='sofa'?(chosen?[selection.id]:SOFAS.map(s=>s.id)):['chair'];for(const seat of seats)actionButton(type==='chair'?'坐下':SEATS[seat].name,()=>run(actor,()=>sit(actor,seat)),{disabled:!available||Object.values(world.people).some(p=>p.present&&p.seat===seat),primary:true});
    actionButton('起身',()=>world.stand(actor),{disabled:!available||!active.seat});
  }else if(type==='exhibition'){
    title='主题书展 · 在故事里慢下来';description='中央低矮书展台，展示本周主题书单。取书与阅读仍使用后方书架里的实际书目。';actionButton('走近书展台',()=>run(actor,()=>near(actor,'exhibition')),{disabled:!available});for(const book of BOOKS)actionButton(`取阅《${book.title}》`,()=>run(actor,async()=>{await takeBook(actor,book.id);openReader(world.read(actor),actor);}),{disabled:!available||!!active.held});
  }else if(type==='coffee'){
    description='咖啡需要约四秒。萃取完成后，拿起杯子，递给朋友。';actionButton('走近咖啡机',()=>run(actor,()=>near(actor,'coffee')),{disabled:!available});
    actionButton(world.coffee.phase==='brewing'?'正在萃取…':'制作咖啡',()=>run(actor,()=>brew(actor)),{disabled:!available||world.coffee.phase==='brewing'||world.cup.full||!!world.cup.holder||world.cup.location!=='counter',primary:true});
    actionButton('拿起咖啡杯',()=>run(actor,()=>takeCup(actor)),{disabled:!available||!!active.held||!!world.cup.holder||world.coffee.phase==='brewing'});
    actionButton('老板请朋友喝咖啡',serveCoffee,{disabled:!world.people.user.present||actorBusy.boss});
  }else if(type==='cup'||type==='table'){
    title=type==='table'?(PLACES[selection.id]?.name||'阅读小桌'):'一只温暖的咖啡杯';if(type==='table')actionButton('走近桌子',()=>run(actor,()=>near(actor,selection.id)),{disabled:!available});description=world.cup.holder?`杯子现在在${world.people[world.cup.holder].name}手里。`:world.cup.full?'杯中的咖啡做好了。':'杯子是空的，可以放回吧台制作咖啡。';
    actionButton('拿起杯子',()=>run(actor,()=>takeCup(actor)),{disabled:!available||!!active.held||!!world.cup.holder||world.coffee.phase==='brewing'});
    actionButton('递给对方',()=>run(actor,()=>deliver(actor)),{disabled:!available||active.held?.kind!=='cup'||!world.people.user.present,primary:true});
    actionButton('饮用',()=>world.drink(actor),{disabled:!available||active.held?.kind!=='cup'||!world.cup.full});
    actionButton('放到这张桌子',()=>run(actor,()=>putCup(actor,type==='table'?selection.id:'table')),{disabled:!available||active.held?.kind!=='cup'});
    actionButton('放回吧台',()=>run(actor,()=>putCup(actor,'counter')),{disabled:!available||active.held?.kind!=='cup'});
  }else if(type==='counter'){
    description='林予会按真实日程安排生活，你可以走近打招呼。';actionButton('走近收银台',()=>run(actor,()=>near(actor,'counter')),{disabled:!available,primary:true});actionButton('林予回到吧台',()=>run('boss',()=>near('boss','counter')),{disabled:true});
  }else{
    title='书店的门，为朋友留着';description=world.people.user.present?'离店前会归还手里的书、放好杯子，再走到门口。':agendaState?.open?'营业中，推门进来，找个位置坐坐。':'已闭店，09:00–18:00 可以到店，线上聊天随时可用。';actionButton(world.people.user.present?'整理物品，离店':'推门进店',enter,{primary:true});
  }
  if(type==='table'){actionButton('放下手中的书',()=>run(actor,async()=>{await near(actor,selection.id);world.putBook(actor,selection.id);}),{disabled:!available||active.held?.kind!=='book'});for(const book of Object.values(world.books).filter(b=>b.location===selection.id)){actionButton(`阅读《${book.title}》`,()=>openReader(world.readTableBook(actor,book.id),actor),{disabled:!available});actionButton(`归还《${book.title}》`,()=>run(actor,async()=>{await takeBook(actor,book.id);await returnBook(actor);}),{disabled:!available||!!active.held});}actionButton('喝桌上的咖啡',()=>world.drinkAtTable(actor),{disabled:!available||world.cup.location!==selection.id||!!world.cup.holder||!world.cup.full});}
  $('object-title').textContent=title;$('object-description').textContent=description;
}
function updateControls(){
  const present=world.people.user.present;$('enter-store').replaceChildren(document.createTextNode(present?'慢慢离店':'推门进店'),el('span','','↗'));$('enter-store').disabled=actorBusy.user||chatBusy||actionQueue.pending.length>0||userActionQueue.pending.length>0;
  $('actor-boss').disabled=true;$('actor-boss').title='林予会自主安排生活';$('actor-user').disabled=!present;$('actor-user').setAttribute('aria-pressed',String(actor==='user'));$('actor-boss').setAttribute('aria-pressed',String(actor==='boss'));
  const p=world.people[actor];$('actor-status').textContent=!p.present?'朋友尚未进店 · 可随时线上聊天':actorBusy[actor]?'正在完成动作…':p.pose==='walking'?'走路中':p.pose==='sitting'?'坐着休息':p.held?.kind==='book'?'手里拿着一本书':p.held?.kind==='cup'?'手里拿着杯子':'站立 · 点击空地行走';
  $('visitor-legend').replaceChildren(el('i','dot visitor-dot'),document.createTextNode(present?'朋友 · 你':'朋友尚未进店'));
  $('stand-up').disabled=!p.present||actorBusy[actor];const configuredMode=config&&($('connection-mode').value==='cloud'?config.cloud_configured:config.demo_enabled);const canChat=configuredMode&&(channel()==='online'||(present&&agendaState?.open));$('store-chat-input').disabled=!canChat||chatBusy;$('store-send').disabled=!canChat||chatBusy;$('weather-preview').disabled=chatBusy||preparingChat;
  $('store-chat-input').placeholder=channel()==='online'?'随时给林予发条线上消息…':present?'今天想和林予聊点什么？':'推门进来，再和林予说说话…';
}
function openReader(book,reader){reading={book,reader};readPage=0;renderReader();$('reader-dialog').showModal();}
function renderReader(){$('reader-title').textContent=reading.book.title;$('reader-text').textContent=reading.book.pages[readPage];$('reader-page').textContent=`${readPage+1} / ${reading.book.pages.length}`;$('reader-prev').disabled=readPage===0;$('reader-next').disabled=readPage===reading.book.pages.length-1;}
async function refreshInsights(force=false){
  if(!session||insightBusy||(!force&&document.hidden))return;insightBusy=true;const sid=session.id;
  try{const data=await api(`/v1/sessions/${sid}/insights`);if(session?.id!==sid)return;
    $('insight-status').textContent=data.mode==='demo'?'固定演示':data.modeling_status==='running'||data.modeling_status==='pending'?'正在整理':data.modeling_status==='failed'?'整理暂缓':'实时同步';$('insight-status').classList.toggle('updating',['running','pending'].includes(data.modeling_status));
    const stamp=JSON.stringify(data);if(stamp===lastInsight&&!force)return;lastInsight=stamp;renderProfile(data);
  }catch{$('insight-status').textContent='等待连接';}finally{insightBusy=false;}
}
let profileData={claims:[]};
const insightPanels=new Map();
function insightModel(){const key=session?.id||'initial';if(!insightPanels.has(key))insightPanels.set(key,new InsightPanel());return insightPanels.get(key);}
function renderProfile(data){profileData=data;const model=insightModel();model.observe(data);renderInsights(model);}

function attachFeedback(message,line){const row=el('div','chat-feedback');for(const [rating,label] of [['helpful','有被理解'],['missed','还差一点']]){const b=el('button',message.feedback===rating?'selected':'',label);b.addEventListener('click',safe(async()=>{await api(`/v1/turns/${message.turn_id}/feedback`,'POST',{rating});message.feedback=rating;row.querySelectorAll('button').forEach(n=>n.classList.remove('selected'));b.classList.add('selected');}));row.append(b);}line.append(row);}
async function sendPending(){
  if(!pendingChat||chatBusy)return;const pending=pendingChat;chatBusy=true;updateControls();$('chat-error').classList.add('hidden');$('chat-status').textContent='正在听你说';
  pending.partial?.line.remove();pending.partial=null;
  if(!pending.timing||pending.timing.processing)pending.timing=startLatency(pending.request.request_id,performance.now());
  $('store-chat-messages').dataset.activeTiming=pending.request.request_id;
  publishLatency(pending.timing);
  try{await ensureSession();const result=await streamChat(session.id,pending.request,(type,data)=>{
    if(type==='request_sent'){pending.timing.request_sent_ms=performance.now()-pending.timing.started;publishLatency(pending.timing);}
    if(type==='meta'){$('chat-status').textContent=data.path==='deep'?'在认真梳理':'正在回应';if(data.weather){weatherState=data.weather;$('weather-preview').value=data.weather.is_preview?data.weather.kind:'live';applyWeather();}}
    if(type==='delta'){if(!pending.partial){pending.partial=chatLine('assistant','');pending.partial.line.classList.add('partial');}if(pending.timing.first_delta_ms===null&&data.text?.trim())pending.timing.first_delta_ms=performance.now()-pending.timing.started;pending.partial.bubble.textContent+=data.text;if(pending.partial.bubble.textContent.trim())firstVisibleText(pending.timing);scrollChat();}
  });insightModel().completeRound(result.turn_id);pending.timing.processing=result.processing;pending.timing.completed=true;publishLatency(pending.timing);pending.user.line.remove();pending.partial?.line.remove();for(const m of result.messages){const row=chatLine(m.role,m.content);if(m.role==='assistant')attachFeedback(m,row.line);}const reply=result.messages.find(m=>m.role==='assistant')?.content||'';const actions=spokenActions(reply,{mode:pending.request.interaction_mode,present:world.people.user.present,catalog:world.context().book_catalog,userContent:pending.request.content});actionQueue.enqueue(result.turn_id,actions);pendingChat=null;$('chat-status').textContent='像朋友一样';
  }catch(error){$('chat-error').classList.remove('hidden');$('chat-error').querySelector('span').textContent=error.message;pending.partial?.line.append(el('span','chat-speaker','回复中断 · 未确认保存'));$('chat-status').textContent='可以重试';}
  finally{chatBusy=false;updateControls();scheduleFlush();await refreshInsights(true);if(weatherState?.kind==='unknown')void syncWeather();}
}
async function submitChat(event){event.preventDefault();const submittedAt=performance.now();if(chatBusy||preparingChat)return;if(channel()==='in_person'&&(!world.people.user.present||!agendaState?.open))throw new Error('面对面聊天需要在营业时间进店，也可以切换线上。');const content=$('store-chat-input').value.trim();if(!content)return;if(pendingChat)throw new Error('上一句话还未确认保存，请先点击重试。');
  // Body actions remain safety-gated, but never hold the text/model request.
  if(channel()==='in_person')void safe(()=>attend(true))();
  insightModel().beginRound();renderInsights(insightModel());
  emptyWelcome();pendingChat={request:{content,weather_snapshot_id:weatherState?.snapshot_id||null,weather_preview:$('weather-preview').value==='live'?null:$('weather-preview').value,request_id:crypto.randomUUID(),interaction_mode:channel(),processing_mode:$('store-deep-mode').getAttribute('aria-pressed')==='true'?'deep':'auto',scene:{...world.context(),pending_user_actions:userSpokenActions(content,{mode:channel(),present:world.people.user.present,catalog:world.context().book_catalog}).map(a=>a.type),pending_actions:actionQueue.pending.map(a=>a.type),owner_activity:agendaState?.activity||'同步中',interruption:(extraction()||actorBusy.boss||world.people.boss.pose==='walking')?'waiting_safe_point':'interacting'}},user:chatLine('user',content),partial:null};pendingChat.timing=startLatency(pendingChat.request.request_id,submittedAt);$('store-chat-input').value='';$('store-deep-mode').setAttribute('aria-pressed','false');userActionQueue.enqueue(pendingChat.request.request_id,userSpokenActions(content,{mode:channel(),present:world.people.user.present,catalog:world.context().book_catalog}));await sendPending();
}
async function init(){
  try{stage=new BookstoreScene($('world-canvas'),world,{onPick:select,onFloor:safe(point=>run(actor,()=>walk(actor,point)))});$('scene-loading').classList.add('hidden');}
  catch(error){$('scene-loading').classList.add('error');$('scene-loading').textContent='三维场景未能启动。请使用支持 WebGL 的现代浏览器并开启硬件加速。';console.error('Bookstore renderer unavailable',error.name);}
  void syncWeather();weatherTimer=setInterval(()=>void syncWeather(),300000);
  await syncAgenda();lifeTimer=setInterval(()=>void syncAgenda(),5000);
  config=await api('/v1/bootstrap?reset_for_test=1','POST');if(config.test_reset_on_reload){localStorage.removeItem('deep-empathy-store-session');localStorage.removeItem('deep-empathy-session');document.querySelector('.chat-footnote').textContent='测试模式 · 刷新页面将清空对话与记忆，恢复初始画像';}$('weather-preview-control').hidden=!config.test_reset_on_reload;const mode=$('connection-mode');mode.querySelector('[value=cloud]').disabled=!config.cloud_configured;mode.querySelector('[value=demo]').disabled=!config.demo_enabled;mode.value=config.cloud_configured?'cloud':config.demo_enabled?'demo':'cloud';
  $('chat-mode-note').textContent=mode.value==='demo'?'固定脚本 · 不分析自由输入':config.cloud_configured?'云端 AI · 流式陪伴':'请先在服务端配置云端 API';
  const saved=latencyBenchmark?null:localStorage.getItem('deep-empathy-store-session');if(saved){const sessions=await api('/v1/sessions');session=sessions.find(s=>s.id===saved&&s.mode===mode.value)||null;if(session){const history=await api(`/v1/sessions/${session.id}/messages`);if(history.items.length){emptyWelcome();for(const message of history.items){const row=chatLine(message.role,message.content);if(message.role==='assistant')attachFeedback(message,row.line);}}}}
  if(config.test_reset_on_reload&&!session)await ensureSession();
  renderProfile({claims:[],mode:mode.value});insightPanels.delete(session?.id||'initial');$('insight-status').textContent=mode.value==='demo'?'固定演示':'等待对话';await refreshInsights();pollTimer=setInterval(()=>void refreshInsights(),2500);updateControls();renderActions();
}
$('weather-preview').addEventListener('change',applyWeather);
$('interaction-mode').addEventListener('change',()=>{if(chatBusy||preparingChat){$('interaction-mode').value=pendingChat?.request.interaction_mode||'online';return;}updateControls();});
$('enter-store').addEventListener('click',safe(enter));$('actor-boss').addEventListener('click',()=>{actor='boss';updateControls();renderActions();});$('actor-user').addEventListener('click',()=>{if(world.people.user.present){actor='user';updateControls();renderActions();}});
$('stand-up').addEventListener('click',safe(()=>world.stand(actor)));$('reset-camera').addEventListener('click',()=>stage?.resetCamera());document.querySelectorAll('[data-place]').forEach(b=>b.addEventListener('click',()=>select({type:b.dataset.place,id:b.dataset.id})));
$('close-reader').addEventListener('click',()=>$('reader-dialog').close());$('reader-dialog').addEventListener('close',()=>{if(reading){world.closeBook(reading.reader);reading=null;}});$('reader-prev').addEventListener('click',()=>{if(readPage>0){readPage--;renderReader();}});$('reader-next').addEventListener('click',()=>{if(reading&&readPage<reading.book.pages.length-1){readPage++;renderReader();}});
$('store-chat-form').addEventListener('submit',safe(submitChat));$('store-chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('store-chat-form').requestSubmit();}});$('store-deep-mode').addEventListener('click',()=>{if(!chatBusy)$('store-deep-mode').setAttribute('aria-pressed',String($('store-deep-mode').getAttribute('aria-pressed')!=='true'));});$('retry-chat').addEventListener('click',safe(sendPending));
$('claim-cancel').addEventListener('click',()=>$('claim-dialog').close());$('claim-form').addEventListener('submit',safe(async event=>{event.preventDefault();const statement=$('claim-correction').value.trim();if(!statement)return;await api(`/v1/me/profile/claims/${editingClaim.id}`,'PATCH',{action:'correct',statement});$('claim-dialog').close();await refreshInsights(true);}));
$('connection-mode').addEventListener('change',safe(async()=>{if(chatBusy||pendingChat){$('connection-mode').value=session?.mode||'demo';throw new Error('先完成当前这句话，再切换陪伴方式。');}if(session){await flushEvents();await api(`/v1/sessions/${session.id}/consolidate`,'POST');}session=null;lastInsight='';localStorage.removeItem('deep-empathy-store-session');$('store-chat-messages').replaceChildren();chatLine('event','已切换陪伴方式，新的对话将独立保存。');$('chat-mode-note').textContent=$('connection-mode').value==='demo'?'固定脚本 · 不分析自由输入':'云端 AI · 流式陪伴';await ensureSession();await refreshInsights(true);}));
setInterval(()=>{$('coffee-state').textContent=world.coffee.phase==='brewing'?`正在萃取 · ${Math.ceil(world.coffee.remaining)} 秒`:world.coffee.phase==='ready'?'咖啡完成，可以拿起了':'咖啡机待机中';},250);
window.addEventListener('pagehide',()=>{clearInterval(lifeTimer);clearInterval(weatherTimer);clearInterval(pollTimer);clearTimeout(flushTimer);stage?.dispose();});
safe(init)();
