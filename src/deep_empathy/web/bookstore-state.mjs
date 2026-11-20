// Pure world rules shared by the 3D renderer and deterministic Node tests.
export const BOOKS = [
  {id:'journey',title:'沿着街巷去散步',shelf:'shelf-d',color:0x8b9d89,pages:['清晨的小巷刚刚醒来。面包店推开窗，修车师傅把凳子搬到门口。她把地图收起来，决定今天只沿着有树荫的路走。','走到河边时，她在长椅上坐了一会儿。原来离熟悉的街道两条路远，就有一处从没留意过的风景。']},
  {id:'slow',title:'把日子过慢一点',shelf:'shelf-a',color:0xc87c56,pages:['雨是在下午三点停的。小巷里的人收起伞，门口的猫却仍躲在屋檐下。林予没有催它，只把椅子挪到阳光刚好照得到的地方。','那天他原本有很长的待办清单。后来，他只做了三件事：给植物浇水，把一本旧书修好，认真听朋友讲完一件小事。','傍晚，猫终于走了出来。他想，许多事情或许并不需要被催促。给它一点空间，也给自己一点时间。']},
  {id:'night',title:'晚风经过的地方',shelf:'shelf-b',color:0x6c8d85,pages:['城里最后一班电车经过时，窗边的风铃轻轻响了。她把今天没能说出口的话写在纸上，没有寄给谁。','楼下有人在练一首不太熟的曲子，总在同一个地方停住。她听了一会儿，忽然觉得，停下来也可以是练习的一部分。','第二天，那张纸被夹进了书里。风还是从同一扇窗经过，带来树叶和面包的味道。今天可以慢慢开始。']},
  {id:'forest',title:'森林里的小小来信',shelf:'shelf-c',color:0xb49b55,pages:['一封没有地址的信落在森林入口。信上只有一句话：如果你累了，可以在这里休息。','小鹿没有替来客决定去处。它指了指河边，又指了指山坡：每条路都有自己的风景，你也可以暂时不选择。','离开时，来客留下一颗种子。没有人知道它会长成什么，但大家都愿意给它一点阳光。']},
];
export const PLACES = {
  'shelf-d':{name:'旅行与生活书架',point:[-6.87,-2.65]},
  'shelf-a':{name:'散文书架',point:[-4.1,-2.65]},
  'shelf-b':{name:'文学书架',point:[-1.0,-2.65]},
  'shelf-c':{name:'自然书架',point:[2.0,-2.65]},
  sofa:{name:'窗边对坐沙发',point:[-5.4,.9]},
  'sofa-front-left':{name:'角落阅读沙发',point:[-4.8,1.75]},
  chair:{name:'窗边阅读沙发',point:[-5.4,-1.5]},
  exhibition:{name:'主题书展台',point:[-.6,1.8]},
  coffee:{name:'咖啡机',point:[4.3,1.0],bossPoint:[4.3,-1.45]},
  cup:{name:'咖啡杯',point:[4.0,1.0],bossPoint:[4.0,-1.45]},
  table:{name:'窗边共享圆桌',point:[-5.4,-.3]},
  'table-front-left':{name:'角落阅读圆桌',point:[-3.6,1.9]},
  counter:{name:'收银台',point:[4.3,1.0],bossPoint:[4.3,-1.45]},
  door:{name:'书店入口',point:[4.3,3.25]},
};
export const SOFAS = [
  {id:'chair',place:'chair',name:'窗边北座',x:-6.6,z:-1.5,rotation:0,color:'#859673',table:'table'},
  {id:'sofa-left',place:'sofa',name:'窗边南座',x:-6.6,z:.9,rotation:Math.PI,color:'#859673',table:'table'},
  {id:'sofa-front-left',place:'sofa-front-left',name:'角落阅读座',x:-4.8,z:2.9,rotation:Math.PI/2,color:'#7f9588',table:'table-front-left'},
];
export const EXHIBITION = {x:-.6,z:.4,w:2.4,d:1.25};
export const TABLES = {
  table:{x:-6.6,z:-.3,radius:.4,height:.52},
  'table-front-left':{x:-3.6,z:2.9,radius:.34,height:.52},
};
export const SEATS = Object.fromEntries(SOFAS.map(s=>[s.id,{name:s.name,place:s.place,table:s.table,position:[s.x+Math.sin(s.rotation)*.08,s.z+Math.cos(s.rotation)*.08],rotation:s.rotation,height:.76}]));
export const OBSTACLES = [
  {x:-6.87,z:-3.5,w:2,d:.7},
  {x:-4.1,z:-3.5,w:2.65,d:.7},{x:-1,z:-3.5,w:2.65,d:.7},{x:2,z:-3.5,w:2.65,d:.7},
  EXHIBITION,
  {x:-7.15,z:2.65,w:.8,d:.8},
  ...SOFAS.map(s=>({x:s.x,z:s.z,w:Math.abs(Math.sin(s.rotation))>.5?1.1:1.35,d:Math.abs(Math.sin(s.rotation))>.5?1.35:1.1})),
  ...Object.values(TABLES).map(t=>({x:t.x,z:t.z,w:t.radius*2,d:t.radius*2})),
  {x:4.3,z:-.25,w:2.5,d:1.25},
];
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
export function walkable(point,padding=.22){return point[0]>=-7.65&&point[0]<=5.65&&point[1]>=-3.03&&point[1]<=3.7&&!OBSTACLES.some(b=>Math.abs(point[0]-b.x)<b.w/2+padding&&Math.abs(point[1]-b.z)<b.d/2+padding);}
export function findPath(start,end){
  const step=.2,origin=[-7.6,-3],width=67,height=34;
  const cell=p=>[Math.max(0,Math.min(width-1,Math.round((p[0]-origin[0])/step))),Math.max(0,Math.min(height-1,Math.round((p[1]-origin[1])/step)))];
  const point=c=>[origin[0]+c[0]*step,origin[1]+c[1]*step];
  const key=c=>c.join(',');let from=cell(start),to=cell(end);
  if(!walkable(end))throw new Error('这里暂时走不过去，请点击空地或物品旁的通道。');
  const open=[from],scores=new Map([[key(from),0]]),parents=new Map(),closed=new Set();
  while(open.length){open.sort((a,b)=>(scores.get(key(a))+distance(a,to))-(scores.get(key(b))+distance(b,to)));
    const current=open.shift(),id=key(current);if(closed.has(id))continue;closed.add(id);
    if(distance(current,to)<.1){const path=[end];let cursor=current;while(parents.has(key(cursor))){path.unshift(point(cursor));cursor=parents.get(key(cursor));}return smoothPath(start,path);}
    for(const [dx,dz] of [[1,0],[-1,0],[0,1],[0,-1]]){const next=[current[0]+dx,current[1]+dz],nextId=key(next);if(next[0]<0||next[0]>=width||next[1]<0||next[1]>=height||!walkable(point(next))||closed.has(nextId))continue;
      const score=scores.get(id)+1;if(score<(scores.get(nextId)??Infinity)){scores.set(nextId,score);parents.set(nextId,current);open.push(next);}}
  }throw new Error('通道被家具挡住了，换一个靠近的位置试试。');
}

