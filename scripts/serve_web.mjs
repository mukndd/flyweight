import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../dist/web/',import.meta.url));
const production=process.env.FLYWEIGHT_ENV==='production';
if(production&&process.env.FLYWEIGHT_SERVICE_ROLE!=='WEB')throw Error('prod:web requires FLYWEIGHT_SERVICE_ROLE=WEB');
const host=process.env.FLYWEIGHT_BIND_HOST??'127.0.0.1';
if(!['127.0.0.1',...(production?['0.0.0.0']:[])].includes(host))throw Error('Invalid bind address');
const rawPort=process.env.PORT??'5180';if(!/^\d{4,5}$/.test(rawPort)||Number(rawPort)>65535||Number(rawPort)<1024)throw Error('Invalid port');
const upstream=process.env.BRAIN_UPSTREAM?new URL(process.env.BRAIN_UPSTREAM):null;
if(upstream&&(upstream.username||upstream.password||upstream.pathname!=='/'||upstream.search||upstream.hash||!['https:','http:'].includes(upstream.protocol)||upstream.protocol==='http:'&&(production||upstream.hostname!=='127.0.0.1')))throw Error('Invalid fixed brain upstream');
const origins=(process.env.FLYWEIGHT_PUBLIC_ORIGINS??(production?'':`http://127.0.0.1:${rawPort}`)).split(',').map(s=>s.trim()).filter(Boolean);
if(!origins.length||origins.length>4||origins.some(x=>{const u=new URL(x);return u.origin!==x||production&&u.protocol!=='https:';}))throw Error('Exact public origins required');
const csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";
const headers={'Content-Security-Policy':csp,'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Permissions-Policy':'camera=(), microphone=(), geolocation=()','Cache-Control':'no-store'};
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png'};
let websocketCount=0;
const server=http.createServer({maxHeaderSize:8192,requestTimeout:10000,headersTimeout:10000},(req,res)=>{
 if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405,headers);res.end();return;}
 if(req.url==='/health'){res.writeHead(200,{...headers,'Content-Type':'application/json'});res.end('{"status":"ready","service":"flyweight-web"}');return;}
 try{
  const url=new URL(req.url,'http://internal.invalid');let decoded=decodeURIComponent(url.pathname);
  if(decoded.includes('..')||decoded.includes('\\')||decoded.includes('\0'))throw Error();
  if(decoded==='/')decoded='/index.html';
  let target=path.resolve(root,'.'+decoded);
  if(!target.startsWith(path.resolve(root)+path.sep))throw Error();
  if(!fs.existsSync(target)){if(path.extname(decoded))throw Error();target=path.join(root,'index.html');}
  const stat=fs.lstatSync(target);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>5000000)throw Error();
  res.writeHead(200,{...headers,'Content-Type':mime[path.extname(target)]??'application/octet-stream','Content-Length':stat.size});if(req.method==='HEAD')res.end();else fs.createReadStream(target).pipe(res);
 }catch{res.writeHead(404,headers);res.end('Not found');}
});
server.on('upgrade',(req,socket,head)=>{
 if(!upstream||req.url!=='/brain/ws'||!origins.includes(req.headers.origin??'')||websocketCount>=4){socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');return;}
 websocketCount++;let closed=false;const done=()=>{if(!closed){closed=true;websocketCount--;}};socket.on('close',done);socket.on('error',()=>socket.destroy());socket.setTimeout(30000,()=>socket.destroy());
 const clean={};for(const key of ['upgrade','connection','sec-websocket-key','sec-websocket-version','sec-websocket-protocol','sec-websocket-extensions','origin'])if(req.headers[key])clean[key]=req.headers[key];
 const transport=upstream.protocol==='https:'?https:http;
 const proxy=transport.request(new URL('/ws',upstream),{method:'GET',headers:clean,timeout:5000});
 proxy.on('upgrade',(response,remote,remoteHead)=>{let responseHeaders='HTTP/1.1 101 Switching Protocols\r\n';for(const key of ['upgrade','connection','sec-websocket-accept','sec-websocket-protocol','sec-websocket-extensions'])if(response.headers[key])responseHeaders+=key+': '+response.headers[key]+'\r\n';socket.write(responseHeaders+'\r\n');if(head.length)remote.write(head);if(remoteHead.length)socket.write(remoteHead);socket.pipe(remote);remote.pipe(socket);remote.on('error',()=>socket.destroy());socket.on('close',()=>remote.destroy());remote.on('close',()=>socket.destroy());});
 proxy.on('response',()=>{socket.end('HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n');proxy.destroy();});proxy.on('error',()=>socket.destroy());proxy.on('timeout',()=>proxy.destroy());proxy.end();
});
server.listen(Number(rawPort),host,()=>console.log(`Flyweight web listening on ${host}:${rawPort}; fixed proxy ${upstream?'configured':'offline'}`));
const stop=()=>{server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),5000).unref();};
process.on('SIGTERM',stop);process.on('SIGINT',stop);
