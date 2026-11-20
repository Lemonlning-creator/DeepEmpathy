import test from 'node:test';
import assert from 'node:assert/strict';
import {spokenActions,SceneActionQueue} from '../src/deep_empathy/web/bookstore-actions.mjs';
import {BookstoreWorld,PLACES,SEATS} from '../src/deep_empathy/web/bookstore-state.mjs';
const context={mode:'in_person',present:true,catalog:[{id:'slow',title:'把日子过慢一点',holder:null}]};
test('saved spoken commitments map to supported physical actions',()=>{
  assert.deepEqual(spokenActions('我来给你做杯咖啡。',context),[{type:'serve_coffee'}]);
  assert.deepEqual(spokenActions('好，我来给你拿《把日子过慢一点》。',context),[{type:'bring_book',bookId:'slow'}]);
  assert.equal(spokenActions('我来给你拿《不存在的书》。',context).length,0);
  assert.equal(spokenActions('我来给你做杯咖啡。我来给你做杯咖啡。',context).length,1);
  assert.deepEqual(spokenActions('好，稍等。',{...context,userContent:'意式就好，谢谢。'}),[{type:'serve_coffee'}]);
  assert.equal(spokenActions('好，想喝咖啡吗？',{...context,userContent:'咖啡'}).length,0);
});
test('online, absent visitors, suggestions, questions, quotes and refusals never act',()=>{
  for(const text of ['我来给你做杯咖啡？','如果你想，我来给你做杯咖啡。','你可以拿本书。','我现在不能给你做咖啡。','你说“我来给你做杯咖啡”。','我已经给你做过咖啡。','我待会给你做杯咖啡。'])assert.equal(spokenActions(text,context).length,0,text);
  assert.equal(spokenActions('我来给你做杯咖啡。',{...context,mode:'online'}).length,0);
  assert.equal(spokenActions('我来给你做杯咖啡。',{...context,present:false}).length,0);
});
test('queue waits for safety, serializes actions and deduplicates retry turns',async()=>{
  const log=[];let release;
  const q=new SceneActionQueue({waitSafe:()=>new Promise(r=>{release=r;}),canRun:()=>true,execute:async a=>log.push(a.type),onError:e=>{throw e;}});
  q.enqueue('saved-turn',[{type:'serve_coffee'}]);q.enqueue('saved-turn',[{type:'serve_coffee'}]);
  assert.equal(log.length,0);assert.equal(q.pending.length,1);release();
  await new Promise(r=>setTimeout(r,0));assert.deepEqual(log,['serve_coffee']);assert.equal(q.pending.length,0);
});
test('book transfer preserves exclusive ownership and can be returned',()=>{
  const w=new BookstoreWorld();w.enter();w.people.boss.position=[...PLACES['shelf-a'].point];w.takeBook('boss','slow');
  w.people.user.position=[-1.6,1];assert.throws(()=>w.deliverBook('boss'),/靠近/);
  w.people.boss.position=[-.6,1];w.deliverBook('boss');
  assert.equal(w.books.slow.holder,'user');assert.equal(w.people.boss.held,null);assert.equal(w.people.user.held.id,'slow');
  w.people.user.position=[...PLACES['shelf-a'].point];w.returnBook('user');assert.equal(w.books.slow.holder,null);
});

