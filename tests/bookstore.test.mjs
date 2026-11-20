import test from 'node:test';
import assert from 'node:assert/strict';
import {BookstoreWorld,BOOKS,PLACES,SEATS,SOFAS,TABLES,EXHIBITION,findPath,walkable} from '../src/deep_empathy/web/bookstore-state.mjs';
const arrive=(w,id,place)=>{const p=PLACES[place];w.people[id].position=[...(id==='boss'&&p.bossPoint?p.bossPoint:p.point)];};
test('user only exists after entry and leaving requires empty hands',()=>{const w=new BookstoreWorld();assert.throws(()=>w.actor('user'));w.enter();assert.equal(w.people.user.present,true);arrive(w,'user','shelf-a');w.takeBook('user','slow');assert.throws(()=>w.leave(),/归还/);w.returnBook('user');w.leave();assert.equal(w.context().user_pose,'absent');assert.ok(w.events.some(e=>e.action==='enter')&&w.events.some(e=>e.action==='leave'));});
test('book has a single holder, real pages, and must return to the original shelf',()=>{const w=new BookstoreWorld();w.enter();assert.throws(()=>w.takeBook('user','slow'),/走近/);arrive(w,'user','shelf-a');w.takeBook('user','slow');arrive(w,'boss','shelf-a');assert.throws(()=>w.takeBook('boss','slow'),/阅读/);const b=w.read('user');assert.ok(b.pages.length>1&&b.reading);arrive(w,'user','shelf-b');assert.throws(()=>w.returnBook('user'),/走近/);arrive(w,'user','shelf-a');w.returnBook('user');assert.equal(w.books.slow.holder,null);assert.equal(w.books.slow.reading,false);});
test('seat occupancy, standing and sitting poses are exclusive',()=>{const w=new BookstoreWorld();w.enter();arrive(w,'user','sofa');w.sit('user','sofa-left');assert.equal(w.people.user.pose,'sitting');arrive(w,'boss','sofa');assert.throws(()=>w.sit('boss','sofa-left'),/有人/);arrive(w,'boss',SEATS.chair.place);w.sit('boss','chair');assert.equal(w.people.boss.pose,'sitting');assert.throws(()=>w.startWalk('user',[[0,0]]),/起身/);w.stand('user');assert.equal(w.people.user.seat,null);assert.deepEqual(w.people.user.position,PLACES.sofa.point);w.stand('boss');arrive(w,'user','chair');w.sit('user','chair');assert.equal(w.people.user.seat,'chair');});
test('coffee lifecycle: brew, wait, ready, pick, deliver, drink and put down',()=>{const w=new BookstoreWorld();w.enter();arrive(w,'boss','coffee');w.brew('boss');assert.equal(w.coffee.phase,'brewing');assert.throws(()=>w.takeCup('boss'),/等/);w.tick(2);assert.equal(w.cup.full,false);w.tick(2);assert.equal(w.coffee.phase,'ready');w.takeCup('boss');assert.equal(w.cup.holder,'boss');assert.throws(()=>w.brew('boss'),/空杯/);w.people.user.position=[4,1];assert.throws(()=>w.deliver('boss'),/靠近/);w.people.boss.position=[3.7,1.1];w.deliver('boss');assert.equal(w.cup.holder,'user');w.drink('user');assert.equal(w.cup.full,false);assert.throws(()=>w.drink('user'),/空/);arrive(w,'user','table');w.putCup('user');assert.equal(w.cup.location,'table');assert.equal(w.cup.holder,null);assert.throws(()=>w.brew('boss'),/走近|空杯/);});
test('navigation avoids sofa and counter and reaches every object',()=>{for(const id of Object.keys(PLACES)){const end=PLACES[id].point;const path=findPath(PLACES.door.point,end);assert.ok(path.length>0,id);assert.deepEqual(path.at(-1),end);assert.ok(path.every(p=>walkable(p)),id);}assert.throws(()=>findPath(PLACES.door.point,[EXHIBITION.x,EXHIBITION.z]),/走不过/);});
test('walking is animated over time, not instantaneous teleportation',()=>{const w=new BookstoreWorld();w.enter();w.people.user.position=[...PLACES.door.point];const path=findPath(w.people.user.position,PLACES['shelf-a'].point);w.startWalk('user',path);w.tick(.016);assert.equal(w.people.user.pose,'walking');for(let i=0;i<500;i++)w.tick(.016);assert.equal(w.people.user.pose,'standing');assert.deepEqual(w.people.user.position,PLACES['shelf-a'].point);});
test('scene context is bounded and does not invent psychological facts',()=>{const w=new BookstoreWorld();w.enter();for(let i=0;i<40;i++)w.stand('user');const context=w.context();assert.equal(context.recent_events.length,8);assert.equal(context.scene_id,'bookstore');assert.equal(context.user_item,'none');assert.ok(!('psychology' in context));assert.equal(BOOKS.length,4);assert.ok(SEATS.chair);});
test('coffee completion retains who started the machine',()=>{const w=new BookstoreWorld();w.enter();arrive(w,'user','coffee');w.brew('user');w.tick(4);assert.equal(w.events.at(-1).actor,'user');assert.equal(w.events.at(-1).action,'coffee_ready');});

test('face-to-face waits for extraction and online replies can run in parallel',async()=>{
  const {interruption}=await import('../src/deep_empathy/web/bookstore-life.mjs');
  assert.equal(interruption({brewing:true,inPerson:true}),'wait');
  assert.equal(interruption({walking:true,inPerson:true}),'wait');
  assert.equal(interruption({busy:true,inPerson:true}),'wait');
  assert.equal(interruption({brewing:true,inPerson:false}),'parallel');
  assert.equal(interruption({inPerson:true}),'pause');
});

