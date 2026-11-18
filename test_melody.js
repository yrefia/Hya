const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('ui.html','utf8');
const box={};vm.createContext(box);
vm.runInContext(source.slice(source.indexOf('function selectMelody('),source.indexOf('function prepareMelodies(')),box);
const note=(start,end,pitch,amplitude=.3)=>({start,end,pitch,amplitude});
const choose=(notes,duration=4,lane='piano')=>box.selectMelody(notes,duration,lane);
const at=(path,t)=>path.find(s=>s.start<=t&&s.end>t)?.note?.pitch??null;
// Soft melody, louder changing accompaniment: amplitude cannot hijack the voice.
const melody=[note(0,1,72),note(1,2,74),note(2,3,76),note(3,4,74)];
const accompaniment=[note(0,4,48,1),note(0,1,60,1),note(1,2,64,1),note(2,3,62,1),note(3,4,60,1)];
let path=choose([...melody,...accompaniment]);
assert.deepEqual([.5,1.5,2.5,3.5].map(t=>at(path,t)),[72,74,76,74]);
// A brief high ornament must not replace a coherent sustained melody.
path=choose([...melody,note(.5,.58,88,1),...accompaniment]);
assert.equal(at(path,.55),72);
// Never jump into a bass tail after the melody ends.
path=choose([note(0,1,72),note(0,4,48,1)]);
assert.equal(at(path,.5),72);assert.equal(at(path,2),null);
// Actual rests and repeated notes survive; no invented continuous pitch.
path=choose([note(0,1,72),note(2,3,72)]);
assert.equal(at(path,1.5),null);assert.equal(at(path,2.5),72);
path=choose([note(0,4,36,.3),note(0,4,60,1)],4,'bass');
assert.equal(at(path,2),36);
assert.equal(choose([],4).length,0);
const original=JSON.stringify(melody);choose(melody);assert.equal(JSON.stringify(melody),original);
assert.deepEqual(JSON.stringify(choose([...melody].reverse())),JSON.stringify(choose(melody)));
console.log('PASS: soft melody, loud accompaniment, ornament, bass tails, rests, bass register, immutable notes and deterministic ordering');
