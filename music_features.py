"""Deterministic spectral pitch candidates, not instrument/source separation."""
import math

def voices(power, rate, window, previous=None):
    total=sum(power)
    empty={'pitch':None,'strength':0.0,'confidence':0.0}
    if total<1e-12:return [dict(empty) for _ in range(4)]
    peaks=[]
    for k in range(2,len(power)-1):
        hz=k*rate/window
        if 65<=hz<=2100 and power[k]>power[k-1] and power[k]>=power[k+1] and power[k]>total*.008:
            a,b,c=[math.log(max(v,1e-30)) for v in power[k-1:k+2]]
            offset=max(-.5,min(.5,.5*(a-c)/(a-2*b+c))) if a-2*b+c else 0
            hz=(k+offset)*rate/window
            strength=sum(power[max(0,k-1):k+2])/total
            peaks.append({'pitch':69+12*math.log2(hz/440),'strength':min(1,math.sqrt(strength)),'confidence':min(1,strength*2),'hz':hz})
    peaks.sort(key=lambda x:x['strength'],reverse=True)
    candidates=[]
    for p in peaks:
        # Suppress obvious integer overtones of a stronger lower peak.
        if any(p['hz']>q['hz']*1.8 and abs(12*math.log2(p['hz']/q['hz']/round(p['hz']/q['hz'])))<.55 for q in candidates):continue
        candidates.append(p)
    melodic=[p for p in candidates if p['pitch']>=48]
    old=previous[0]['pitch'] if previous else None
    lead=max(melodic,key=lambda p:p['strength']*(1+.25*math.exp(-abs(p['pitch']-old)/4) if old else 1),default=None)
    remaining=[p for p in candidates if p is not lead]
    # Lower accompaniment first: ordering is explicit, not semantic instrument labels.
    remaining=sorted(sorted(remaining,key=lambda p:p['strength'],reverse=True)[:3],key=lambda p:p['pitch'])
    result=([lead] if lead else [None])+remaining
    return [{k:p[k] for k in ('pitch','strength','confidence')} if p else dict(empty) for p in (result+[None]*4)[:4]]