test('book and coffee deliveries use the table while the visitor keeps holding a book',()=>{
  const w=new BookstoreWorld();w.enter();
  w.people.user.position=[...PLACES['shelf-a'].point];w.takeBook('user','slow');
  w.people.boss.position=[...PLACES['shelf-b'].point];w.takeBook('boss','night');
  w.people.boss.position=[...PLACES.table.point];w.putBook('boss');
  assert.equal(w.books.night.location,'table');assert.equal(w.books.night.holder,null);
  assert.equal(w.people.user.held.id,'slow');assert.equal(w.people.boss.held,null);
  w.people.boss.position=[...PLACES.coffee.bossPoint];w.brew('boss');w.tick(4.1);w.takeCup('boss');
  w.people.boss.position=[...PLACES.table.point];w.putCup('boss','table');
  assert.equal(w.cup.location,'table');assert.equal(w.cup.holder,null);assert.equal(w.people.user.held.id,'slow');
  w.people.user.position=[...PLACES.table.point];w.readTableBook('user','night');assert.equal(w.books.night.reader,'user');
  w.closeBook('user');assert.equal(w.books.night.reading,false);
  w.drinkAtTable('user');assert.equal(w.cup.full,false);assert.equal(w.people.user.held.id,'slow');
});
test('table book can be picked up and returned, without leaving a duplicate on the table',()=>{
  const w=new BookstoreWorld();w.enter();w.people.boss.position=[...PLACES['shelf-a'].point];w.takeBook('boss','slow');
  w.people.boss.position=[...PLACES.table.point];w.putBook('boss');w.people.user.position=[...PLACES.table.point];
  w.readTableBook('user','slow');assert.equal(w.context().reading_title,'把日子过慢一点');w.closeBook('user');
  w.takeBook('user','slow');assert.equal(w.books.slow.location,'held');w.people.user.position=[...PLACES['shelf-a'].point];w.returnBook('user');assert.equal(w.books.slow.location,'shelf');
});

test('user chat gestures recognize self-directed drink/read and reject quoted or negated acts',async()=>{
  const {userSpokenActions}=await import('../src/deep_empathy/web/bookstore-actions.mjs');
  const c={...context,catalog:[{id:'slow',title:'把日子过慢一点',location:'table',holder:null}]};
  assert.deepEqual(userSpokenActions('喝口咖啡',c),[{type:'drink_coffee'}]);
  assert.deepEqual(userSpokenActions('我想喝一口咖啡。',c),[{type:'drink_coffee'}]);
  assert.deepEqual(userSpokenActions('翻开书看看',c),[{type:'read_book',bookId:'slow'}]);
  assert.equal(userSpokenActions('喝口咖啡，然后翻开书看看',c).length,2);
  for(const text of ['不喝咖啡','我不想翻开书','你喝口咖啡吧','林予翻开书看看','如果我喝口咖啡','我说“喝口咖啡”','刚才我喝口咖啡','翻开《不存在》看看'])assert.equal(userSpokenActions(text,c).length,0,text);
  assert.equal(userSpokenActions('喝口咖啡',{...c,mode:'online'}).length,0);
  assert.equal(spokenActions('好，稍等。',{...c,userContent:'喝口咖啡'}).length,0);
});
test('user sip and brief reading temporarily hold items, then restore the table and free hands',()=>{
  const w=new BookstoreWorld();w.enter();w.people.boss.position=[...PLACES['shelf-a'].point];w.takeBook('boss','slow');w.people.boss.position=[...PLACES.table.point];w.putBook('boss');
  w.people.boss.position=[...PLACES.coffee.bossPoint];w.brew('boss');w.tick(4.1);w.takeCup('boss');w.people.boss.position=[...PLACES.table.point];w.putCup('boss','table');
  w.people.user.position=[...PLACES[SEATS['sofa-left'].place].point];w.sit('user','sofa-left');
  w.startTableAction('user','drink_coffee');assert.equal(w.cup.holder,'user');assert.equal(w.context().user_activity,'drinking');
  assert.throws(()=>w.startWalk('user',[[0,0]]),/完成/);w.tick(1.7);
  assert.equal(w.people.user.held,null);assert.equal(w.cup.holder,null);assert.equal(w.cup.location,'table');assert.equal(w.cup.full,true);assert.equal(w.people.user.pose,'sitting');
  w.startTableAction('user','read_book','slow');assert.equal(w.books.slow.holder,'user');assert.equal(w.context().reading_title,'把日子过慢一点');w.tick(4.1);
  assert.equal(w.books.slow.location,'table');assert.equal(w.books.slow.holder,null);assert.equal(w.books.slow.reading,false);assert.equal(w.people.user.held,null);assert.equal(w.context().user_activity,'none');
});
test('missing table objects fail without creating coffee or taking a book from a shelf',()=>{
  const w=new BookstoreWorld();w.enter();w.people.user.position=[...PLACES.table.point];
  assert.throws(()=>w.startTableAction('user','drink_coffee'),/咖啡/);assert.throws(()=>w.startTableAction('user','read_book','slow'),/这本书/);
  assert.equal(w.people.user.held,null);assert.equal(w.books.slow.location,'shelf');
});
