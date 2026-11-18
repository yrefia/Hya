// Exercise the real browser script with controlled network responses.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/ui.html'),'utf8').split('<script>')[1].split('</script>')[0];
function harness(responses){
 const requests=[],downloads=[],elements={},listeners={};
 const ctx=new Proxy({},{get:()=>()=>{},set:()=>true});
 const element=id=>elements[id]||(elements[id]={value:id==='mode'?'ml':'',checked:true,currentTime:0,getBoundingClientRect:()=>({width:800,height:600}),getContext:()=>ctx,pause(){},load(){},getAttribute(key){return this[key]},removeAttribute(key){delete this[key]},toBlob(callback){callback(new Blob(['png']))}});
 const document={getElementById:element,createElement:()=>({click(){downloads.push(this.download)}})};
 const box={window:{addEventListener(name,fn){listeners[name]=fn}},document,location:{search:'?token=test'},URLSearchParams,Blob,devicePixelRatio:1,matchMedia:()=>({matches:false}),requestAnimationFrame:()=>{},setTimeout:fn=>{queueMicrotask(fn);return 1},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},fetch:async(path,options={})=>{requests.push({path,options});const next=responses.shift();assert(next,`Unexpected fetch ${path}`);if(typeof next==='function')return next(path,options);return {ok:next.ok!==false,status:next.status||200,json:async()=>next.body??next}}};
 vm.createContext(box);vm.runInContext(source,box);return {box,elements,requests,downloads,listeners,run:code=>vm.runInContext(code,box)};
}
const result={version:'hya-ml-2',duration:3,frames:[{t:0,rms:.1,energy:.5,centroid:400}],tracks:{vocals:{notes:[]},bass:{notes:[]},drums:{onsets:[]}},warnings:['分轨可能存在泄漏']};
(async()=>{
 let h=harness([{id:'a',state:'queued',progress:0},{id:'a',state:'running',message:'分轨中',progress:.3},{id:'a',state:'done',cached:true,progress:1},result]);
 await h.run("load(new Blob(['audio']), 'test.wav')");
 assert.deepEqual(h.requests.map(r=>r.path),['/jobs','/jobs/a','/jobs/a','/jobs/a/result']);assert(h.requests.every(r=>r.options.headers['X-Hya-Token']==='test'));assert.equal(h.elements.file.disabled,false);assert.equal(h.elements.save.disabled,false);assert.match(h.elements.status.textContent,/已复用缓存/);assert.match(h.elements.warnings.textContent,/泄漏/);
 h.run("$('save').onclick(); $('png').onclick()");assert.deepEqual(h.downloads,['hya-analysis.json','hya-tracks.png']);
 h=harness([{id:'b',state:'queued'},{id:'b',state:'error',error:'缺少模型'}]);await h.run("load(new Blob(['audio']), 'bad.wav')");assert.match(h.elements.status.textContent,/缺少模型/);assert.equal(h.elements.file.disabled,false);assert.equal(h.elements.save.disabled,true);assert.equal(h.run('result'),null);
 h=harness([{id:'c',state:'queued'}, {id:'c',state:'cancelled'}]);const pending=h.run("load(new Blob(['audio']), 'cancel.wav')");h.run("$('cancel').onclick()");await pending;assert.equal(h.requests[1].options.method,'DELETE');assert.equal(h.requests[1].path,'/jobs/c');assert.match(h.elements.status.textContent,/已取消/);assert.equal(h.elements.file.disabled,false);assert.equal(h.run('result'),null);
 h=harness([{ok:false,body:{error:'忙碌'}}]);await h.run("load(new Blob(['audio']), 'busy.wav')");assert.match(h.elements.status.textContent,/忙碌/);assert.equal(h.elements.mode.disabled,false);
 h=harness([{...result,tracks:undefined}]);h.run("$('mode').value='quick'");await h.run("load(new Blob(['audio']), 'quick.wav')");assert.equal(h.requests[0].path,'/analyze');assert.equal(h.elements.cancel.hidden,true);
 h=harness([{name:'远方的寂静',playback:true},result]);
 await h.listeners.DOMContentLoaded();
 assert.deepEqual(h.requests.map(r=>r.path),['/default','/default/result']);
 assert(h.requests.every(r=>!r.options.body&&!r.options.method));
 assert.equal(h.elements.audio.src,'/sample?playback=1&token=test');
 assert.match(h.elements.status.textContent,/远方的寂静.*已复用缓存/);
 // Playback must be assigned before analysis arrives, and survive cache/network errors.
 let finish;
 h=harness([{name:'远方的寂静'},()=>new Promise(resolve=>{finish=resolve})]);
 const loading=h.listeners.DOMContentLoaded();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.elements.audio.src,'/sample?playback=1&token=test');
 assert.equal(h.run('result'),null);
 finish({ok:false,status:409,json:async()=>({error:'缓存缺失，请在电脑上预缓存'})});await loading;
 assert.equal(h.elements.audio.src,'/sample?playback=1&token=test');
 assert.match(h.elements.status.textContent,/仍可尝试播放.*缓存缺失/);
 assert.equal(h.elements.sample.disabled,false);assert.equal(h.elements.save.disabled,true);
 h=harness([{name:'song'},()=>({ok:false,status:502,json:async()=>{throw new SyntaxError('The string did not match the expected pattern.')}})]);
 await h.listeners.DOMContentLoaded();assert.match(h.elements.status.textContent,/访问通道.*HTTP 502/);
 h=harness([()=>({ok:false,status:413,json:async()=>{throw new SyntaxError('bad json')}})]);
 await h.run("load(new Blob(['audio']), 'large.flac')");assert.match(h.elements.status.textContent,/拒绝了过大的音频上传/);
 h=harness([{ok:false,status:404,body:{error:'默认曲目不存在'}}]);await h.listeners.DOMContentLoaded();assert.match(h.elements.status.textContent,/默认曲目不存在/);assert.equal(h.elements.file.disabled,false);
 // Standard fixtures use real cached transcription, never upload or synthetic truth as predictions.
 const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/demos/pure.json'),'utf8'));
 h=harness([fixture]);h.run("$('standardDemo').value='pure'");
 await h.run('loadStandard()');
 assert.deepEqual(h.requests.map(r=>r.path),['/demos/pure.json']);
 assert.equal(h.elements.audio.src,'/demos/pure.wav?token=test');
 assert.equal(h.elements.referencePanel.hidden,false);
 assert.equal(h.elements.referenceNotes.textContent.split('✓').length-1,8);
 assert.equal(h.elements.loadStandard.disabled,false);
 h.run('resetTrack()');assert.equal(h.elements.referencePanel.hidden,true);
 h=harness([{ok:false,status:404,body:{error:'missing'}}]);h.run("$('standardDemo').value='louder-bass'");
 await h.run('loadStandard()');assert.match(h.elements.status.textContent,/标准示范数据加载失败/);
 assert.equal(h.elements.audio.src,'/demos/louder-bass.wav?token=test');
 assert.equal(h.elements.loadStandard.disabled,false);
 console.log('PASS: default auto-load/cache/missing file, ML polling/auth, cache, export, failure recovery, cancellation during upload, quick fallback');
})().catch(error=>{console.error(error);process.exitCode=1});
