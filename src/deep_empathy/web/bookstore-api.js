export async function api(path,method='GET',body){
  const response=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-Deep-Empathy':'1'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result=await response.json();if(!response.ok)throw new Error(result.error?.message||'暂时无法连接，请稍后再试。');return result;
}
export async function streamChat(session,request,onEvent){
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),195000);let reader;
  try{onEvent('request_sent',{});const response=await fetch(`/v1/sessions/${session}/messages/stream`,{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','X-Deep-Empathy':'1','Accept':'text/event-stream'},body:JSON.stringify(request)});
    if(!response.ok){const error=await response.json();throw new Error(error.error?.message||'发送失败。');}if(!response.body)throw new Error('无法建立流式连接。');
    reader=response.body.getReader();const decoder=new TextDecoder();let buffer='',result=null;
    const consume=block=>{let type='message';const data=[];for(const line of block.split('\n')){if(line.startsWith('event:'))type=line.slice(6).trim();if(line.startsWith('data:'))data.push(line.slice(5).trimStart());}if(!data.length||type==='ping')return;const value=JSON.parse(data.join('\n'));if(type==='error')throw new Error(value.message||'回复中断。');onEvent(type,value);if(type==='done')result=value;};
    while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});buffer=buffer.replace(/\r\n/g,'\n');let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){consume(buffer.slice(0,boundary));buffer=buffer.slice(boundary+2);}if(buffer.length>30000)throw new Error('流式数据异常。');if(done)break;}
    if(!result)throw new Error('连接中断，回复未确认保存。请重试。');return result;
  }catch(error){if(error.name==='AbortError')throw new Error('等待超时，回复未确认保存。');throw error;}
  finally{clearTimeout(timeout);if(reader){await reader.cancel().catch(()=>{});reader.releaseLock();}}
}
