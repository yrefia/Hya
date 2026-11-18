"""Foreground note estimates from Rubia's Demucs stems. Times are source seconds."""
import hashlib
from pathlib import Path

# Polyphony, lowest/highest MIDI key, within-note bend (semitones), glide (seconds).
PROFILES = {
    'piano': (6, 28, 100, .08, 0),
    'vocals': (1, 42, 89, .45, .06),
    'guitar': (4, 38, 94, .45, .06),
    'other': (5, 30, 100, .9, .10),
    'bass': (3, 24, 72, .9, .10),
}
STEP = .02


def cache_path(directory, background):
    key = hashlib.sha256(Path(__file__).read_bytes())
    key.update(background)
    return directory / ('rubia-' + key.hexdigest() + '.json')


def estimate(audio, name, rate=44100):
    """Track spectral peaks, using level attacks and a decaying harmonic residual."""
    import numpy as np
    from scipy.signal import resample_poly, find_peaks

    count, low, high, bend, glide = PROFILES[name]
    signal = resample_poly(audio, 1, 4, axis=0)
    if signal.ndim == 1:
        signal = signal[:, None]
    sr = rate / 4
    size = 2048 if name in ('bass', 'other') else 1024
    fft = size * 4
    padded = np.pad(signal, ((size//2, size//2), (0, 0)))
    window = np.hanning(size)[:, None]
    duration = len(audio) / rate
    floor = max(.00025, float(np.sqrt(np.mean(signal**2))) * .045)
    active = {}
    notes = []
    last_level = 0.
    last_spectrum = np.zeros(fft//2+1)
    for frame in range(int(np.ceil(duration / STEP))):
        t = frame * STEP
        pos = round(t * sr)
        block = padded[pos:pos+size]
        short = signal[pos:pos+round(STEP*sr)]
        if not len(short):
            break
        level = float(np.sqrt(np.mean(short**2)))
        spectrum = np.sqrt(np.mean(abs(np.fft.rfft(block*window, fft, axis=0))**2, axis=1))
        peaks = find_peaks(spectrum)[0]
        peaks = peaks[spectrum[peaks] > max(floor*size*.03, spectrum.max()*.055)]
        residual = spectrum.copy()
        # Discount the previous frame's decaying partials while scoring new attacks.
        for key, note in active.items():
            fundamental = 440 * 2**((note['samples'][-1]-69)/12) * fft/sr
            decay = np.exp(-(t-note['start'])/.32)
            for h in range(1, 7):
                center = round(fundamental*h)
                width = max(3, round(center*.016))
                sl = slice(max(0, center-width), center+width+1)
                residual[sl] -= last_spectrum[sl] * (.35+.45*decay)/np.sqrt(h)
        candidates = []
        for k in peaks:
            # Sub-bin peak interpolation measures vibrato independently of MIDI.
            a,b,c = np.log(np.maximum(1e-12,spectrum[k-1:k+2]))
            offset = .5*(a-c)/(a-2*b+c) if a-2*b+c else 0.
            pitch = 69+12*np.log2((k+offset)*sr/fft/440)
            key = round(pitch)
            if not low <= key <= high:
                continue
            rise = spectrum[k] / max(floor, last_spectrum[k])
            if key not in active and rise < 1.18 and active:
                closest = min(active, key=lambda n: abs(n-pitch))
                if abs(pitch-closest) <= bend:
                    key = closest
            same = key in active
            attack = rise > 1.18 or level > 1.18*last_level
            if not same and not attack:
                continue
            score = spectrum[k] if same else max(0., residual[k])
            candidates.append((score, key, pitch, k, rise))
        chosen = {}
        if level > floor and candidates:
            strongest = max(row[0] for row in candidates)
            # Prefer fundamentals over partials of pitches already explained in this frame.
            for score, key, pitch, k, rise in sorted(candidates, reverse=True):
                if score < strongest*.16 or len(chosen) >= count:
                    break
                if key in chosen:
                    continue
                if any(2 <= round(k/base) <= 7 and abs(k/base-round(k/base)) < .045
                       and score < strength*.85 for base,strength in chosen.values()):
                    continue
                chosen[key] = (k, score)
                measured = round(key+float(np.clip(pitch-key, -bend, bend)), 3)
                note = active.get(key)
                retrigger = (note and t-note['start'] >= .10 and level > last_level*1.35
                             and rise > 1.12)
                if not note or retrigger:
                    note = {'start': round(t, 3), 'pitch': key, 'samples': []}
                    notes.append(note)
                    active[key] = note
                note['samples'].append(measured)
                note['end'] = round(min(duration, t+STEP), 6)
        active = {key:active[key] for key in chosen}
        last_level, last_spectrum = level, spectrum
    notes = [note for note in notes if len(note['samples']) >= 3]
    # Pair adjacent note endings to new attacks once, by nearest pitch.
    endings = {}
    for note in notes:
        tick = round(note['start']/STEP)
        nearby = endings.get(tick, [])
        if glide and nearby:
            previous = min(nearby, key=lambda n: abs(n['pitch']-note['pitch']))
            nearby.remove(previous)
            note['fromPitch'] = previous['samples'][-1]
        endings.setdefault(round(note['end']/STEP), []).append(note)
    return {'notes': notes, 'glide': glide}


def build(background, source, stems_dir=None):
    import json
    import tempfile
    import numpy as np
    import soundfile as sf
    from ml_pipeline import RATE, decode, separate_stems, drum_onsets

    result = json.loads(background)
    if stems_dir is None:
        with tempfile.TemporaryDirectory() as folder:
            audio = decode(source, Path(folder)/'audio.wav')
            stems = separate_stems(audio, lambda **event: None)
        def read(name):
            return stems[name]
    else:
        def read(name):
            audio, rate = sf.read(stems_dir/(name+'.wav'), dtype='float32', always_2d=True)
            if rate != RATE or abs(len(audio)/rate-result['duration']) > .001:
                raise ValueError(f'{name} 分轨采样率或长度与原曲不符')
            return audio
    foreground = {name: estimate(read(name), name) for name in PROFILES}
    hits = drum_onsets(read('drums'))
    if hits:
        threshold = np.quantile([hit['strength'] for hit in hits], .70)
        hits = [hit for hit in hits if hit['strength'] >= threshold]
    result['foreground'] = {'step': STEP, 'tracks': foreground, 'accents': hits}
    return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
