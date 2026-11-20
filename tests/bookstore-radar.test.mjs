import test from 'node:test';
import assert from 'node:assert/strict';
import {profileMetrics,RadarSnapshot} from '../src/deep_empathy/web/bookstore-radar.mjs';
const claim={layer:'core',confidence:.9,status:'tentative',evidence:[{quote:'原话'}]};
test('empty or ungrounded profiles do not fabricate scores',()=>{
  assert.ok(profileMetrics().every(v=>v.clarity===0&&v.stability===0));
  assert.equal(profileMetrics([{...claim,evidence:[]}])[0].clarity,0);
});
test('inner stability remains inside clarity and confirmation affects it',()=>{
  const a=profileMetrics([claim])[0],b=profileMetrics([{...claim,status:'user_confirmed'}])[0];
  assert.equal(a.stability,0);assert.ok(b.stability>0&&b.stability<=b.clarity);
});
test('polling preserves changes, first load has no change and new round resets baseline',()=>{
  const m=new RadarSnapshot();m.update([claim]);assert.equal(m.deltas[0],0);
  m.beginRound();m.update([claim,claim]);const d=m.deltas[0];assert.ok(d>0);
  m.update([claim,claim]);assert.equal(m.deltas[0],d);
  m.beginRound();m.update([claim]);assert.ok(m.deltas[0]<0);
});
