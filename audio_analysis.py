import math, cmath, wave, struct
from music_features import voices

RATE, WINDOW, HOP = 22050, 4096, 1024
VERSION = 'hya-python-3'

def fft(values):
    n = len(values)
    if n == 1: return values
    even, odd = fft(values[::2]), fft(values[1::2])
    terms = [cmath.exp(-2j * math.pi * k / n) * odd[k] for k in range(n//2)]
    return [even[k]+terms[k] for k in range(n//2)] + [even[k]-terms[k] for k in range(n//2)]

def analyze(path):
    with wave.open(str(path), 'rb') as f:
        if f.getsampwidth()!=2 or f.getnchannels()!=1 or f.getframerate()!=RATE:
            raise ValueError('分析文件需要 22050 Hz / 单声道 / 16-bit PCM')
        count=f.getnframes()
        if not count: raise ValueError('音频为空')
        if count > RATE*600: raise ValueError('原型支持最长 10 分钟的音频，请先裁剪。')
        data=struct.unpack('<'+'h'*count, f.readframes(count))
    frames=[]
    previous=None
    window=[.5-.5*math.cos(2*math.pi*i/(WINDOW-1)) for i in range(WINDOW)]
    for start in range(0,count,HOP):
        x=[v/32768 for v in data[start:start+WINDOW]]
        rms=math.sqrt(sum(v*v for v in x)/len(x))
        x += [0.]*(WINDOW-len(x))
        spectrum=[abs(v)**2 for v in fft([v*w for v,w in zip(x,window)])[:WINDOW//2+1]]
        total=sum(spectrum)
        centroid=sum(i*RATE/WINDOW*p for i,p in enumerate(spectrum))/total if total>1e-15 else 0
        bands=[sum(p for i,p in enumerate(spectrum) if lo<=i*RATE/WINDOW<hi)/total if total>1e-15 else 0 for lo,hi in [(0,250),(250,2000),(2000,RATE)]]
        tracks=voices(spectrum,RATE,WINDOW,previous)
        previous=tracks
        flatness=math.exp(sum(math.log(max(p,1e-20)) for p in spectrum)/len(spectrum))/(total/len(spectrum)+1e-20) if total>1e-12 else 0
        frames.append({'t':min(count/RATE,(start+WINDOW/2)/RATE),'energy':max(0,min(1,(20*math.log10(max(rms,1e-9))+60)/60)), 'rms':rms,'centroid':centroid,'bands':bands,'voices':tracks,'noise':min(1,flatness*4)})
    from statistics import median
    original=[[dict(v) for v in f['voices']] for f in frames]
    for i,frame in enumerate(frames):
        for j,v in enumerate(frame['voices']):
            if v['pitch'] is None:continue
            neighbors=[original[k][j]['pitch'] for k in range(max(0,i-1),min(len(frames),i+2)) if original[k][j]['pitch'] is not None]
            if len(neighbors)==3 and abs(v['pitch']-median(neighbors))>3:
                v.update(pitch=None,strength=0,confidence=0)
    shape=[]
    for i in range(180):
        segment=frames[i*len(frames)//180:max(i*len(frames)//180+1,(i+1)*len(frames)//180)]
        shape.append(sum(f['energy'] for f in segment)/len(segment))
    return {'version':VERSION,'rate':RATE,'window':WINDOW,'hop':HOP,'duration':count/RATE,'frames':frames,'shape':shape}