// Shortcut grid staircases only when the whole swept segment clears furniture.
export function smoothPath(start,path){
  const clear=(a,b)=>!OBSTACLES.some(box=>{
    let lo=0,hi=1;
    for(const [axis,center,size] of [[0,box.x,box.w],[1,box.z,box.d]]){
      const min=center-size/2-.221,max=center+size/2+.221,d=b[axis]-a[axis];
      if(Math.abs(d)<1e-9){if(a[axis]<min||a[axis]>max)return false;}
      else{const t1=(min-a[axis])/d,t2=(max-a[axis])/d;lo=Math.max(lo,Math.min(t1,t2));hi=Math.min(hi,Math.max(t1,t2));if(lo>hi)return false;}
    }return hi>=0&&lo<=1;
  });
  const result=[];let origin=start,index=0;
  while(index<path.length){let next=index;for(let j=path.length-1;j>index;j--)if(clear(origin,path[j])){next=j;break;}result.push(path[next]);origin=path[next];index=next+1;}
  return result;
}
export function turnToward(current,target,dt){
  const delta=Math.atan2(Math.sin(target-current),Math.cos(target-current));
  const step=Math.min(Math.abs(delta)*(1-Math.exp(-8*dt)),3*Math.min(dt,.1));
  return current+Math.sign(delta)*step;
}

