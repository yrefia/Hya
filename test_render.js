// Canvas regression: stored notes/history stay fixed vertically across time and seeks.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let paths=[],rects=[],current=[];
const ctx=new Proxy({beginPath(){current=[]},moveTo(x,y){current.push([x,y])},lineTo(x,y){current.push([x,y])},stroke(){paths.push(current)},fillRect(...args){rects.push(args)},arc(){},save(){},restore(){},rect(){},clip(){}},{get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
const elements={};const document={getElementById:id=>elements[id]||(elements[id]={checked:true,currentTime:6,paused:true,width:800,height:480,getBoundingClientRect:()=>({width:800,height:480}),getContext:()=>ctx})};
const box={window:{addEventListener(){}},document,location:{search:''},URLSearchParams,devicePixelRatio:1,matchMedia:()=>({matches:false}),requestAnimationFrame:()=>{}};vm.createContext(box);vm.runInContext(fs.readFileSync('ui.html','utf8').split('<script>')[1].split('</script>')[0],box);
const frames=Array.from({length:101},(_,i)=>({t:i/10,energy:.5,centroid:440,rms:.2,voices:[{pitch:60+i/100,confidence:1},{pitch:48,confidence:1}]}));
vm.runInContext('result='+JSON.stringify({duration:10,rate:22050,frames})+';',box);
function render(t,staticOnly=false){elements.audio.currentTime=t;paths=[];rects=[];vm.runInContext(`draw(${staticOnly})`,box);return {paths:paths.filter(p=>p.length>20).slice(0,2),notes:rects.filter(r=>r[3]===4)}}
let a=render(1),b=render(2);for(let j=0;j<2;j++)for(let i=0;i<a.paths[j].length;i++){assert.equal(a.paths[j][i][1],b.paths[j][i][1]);assert(Math.abs(a.paths[j][i][0]-b.paths[j][i][0]-725/12)<1e-8)}assert.deepEqual(render(2),b);assert.deepEqual(render(1),a);
const tracks={vocals:{notes:[{start:1,end:2,pitch:69,amplitude:.7},{start:8,end:9,pitch:71,amplitude:.8}]},bass:{notes:[{start:2,end:4,pitch:36,amplitude:.5}]},drums:{onsets:[{t:3,strength:.7},{t:9,strength:1}]},piano:{notes:[{start:4,end:5,pitch:60,amplitude:.8}]},guitar:{notes:[{start:5,end:6,pitch:55,amplitude:.7}]},other:{frames:[{t:3,energy:.5,centroid:2000},{t:4,energy:.3,centroid:1500}]}};
vm.runInContext('result='+JSON.stringify({duration:10,frames,tracks})+';',box);
a=render(4);b=render(4.5);assert.equal(a.notes.length,5,'all four pitched tracks including upcoming notes');for(let i=1;i<a.notes.length;i++){assert.equal(a.notes[i][1],b.notes[i][1]);assert(Math.abs(a.notes[i][2]-b.notes[i][2])<1e-8);assert(Math.abs(a.notes[i][0]-b.notes[i][0]-725/24)<1e-8)}assert.deepEqual(render(4),a);assert.equal(render(6,true).notes.length,5,'export includes all pitched tracks');
vm.runInContext("$('motion').checked=false",box);assert.deepEqual(render(6).notes,render(7).notes,'reduced motion retains fixed page positions');
assert.equal(vm.runInContext('nearestFrame(result.frames, 1.16).t',box),1.2);
console.log('PASS: legacy and ML history, pause/seek, upcoming notes and six tracks, whole-song export, reduced motion, nearest frame');
