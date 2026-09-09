export function brainSocketUrl(base:string|undefined,origin:string,development:boolean):string{
 const chosen=base?.trim()||(development?'http://127.0.0.1:8000':origin+'/brain');
 const url=new URL(chosen,origin);
 if(url.username||url.password||url.search||url.hash||!['http:','https:'].includes(url.protocol))throw Error('Invalid Fly Brain URL');
 if(url.protocol==='http:'&&!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw Error('Fly Brain URL must use HTTPS');
 url.protocol=url.protocol==='https:'?'wss:':'ws:';url.pathname=url.pathname.replace(/\/$/,'')+'/ws';return url.toString();
}
