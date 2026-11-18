"""Opt-in end-to-end check with known sine-wave melody (requires audio .venv).
Run: .venv/bin/python test_synthetic_melody.py
Artifacts: outputs/validation/simple-melody/ (audio, truth, predictions, report).
"""
import argparse
import shutil
import json
from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf
from ml_pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/validation/simple-melody'
RATE = 44100
DURATION = 9.0


def synth(notes):
    audio = np.zeros(round(DURATION * RATE), dtype=np.float32)
    for n in notes:
        start, end = round(n['start'] * RATE), round(n['end'] * RATE)
        t = np.arange(end - start) / RATE
        envelope = np.minimum(1, t / .015) * np.minimum(1, (len(t) / RATE - t) / .025)
        hz = 440 * 2 ** ((n['pitch'] - 69) / 12)
        audio[start:end] += n['amplitude'] * np.sin(2 * np.pi * hz * t) * envelope
    return audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Publish passing fixtures to assets/demos')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    melody = [dict(start=round(.5 + i * .9 + (.7 if i >= 4 else 0), 3),
                   end=round(1.2 + i * .9 + (.7 if i >= 4 else 0), 3),
                   pitch=p, amplitude=.14)
              for i, p in enumerate([72, 74, 76, 79, 76, 74, 72, 72])]
    bass = [dict(n, pitch=p, amplitude=.32) for n, p in zip(melody, [48, 50, 52, 55, 52, 50, 48, 48])]
    (OUT / 'truth.json').write_text(json.dumps(dict(duration=DURATION, melody=melody, bass=bass), indent=2))
    for name, notes in [('pure', melody), ('louder-bass', melody + bass)]:
        wav = OUT / (name + '.wav')
        sf.write(wav, synth(notes), RATE, subtype='PCM_16')
        run_pipeline(wav, OUT / (name + '.json'), piano_solo=True)
    # Exercise the exact frontend selector, without reimplementing it in Python.
    script = r'''
const fs=require('fs'),vm=require('vm');
const folder=process.argv[1],source=fs.readFileSync('ui.html','utf8'),box={};vm.createContext(box);
vm.runInContext(source.slice(source.indexOf('function selectMelody('),source.indexOf('function prepareMelodies(')),box);
const truth=JSON.parse(fs.readFileSync(folder+'/truth.json'));
const report={};
for(const name of ['pure','louder-bass']){
 const result=JSON.parse(fs.readFileSync(folder+'/'+name+'.json'));
 const notes=result.tracks.piano.notes,path=box.selectMelody(notes,truth.duration,'piano');
 const at=t=>path.find(s=>s.start<=t&&s.end>t)?.note?.pitch??null;
 let correct=0,total=0,recognized=0,restCorrect=0,restTotal=0;
 const perNote=truth.melody.map(n=>{
  const samples=[];
  for(let t=n.start+.15;t<n.end-.12;t+=.05){
   const pitch=at(t);samples.push(pitch);total++;if(pitch===n.pitch)correct++;
   if(notes.some(p=>p.start<=t&&p.end>t&&p.pitch===n.pitch))recognized++;
  }
  const matches=notes.filter(p=>p.pitch===n.pitch&&p.end>n.start&&p.start<n.end);
  return {expected:n,selectedPitches:[...new Set(samples)],detected:matches};
 });
 for(let t=.1;t<truth.duration-.1;t+=.05){
  if(truth.melody.some(n=>t>=n.start-.15&&t<n.end+.15))continue;
  restTotal++;if(at(t)===null)restCorrect++;
 }
 report[name]={recognizedFrames:recognized,totalFrames:total,selectedCorrectFrames:correct,
  melodyAccuracy:correct/total,restAccuracy:restCorrect/restTotal,perNote};
}
fs.writeFileSync(folder+'/report.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(Object.fromEntries(Object.entries(report).map(([k,v])=>[k,{...v,perNote:undefined}]))));
if(Object.values(report).some(r=>r.melodyAccuracy<.95||r.restAccuracy<.95))process.exitCode=1;
'''
    subprocess.run(['node', '-e', script, str(OUT)], cwd=ROOT, check=True)
    if args.publish:
        target = ROOT / 'assets/demos'
        target.mkdir(parents=True, exist_ok=True)
        for name in ('pure', 'louder-bass'):
            data = json.loads((OUT / (name + '.json')).read_text())
            data['reference_melody'] = melody
            data['warnings'] = ['标准正弦波示范：参考音符来自生成配方，识别音符来自 Basic Pitch，二者独立。']
            (target / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False))
            shutil.copyfile(OUT / (name + '.wav'), target / (name + '.wav'))
        shutil.copyfile(OUT / 'report.json', target / 'validation.json')


if __name__ == '__main__':
    main()
