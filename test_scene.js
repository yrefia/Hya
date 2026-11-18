// Shared layers: fixed pen, real pitch changes, deterministic seeks, and silent gaps.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let strokes=[],dots=[],path=[],color;
const ctx=new Proxy({beginPath(){path=[]},moveTo(x,y){path.push([x,y])},lineTo(x,y){path.push([x,y])},stroke(){strokes.push({color,points:path})},arc(x,y,r){dots.push({x,y,r,color})},save(){},restore(){}},{get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>{o[k]=v;if(k==='strokeStyle')color=v;return true}});
const dummy=new Proxy({},{get:()=>()=>{},set:()=>true}),elements={};
const document={getElementById:id=>elements[id]||(elements[id]={checked:true,currentTime:0,paused:true,getBoundingClientRect:()=>({width:1000,height:600}),getContext:()=>id==='scene'?ctx:dummy})};
const box={window:{addEventListener(){}},document,location:{search:''},URLSearchParams,devicePixelRatio:1,matchMedia:()=>({matches:false}),requestAnimationFrame(){},Uint8Array};
vm.createContext(box);vm.runInContext(fs.readFileSync('ui.html','utf8').split('<script>')[1].split('</script>')[0],box);
const run=code=>vm.runInContext(code,box);
const notes=[{start:0,end:1,pitch:60,amplitude:.8},{start:1,end:3,pitch:72,amplitude:.8},{start:0,end:3,pitch:40,amplitude:.2}];
const tracks={vocals:{notes},piano:{notes},bass:{notes:[{start:0,end:3,pitch:36,amplitude:.8}]},guitar:{notes:[{start:0,end:3,pitch:67,amplitude:.8}]},drums:{onsets:[{t:1.4,strength:.8}]},other:{frames:[{t:0,energy:.5},{t:3,energy:.5}]}};
run('result='+JSON.stringify({duration:5,frames:[],tracks})+';prepareMelodies()');
function render(t){elements.audio.currentTime=t;strokes=[];dots=[];run('drawScene()');return JSON.parse(JSON.stringify({strokes,dots}))}
let a=render(.5),b=render(1.5);const gold='#edcc8e',blue='#9ebfee';
const dot=(r,c)=>r.dots.find(d=>d.color===c);
assert.equal(dot(a,gold).x,dot(b,gold).x,'pen must not travel horizontally');
assert(dot(b,gold).y<dot(a,gold).y,'higher notes move the pen upward');
assert.equal(dot(b,gold).y,dot(b,blue).y,'same pitch shares same y across stems; no separate lanes');
assert.equal(b.dots.length,6,'six layers overlap the same canvas');
for(const stroke of b.strokes.filter(s=>s.color===gold))assert(stroke.points.every(p=>p[0]<=dot(b,gold).x),'no melody drawn beyond current pen');
assert.deepEqual(render(.5),a,'seeking rebuilds the exact previous trace');assert.deepEqual(render(1.5),b,'pause/redraw never changes history');
assert(!dot(render(3.5),gold),'silent gap has no invented melody');
assert.equal(run('scenePoint(lanes[0],.5).pitch'),60,'strongest simultaneous note is chosen');
run('result.piano_solo=true');assert.deepEqual(render(1.5).dots.map(d=>d.color),[blue]);
run("result={duration:2,frames:[],tracks:{vocals:{notes:[],note_candidates:[{start:0,end:2,pitch:80}]}}};prepareMelodies()");assert.equal(render(1).dots.length,0,'uncertain candidates never become melody');
console.log('PASS: fixed pen, vertical pitch movement, shared layers, six colors, past-only paths, pause/seek, silence, solo and candidates');
