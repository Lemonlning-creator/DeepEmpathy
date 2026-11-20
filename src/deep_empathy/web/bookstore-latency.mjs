// Real browser-clock instrumentation; no simulated typing or extra network requests.
export function startLatency(requestId,started){
  return {request_id:requestId,started,request_sent_ms:null,first_delta_ms:null,
    first_dom_ms:null,first_paint_estimate_ms:null,visible_at_first_text:null,
    processing:null,completed:false};
}
export function publishLatency(t){
  const view={...t};delete view.started;
  const root=document.getElementById('store-chat-messages');
  if(root.dataset.activeTiming!==t.request_id)return;
  root.dataset.latency=JSON.stringify(view);
  if(new URLSearchParams(location.search).get('latency')!=='1')return;
  let output=document.getElementById('latency-measurements');
  if(!output){output=document.createElement('output');output.id='latency-measurements';output.className='latency-measurements';document.querySelector('.store-chat-panel').append(output);}
  const number=n=>n==null?'—':`${Math.round(n)} ms`;
  output.textContent=`云端首正文 ${number(t.processing?.upstream_ttft_ms)} · 后端首正文 ${number(t.processing?.ttft_ms)} · 网页首字 ${number(t.first_dom_ms)} · 绘制估计 ${number(t.first_paint_estimate_ms)}`;
}
export function firstVisibleText(t){
  if(t.first_dom_ms!==null)return;
  t.first_dom_ms=performance.now()-t.started;
  t.visible_at_first_text=document.visibilityState==='visible';
  publishLatency(t);
  if(t.visible_at_first_text)requestAnimationFrame(()=>requestAnimationFrame(()=>{
    t.first_paint_estimate_ms=performance.now()-t.started;publishLatency(t);
  }));
}