export class BookstoreWorld {
  constructor(){
    this.people={boss:{name:'林予',present:true,position:[4.3,-1.45],rotation:0,pose:'standing',seat:null,held:null,path:[]},user:{name:'朋友',present:false,position:[4.3,4.6],rotation:Math.PI,pose:'standing',seat:null,held:null,path:[]}};
    this.books=Object.fromEntries(BOOKS.map(b=>[b.id,{...b,holder:null,location:'shelf',reading:false,reader:null}]));
    this.cup={holder:null,location:'counter',full:false};this.coffee={phase:'idle',remaining:0};this.events=[];this.listeners=new Set();this.sequence=0;
  }
  subscribe(fn){this.listeners.add(fn);return()=>this.listeners.delete(fn);}
  record(action,actor,description){const event={id:`store-${Date.now()}-${++this.sequence}`,action,actor,description};this.events.push(event);this.events=this.events.slice(-30);this.listeners.forEach(fn=>fn(event));return event;}
  actor(id){const p=this.people[id];if(!p?.present)throw new Error('朋友还没进店，请先推门进来。');return p;}
  near(id,place){const p=this.actor(id),v=PLACES[place];return distance(p.position,id==='boss'&&v.bossPoint?v.bossPoint:v.point)<1.6;}
  assertNear(id,place){if(!this.near(id,place))throw new Error(`先走近${PLACES[place].name}吧。`);}
  startWalk(id,path){const p=this.actor(id);if(p.tableAction)throw new Error('请等桌面动作完成。');if(p.seat)throw new Error('请先起身，再走动。');if(p.pose==='walking')throw new Error('正在走路，请稍等。');if(p.held?.kind==='book')this.books[p.held.id].reading=false;p.path=path.map(v=>[...v]);p.pose='walking';this.record('walk',id,`${p.name}走向选中的位置`);}
  tick(dt){
    for(const [id,p] of Object.entries(this.people)){if(p.tableAction){p.tableAction.remaining=Math.max(0,p.tableAction.remaining-dt);if(p.tableAction.remaining===0)this.finishTableAction(id);}if(p.gestureRemaining>0)p.gestureRemaining=Math.max(0,p.gestureRemaining-dt);if(!p.present||p.pose!=='walking')continue;let travel=Math.min(dt,.1)*2.4;
      while(travel>0&&p.path.length){const target=p.path[0],d=distance(p.position,target);if(d<.001){p.path.shift();continue;}p.rotation=Math.atan2(target[0]-p.position[0],target[1]-p.position[1]);if(travel>=d){p.position=[...target];p.path.shift();travel-=d;}else{p.position=[p.position[0]+(target[0]-p.position[0])*travel/d,p.position[1]+(target[1]-p.position[1])*travel/d];travel=0;}}
      if(!p.path.length){p.pose='standing';this.record('arrive',id,`${p.name}停下脚步`);}}
    if(this.coffee.phase==='brewing'){this.coffee.remaining=Math.max(0,this.coffee.remaining-dt);if(this.coffee.remaining===0){this.coffee.phase='ready';this.cup.full=true;this.record('coffee_ready',this.coffee.maker||'boss','咖啡做好了，杯子里盛着热咖啡');}}
  }
  setOwnerOpen(open){
    const p=this.people.boss;
    if(open){if(!p.present){p.position=[4.3,-1.45];p.rotation=0;p.present=true;}return;}
    if(p.held?.kind==='book'){const book=this.books[p.held.id];book.holder=null;book.location='shelf';book.reading=false;book.reader=null;}
    if(p.held?.kind==='cup'){this.cup.holder=null;this.cup.location='counter';}
    p.held=null;p.seat=null;p.path=[];p.pose='standing';p.gestureRemaining=0;p.present=false;
  }
  enter(){if(this.people.user.present)throw new Error('你已经在书店里了。');const p=this.people.user;p.present=true;p.pose='standing';p.seat=null;p.held=null;p.position=[4.3,4.6];p.rotation=Math.atan2(PLACES.door.point[0]-p.position[0],PLACES.door.point[1]-p.position[1]);p.path=[];this.record('enter','user','朋友推开店门，走进书店');}
  leave(){const p=this.actor('user');if(p.held)throw new Error('离店前先归还书籍、放下杯子。');if(p.seat||p.pose==='walking')throw new Error('先起身，走到店门口吧。');p.present=false;p.position=[4.3,4.6];this.record('leave','user','朋友走出书店，轻轻带上店门');}
  sit(id,seatId){const p=this.actor(id),seat=SEATS[seatId];if(!seat)throw new Error('座位不存在。');if(p.pose==='walking'||p.seat)throw new Error('请先停下或起身。');this.assertNear(id,seat.place);if(Object.values(this.people).some(other=>other.present&&other.seat===seatId))throw new Error('这个位置已经有人坐了，换个座位吧。');p.seat=seatId;p.position=[...seat.position];p.rotation=seat.rotation;p.pose='sitting';this.record('sit',id,`${p.name}坐在${seat.name}`);}
  stand(id){const p=this.actor(id);if(p.pose==='walking')throw new Error('正在走路，请稍等。');if(p.seat){p.position=[...PLACES[SEATS[p.seat].place].point];p.seat=null;}p.pose='standing';this.record('stand',id,`${p.name}起身站好`);}
  tableFor(id){return SEATS[this.people[id]?.seat]?.table||'table';}
  assertAtTable(id,table){const p=this.actor(id);if(p.seat&&this.tableFor(id)===table)return;this.assertNear(id,table);}
  takeBook(id,bookId){const p=this.actor(id),book=this.books[bookId];if(!book)throw new Error('这本书不存在。');this.assertNear(id,book.location.startsWith('table')?book.location:book.shelf);if(p.held)throw new Error('先把手里的物品放好。');if(book.holder)throw new Error('这本书正在被阅读。');p.held={kind:'book',id:bookId};book.holder=id;book.location='held';book.reading=false;book.reader=null;this.record('take_book',id,`${p.name}从书架取下《${book.title}》`);}
  read(id){const p=this.actor(id);if(p.held?.kind!=='book')throw new Error('先从书架拿一本书吧。');this.books[p.held.id].reading=true;this.books[p.held.id].reader=id;this.record('read_book',id,`${p.name}翻开《${this.books[p.held.id].title}》`);return this.books[p.held.id];}
  closeBook(id){this.actor(id);for(const book of Object.values(this.books)){if(book.reader===id){book.reading=false;book.reader=null;this.record('close_book',id,`${this.people[id].name}合上《${book.title}》`);}}}
  putBook(id,table=this.tableFor(id)){const p=this.actor(id);if(p.held?.kind!=='book')throw new Error('手里没有书。');this.assertAtTable(id,table);const b=this.books[p.held.id];b.holder=null;b.location=table;b.reading=false;b.reader=null;p.held=null;this.record('put_book',id,`${p.name}把《${b.title}》放在桌上`);}
  readTableBook(id,bookId){const p=this.actor(id),book=this.books[bookId];if(!book||!book.location.startsWith('table')||book.holder)throw new Error('这本书不在桌上。');this.assertAtTable(id,book.location);book.reading=true;book.reader=id;this.record('read_book',id,`${p.name}阅读桌上的《${book.title}》`);return book;}
  startTableAction(id,type,bookId){
    const p=this.actor(id);if(p.pose==='walking'||p.tableAction)throw new Error('等当前动作完成后再使用桌上物品。');
    const table=this.tableFor(id);this.assertAtTable(id,table);
    let book;
    if(type==='drink_coffee'){
      if(!this.cup.full||!(this.cup.location===table&&!this.cup.holder||this.cup.holder===id))throw new Error('桌上还没有可喝的咖啡，先等咖啡送到吧。');
    }else if(type==='read_book'){
      book=bookId?this.books[bookId]:Object.values(this.books).find(b=>b.location===table||b.holder===id);
      if(!book||!(book.location===table&&!book.holder||book.holder===id))throw new Error('桌上还没有这本书，先请林予拿来吧。');
    }else throw new Error('不支持这个桌面动作。');
    // Previously hand-held objects also return to the table before the new gesture.
    if(p.held){if(p.held.kind==='book'){const old=this.books[p.held.id];old.holder=null;old.location=table;old.reading=false;old.reader=null;this.record('put_book',id,`${p.name}把《${old.title}》放在桌上`);}else{this.cup.holder=null;this.cup.location=table;this.record('put_cup',id,`${p.name}把杯子放在桌上`);}p.held=null;}
    if(type==='drink_coffee'){
      p.held={kind:'cup',id:'cup'};this.cup.holder=id;p.gestureRemaining=1.6;
      this.record('take_cup',id,`${p.name}拿起桌上的咖啡，喝了一口`);
    }else{
      p.held={kind:'book',id:book.id};book.holder=id;book.location='held';book.reading=true;book.reader=id;
      this.record('read_book',id,`${p.name}翻开《${book.title}》看了看`);
    }
    p.tableAction={type,table,bookId:book?.id,remaining:type==='drink_coffee'?1.6:4};
  }
  finishTableAction(id){const p=this.people[id],action=p.tableAction;if(!action)return;
    if(action.type==='drink_coffee'){this.cup.holder=null;this.cup.location=action.table;this.record('drink',id,`${p.name}喝了一口咖啡`);}
    else{const b=this.books[action.bookId];b.holder=null;b.location=action.table;b.reading=false;b.reader=null;this.record('close_book',id,`${p.name}合上《${b.title}》`);}
    p.held=null;p.tableAction=null;p.gestureRemaining=0;
    this.record(action.type==='drink_coffee'?'put_cup':'put_book',id,`${p.name}把${action.type==='drink_coffee'?'咖啡杯':'书'}放回桌上`);
  }
  drinkAtTable(id){const p=this.actor(id);if(this.cup.holder||!this.cup.location.startsWith('table')||!this.cup.full)throw new Error('桌上没有可以饮用的咖啡。');this.assertAtTable(id,this.cup.location);this.cup.full=false;this.coffee.phase='idle';p.gestureRemaining=1.4;this.record('drink',id,`${p.name}喝完桌上的咖啡，把杯子留在桌上`);}
  returnBook(id){const p=this.actor(id);if(p.held?.kind!=='book')throw new Error('手里没有书。');const b=this.books[p.held.id];this.assertNear(id,b.shelf);b.holder=null;b.location='shelf';b.reading=false;b.reader=null;p.held=null;this.record('return_book',id,`${p.name}把《${b.title}》放回书架`);}
  brew(id){this.assertNear(id,'coffee');if(this.coffee.phase==='brewing')throw new Error('咖啡正在制作，请稍等一会儿。');if(this.cup.holder||this.cup.location!=='counter'||this.cup.full)throw new Error('先把空杯放回吧台，再制作咖啡。');this.coffee={phase:'brewing',remaining:4,maker:id};this.record('make_coffee',id,`${this.people[id].name}开始制作咖啡`);}
  takeCup(id){const p=this.actor(id);if(this.cup.holder)throw new Error('杯子已经被拿起了。');if(this.coffee.phase==='brewing')throw new Error('还在萃取咖啡，等做好再拿。');this.assertNear(id,this.cup.location.startsWith('table')?this.cup.location:'cup');if(p.held)throw new Error('先把手里的物品放好。');p.held={kind:'cup',id:'cup'};this.cup.holder=id;this.record('take_cup',id,`${p.name}拿起${this.cup.full?'咖啡':'空'}杯`);}
  deliver(id){const p=this.actor(id),otherId=id==='boss'?'user':'boss',other=this.actor(otherId);if(p.held?.kind!=='cup')throw new Error('先拿起咖啡杯。');if(other.held)throw new Error('对方手里还有物品，暂时接不了杯子。');if(distance(p.position,other.position)>1.8)throw new Error('靠近朋友一些，再递给对方。');p.held=null;other.held={kind:'cup',id:'cup'};this.cup.holder=otherId;this.record('deliver_cup',id,`${p.name}把咖啡杯递给${other.name}`);}
  deliverBook(id){const p=this.actor(id),otherId=id==='boss'?'user':'boss',other=this.actor(otherId);if(p.held?.kind!=='book')throw new Error('手里没有书。');if(other.held)throw new Error('朋友手里还有物品，暂时接不了书。');if(distance(p.position,other.position)>1.8)throw new Error('先靠近朋友再递书。');const book=this.books[p.held.id];other.held={...p.held};p.held=null;book.holder=otherId;book.reading=false;this.record('deliver_book',id,`${p.name}把《${book.title}》递给${other.name}`);}
  drink(id){const p=this.actor(id);if(p.held?.kind!=='cup')throw new Error('先拿起杯子。');if(!this.cup.full)throw new Error('杯子已经空了，先制作咖啡吧。');this.cup.full=false;this.coffee.phase='idle';p.gestureRemaining=1.4;this.record('drink',id,`${p.name}喝完杯中的咖啡`);}
  putCup(id,location='table'){const p=this.actor(id);if(p.held?.kind!=='cup')throw new Error('手里没有杯子。');this.assertNear(id,location.startsWith('table')?location:'cup');this.cup.holder=null;this.cup.location=location;p.held=null;this.record('put_cup',id,`${p.name}把杯子放在${location.startsWith('table')?PLACES[location].name:'吧台'}上`);}
  context(){return {user_activity:this.people.user.tableAction?.type==='drink_coffee'?'drinking':this.people.user.tableAction?.type==='read_book'?'reading':'none',book_catalog:Object.values(this.books).map(({id,title,holder,location})=>({id,title,holder,location})),scene_id:'bookstore',user_present:this.people.user.present,boss_pose:this.people.boss.pose,user_pose:this.people.user.present?this.people.user.pose:'absent',user_item:this.people.user.held?.kind||'none',boss_item:this.people.boss.held?.kind||'none',coffee_phase:this.coffee.phase,cup_full:this.cup.full,reading_title:Object.values(this.books).find(b=>b.reader==='user'&&b.reading)?.title||'',recent_events:this.events.slice(-8)};}
}
