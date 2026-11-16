// Exercise the real browser script with controlled network responses.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('ui.html','utf8').split('<script>')[1].split('</script>')[0];
function harness(responses){
 const requests=[],downloads=[],elements={};
 const ctx=new Proxy({},{get:()=>()=>{},set:()=>true});
 const element=id=>elements[id]||(elements[id]={value:id==='mode'?'ml':'',checked:true,currentTime:0,getBoundingClientRect:()=>({width:800,height:600}),getContext:()=>ctx,pause(){},load(){},removeAttribute(key){delete this[key]},toBlob(callback){callback(new Blob(['png']))}});
 const document={getElementById:element,createElement:()=>({click(){downloads.push(this.download)}})};
 const box={document,location:{search:'?token=test'},URLSearchParams,Blob,devicePixelRatio:1,matchMedia:()=>({matches:false}),requestAnimationFrame:()=>{},setTimeout:fn=>{queueMicrotask(fn);return 1},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},fetch:async(path,options={})=>{requests.push({path,options});const next=responses.shift();assert(next,`Unexpected fetch ${path}`);if(typeof next==='function')return next(path,options);return {ok:next.ok!==false,status:next.status||200,json:async()=>next.body??next}}};
 vm.createContext(box);vm.runInContext(source,box);return {box,elements,requests,downloads,run:code=>vm.runInContext(code,box)};
}
const result={version:'hya-ml-1',duration:3,frames:[{t:0,rms:.1,energy:.5,centroid:400}],tracks:{vocals:{notes:[]},bass:{notes:[]},drums:{onsets:[]}},warnings:['分轨可能存在泄漏']};
(async()=>{
 let h=harness([{id:'a',state:'queued',progress:0},{id:'a',state:'running',message:'分轨中',progress:.3},{id:'a',state:'done',cached:true,progress:1},result]);
 await h.run("load(new Blob(['audio']), 'test.wav')");
 assert.deepEqual(h.requests.map(r=>r.path),['/jobs','/jobs/a','/jobs/a','/jobs/a/result']);assert(h.requests.every(r=>r.options.headers['X-Hya-Token']==='test'));assert.equal(h.elements.file.disabled,false);assert.equal(h.elements.save.disabled,false);assert.match(h.elements.status.textContent,/已复用缓存/);assert.match(h.elements.warnings.textContent,/泄漏/);
 h.run("$('save').onclick(); $('png').onclick()");assert.deepEqual(h.downloads,['hya-analysis.json','hya-tracks.png']);
 h=harness([{id:'b',state:'queued'},{id:'b',state:'error',error:'缺少模型'}]);await h.run("load(new Blob(['audio']), 'bad.wav')");assert.match(h.elements.status.textContent,/缺少模型/);assert.equal(h.elements.file.disabled,false);assert.equal(h.elements.save.disabled,true);assert.equal(h.run('result'),null);
 h=harness([{id:'c',state:'queued'}, {id:'c',state:'cancelled'}]);const pending=h.run("load(new Blob(['audio']), 'cancel.wav')");h.run("$('cancel').onclick()");await pending;assert.equal(h.requests[1].options.method,'DELETE');assert.equal(h.requests[1].path,'/jobs/c');assert.match(h.elements.status.textContent,/已取消/);assert.equal(h.elements.file.disabled,false);assert.equal(h.run('result'),null);
 h=harness([{ok:false,body:{error:'忙碌'}}]);await h.run("load(new Blob(['audio']), 'busy.wav')");assert.match(h.elements.status.textContent,/忙碌/);assert.equal(h.elements.mode.disabled,false);
 h=harness([{...result,tracks:undefined}]);h.run("$('mode').value='quick'");await h.run("load(new Blob(['audio']), 'quick.wav')");assert.equal(h.requests[0].path,'/analyze');assert.equal(h.elements.cancel.hidden,true);
 console.log('PASS: ML polling/auth, cache, export, failure recovery, cancellation during upload, quick fallback');
})().catch(error=>{console.error(error);process.exitCode=1});