test('smoothed routes clear all furniture between every approach point',()=>{
  for(const a of Object.values(PLACES))for(const b of Object.values(PLACES)){
    const path=findPath(a.point,b.point);let from=a.point;
    for(const to of path){const n=Math.max(1,Math.ceil(Math.hypot(to[0]-from[0],to[1]-from[1])/.04));for(let i=1;i<=n;i++)assert.ok(walkable([from[0]+(to[0]-from[0])*i/n,from[1]+(to[1]-from[1])*i/n]));from=to;}
  }
});
test('rotation takes the shortest arc at bounded angular speed',async()=>{
  const {turnToward}=await import('../src/deep_empathy/web/bookstore-state.mjs');
  let angle=Math.PI-.01;const target=-Math.PI+.01;
  const next=turnToward(angle,target,1/60);assert.ok(next>angle&&next-angle<.05);
  angle=0;for(let i=0;i<100;i++){const next=turnToward(angle,Math.PI/2,1/60);assert.ok(next>=angle&&next-angle<=3/60+.000001);angle=next;}
  assert.ok(Math.abs(angle-Math.PI/2)<.001);
});
test('window seats face their tables in opposed pairs and door aligns with counter',()=>{
  const w=new BookstoreWorld();w.enter();
  for(const seat of ['chair','sofa-left']){arrive(w,'user',SEATS[seat].place);w.sit('user',seat);assert.equal(SEATS[seat].height,.76);assert.equal(SEATS[seat].rotation,seat==='chair'?0:Math.PI);w.stand('user');assert.ok(walkable(w.people.user.position));}
  arrive(w,'user','cup');w.takeCup('user');
  for(const table of ['table']){arrive(w,'user',table);w.putCup('user',table);assert.equal(w.cup.location,table);w.takeCup('user');}
});

test('all three seats have reachable approaches and table actions return to the correct local table',()=>{
 assert.equal(SOFAS.length,3);assert.equal(Object.keys(TABLES).length,2);assert.equal(PLACES.door.point[0],PLACES.counter.point[0]);
 for(const sofa of SOFAS){
  const w=new BookstoreWorld();w.enter();const seat=SEATS[sofa.id],table=TABLES[seat.table];
  assert.ok(findPath(PLACES.door.point,PLACES[seat.place].point).length);
  assert.ok((table.x-seat.position[0])*Math.sin(seat.rotation)+(table.z-seat.position[1])*Math.cos(seat.rotation)>0);
  arrive(w,'user',seat.place);w.sit('user',sofa.id);
  w.cup.full=true;w.cup.location=seat.table;w.startTableAction('user','drink_coffee');w.tick(2);
  assert.equal(w.cup.location,seat.table);assert.equal(w.people.user.held,null);
  w.books.slow.location=seat.table;w.startTableAction('user','read_book','slow');w.tick(5);
  assert.equal(w.books.slow.location,seat.table);w.stand('user');assert.ok(walkable(w.people.user.position));
 }
});

 test('each entry faces inward even after leaving with an outward heading',()=>{
  const w=new BookstoreWorld();
  for(let visit=0;visit<2;visit++){
    w.enter();const p=w.people.user;
    const expected=Math.atan2(PLACES.door.point[0]-p.position[0],PLACES.door.point[1]-p.position[1]);
    assert.equal(p.rotation,expected);
    const start=[...p.position];w.startWalk('user',[PLACES.door.point]);w.tick(1/60);
    assert.ok((p.position[0]-start[0])*Math.sin(p.rotation)+(p.position[1]-start[1])*Math.cos(p.rotation)>0);
    while(p.pose==='walking')w.tick(.1);p.rotation=0;w.leave();
  }
});

test('window seats oppose each other across shared table and central exhibit stays clear',()=>{
 const seat=SEATS.chair,table=TABLES[seat.table];
 assert.ok(Math.abs(Math.sin(seat.rotation))<1e-8);
 assert.ok(Math.cos(seat.rotation)>.99);
 assert.ok(Math.abs(table.x-seat.position[0])<.1);
 assert.ok(table.z>seat.position[1]);
 assert.equal(SEATS['sofa-left'].table,seat.table);
 assert.equal(SEATS['sofa-left'].rotation,Math.PI);
 assert.ok(!walkable([EXHIBITION.x,EXHIBITION.z]));
 assert.ok(findPath(PLACES.door.point,PLACES.exhibition.point).length);
 assert.ok(findPath(PLACES.door.point,PLACES.chair.point).length);
});

test('spacious layout reserves green corner and removes bar seating',()=>{
 assert.ok(!SEATS['sofa-right']);assert.ok(!TABLES['table-front-right']);
 assert.ok(walkable([-7.4,-2.5]));
 assert.ok(!walkable([-7.15,2.65]));
 assert.ok(Math.hypot(SEATS.chair.position[0]-SEATS['sofa-front-left'].position[0],SEATS.chair.position[1]-SEATS['sofa-front-left'].position[1])>3);
});

test('owner leaves at close, releases seat and book, then returns at opening',()=>{
 const w=new BookstoreWorld();arrive(w,'boss','shelf-a');w.takeBook('boss','slow');arrive(w,'boss','chair');w.sit('boss','chair');
 w.setOwnerOpen(false);assert.equal(w.people.boss.present,false);assert.equal(w.people.boss.seat,null);assert.equal(w.books.slow.location,'shelf');assert.equal(w.books.slow.holder,null);
 w.setOwnerOpen(false);w.setOwnerOpen(true);assert.equal(w.people.boss.present,true);assert.deepEqual(w.people.boss.position,[4.3,-1.45]);
});
