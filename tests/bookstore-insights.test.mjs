import test from 'node:test';
import assert from 'node:assert/strict';
import {InsightPanel,psychologyParts,READING_CAPS,EMOTIONAL_CAPS} from '../src/deep_empathy/web/bookstore-insights.mjs';
const claim={id:'one',layer:'regulation',statement:'倾向先倾听',status:'tentative',version:1,confidence:.35,evidence:[{quote:'听我说'}]};
const p={needs:['relatedness'],goals:[],actual_self:'',ideal_self:'',ought_self:'',interpretation:'希望被倾听',citations:[{message_id:'source',quote:'听我说'}]};
test('initial load only shows clarity, without replaying previous round activation',()=>{
 const m=new InsightPanel();m.observe({mode:'cloud',claims:[claim],current_turn:{id:'old',psychology:p,capabilities:[{id:'user_memory'}],profile_updates:[claim]}});
 const v=m.view();assert.ok(v.metrics[1].clarity>0);assert.equal(v.updates.length,0);assert.equal(v.capabilities.length,0);assert.equal(v.psychology.needs.active,false);
 assert.equal(READING_CAPS.length,4);assert.equal(EMOTIONAL_CAPS.length,4);
});
test('only the current saved turn may activate changes, and repeated polling preserves them',()=>{
 const m=new InsightPanel();m.observe({mode:'cloud',claims:[claim],current_turn:{id:'old',psychology:null}});m.beginRound();m.completeRound('new');
 const old={mode:'cloud',claims:[claim],current_turn:{id:'old',psychology:p,latent_psychology:{part:'needs',state:'希望被倾听',quote:'听我说'},profile_updates:[claim],capabilities:[{id:'user_memory'}]}};m.observe(old);assert.equal(m.view().capabilities.length,0);
 const data={...old,current_turn:{...old.current_turn,id:'new'}};m.observe(data);assert.equal(m.view().updates.length,1);assert.equal(m.view().psychology.needs.active,true);m.observe(data);assert.equal(m.view().psychology.needs.active,true);
 m.beginRound();assert.equal(m.view().capabilities.length,0);m.completeRound('next');m.observe({...data,current_turn:{...data.current_turn,id:'next',latent_psychology:null,profile_updates:[],capabilities:[]}});assert.equal(m.view().psychology.needs.active,false);
});
test('unsupported psychology, inactive claims and demo metadata never fabricate activity',()=>{
 assert.equal(psychologyParts({...p,citations:[]}).needs,'');assert.equal(psychologyParts({...p,needs:[],actual_self:'尚不明确'}).self_view,'');
 const m=new InsightPanel();m.completeRound('new');m.observe({mode:'cloud',claims:[{...claim,status:'retracted'}],current_turn:{id:'new',profile_updates:[claim]}});assert.equal(m.view().updates.length,0);
 m.observe({mode:'demo',claims:[],current_turn:{id:'new',psychology:p,capabilities:[{id:'user_memory'}]}});assert.equal(m.view().capabilities.length,0);
});
test('foreground psychology activates one immediately without background analysis; null never falls back',()=>{
 const m=new InsightPanel();m.beginRound();m.completeRound('one');
 const data={mode:'cloud',claims:[],current_turn:{id:'one',psychology:null,latent_psychology:{part:'self_view',state:'怀疑自己的能力（暂时推测）',quote:'我是不是不行'}}};
 m.observe(data);assert.equal(m.view().psychology.self_view.active,true);
 assert.equal(Object.values(m.view().psychology).filter(x=>x.active).length,1);
 m.beginRound();m.completeRound('one');assert.equal(m.view().psychology.self_view.active,true);
 m.observe({...data,current_turn:{...data.current_turn,latent_psychology:null,psychology:p}});
 assert.equal(Object.values(m.view().psychology).filter(x=>x.active).length,0);
});
test('profile progress follows current turn job rather than an earlier session job',()=>{
 const m=new InsightPanel();
 m.observe({mode:'cloud',claims:[],modeling_status:'completed',current_turn:{id:'one',modeling_status:'pending'}});
 assert.equal(m.view().modelingStatus,'pending');
 m.data.current_turn.modeling_status='running';assert.equal(m.view().modelingStatus,'running');
 m.data.current_turn.modeling_status='completed';assert.equal(m.view().modelingStatus,'completed');
 m.data.current_turn.modeling_status='not_requested';m.data.modeling_status='running';assert.equal(m.view().modelingStatus,'not_requested');
});
