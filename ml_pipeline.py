"""Offline Demucs + Basic Pitch worker. stdout is a JSON-lines progress protocol.

The HTTP process stays dependency-free; this worker runs in the audio .venv.
All times are seconds from the decoded source start, with no trimming or stem
normalization. Models are loaded only from the local model repository.
"""
import contextlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

VERSION = 'hya-ml-2'
STEMS = ('vocals', 'bass', 'piano', 'guitar', 'drums', 'other')
PITCHED = ('vocals', 'bass', 'piano', 'guitar')
RATE = 44100
WINDOW = 4096
HOP = 2205  # 20 visual frames / second
MAX_DURATION = 600
ROOT = Path(__file__).resolve().parent
MODEL_REPO = ROOT / '.models' / 'audio-separator'


def acoustic_frames(audio, rate=RATE):
    """Channel-power average preserves energy even for anti-phase stereo."""
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]
    if not len(audio):
        return []
    window = np.hanning(WINDOW).astype(np.float32)[:, None]
    frequencies = np.fft.rfftfreq(WINDOW, 1 / rate)
    frames = []
    for start in range(0, len(audio), HOP):
        samples = audio[start:start + WINDOW]
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        padded = np.pad(samples, ((0, WINDOW - len(samples)), (0, 0)))
        power = np.mean(np.abs(np.fft.rfft(padded * window, axis=0)) ** 2, axis=1)
        total = float(power.sum())
        frames.append({
            't': min((start + WINDOW / 2) / rate, len(audio) / rate),
            'energy': max(0., min(1., (20 * math.log10(max(rms, 1e-9)) + 60) / 60)),
            'rms': rms,
            'centroid': float(np.dot(power, frequencies) / total) if total > 1e-15 else 0.,
        })
    return frames


def drum_onsets(audio, rate=RATE):
    """Positive spectral flux peaks; events are onsets, not inferred beats."""
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]
    hop, size = 441, 1024  # 10 ms events, independent of visual frame cadence
    window = np.hanning(size)[:, None]
    previous = np.zeros(size // 2 + 1)
    flux, times = [], []
    for start in range(0, len(audio), hop):
        block = audio[start:start + size]
        block = np.pad(block, ((0, size - len(block)), (0, 0)))
        magnitude = np.sqrt(np.mean(np.abs(np.fft.rfft(block * window, axis=0)) ** 2, axis=1))
        flux.append(float(np.maximum(magnitude - previous, 0).mean()))
        times.append(min((start + size / 2) / rate, len(audio) / rate))
        previous = magnitude
    if not flux or max(flux) < 1e-5:
        return []
    peak = max(flux)
    events = []
    for index, value in enumerate(flux):
        neighborhood = flux[max(0, index - 10):index + 11]
        threshold = max(peak * .08, float(np.median(neighborhood)) * 1.5, 1e-5)
        before = flux[index - 1] if index else 0
        after = flux[index + 1] if index + 1 < len(flux) else 0
        if value > threshold and value > before and value >= after:
            event = {'t': times[index], 'strength': min(1., value / peak)}
            if events and event['t'] - events[-1]['t'] < .08:
                if event['strength'] > events[-1]['strength']:
                    events[-1] = event
            else:
                events.append(event)
    return events


def clean_notes(events, duration):
    notes = []
    for start, stop, pitch, amplitude, _bends in events:
        values = (float(start), float(stop), float(pitch), float(amplitude))
        if not all(math.isfinite(value) for value in values):
            continue
        start, stop = max(0., values[0]), min(duration, values[1])
        if stop > start:
            notes.append({'start': start, 'end': stop, 'pitch': int(pitch),
                          'amplitude': max(0., min(1., values[3]))})
    return sorted(notes, key=lambda note: (note['start'], note['pitch']))


def decode(input_path, target):
    import imageio_ffmpeg
    import soundfile as sf
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-y', '-i', str(input_path), '-map', '0:a:0', '-t', str(MAX_DURATION + .1),
               '-ac', '2', '-ar', str(RATE), '-c:a', 'pcm_f32le', str(target)]
    converted = subprocess.run(command, capture_output=True, timeout=90)
    if converted.returncode:
        raise ValueError('无法解码音频，请尝试 WAV、MP3、M4A 或 AIFF。')
    with sf.SoundFile(target) as handle:
        if not handle.frames:
            raise ValueError('音频为空。')
        if handle.frames > RATE * MAX_DURATION:
            raise ValueError('MVP 支持最长 10 分钟的音频，请先裁剪。')
        audio = handle.read(dtype='float32', always_2d=True)
    import numpy as np
    if not np.isfinite(audio).all():
        raise ValueError('音频包含无效采样值。')
    return audio


def run_pipeline(input_path, output_path, progress_callback=None):
    report = progress_callback or (lambda **event: None)
    report(stage='decoding', message='正在解码音频', progress=.04)
    import numpy as np
    import soundfile as sf
    import torch
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.manual_seed(0)
    warnings = ['分轨可能串音；音符为模型估计，振幅分数不是校准置信度。',
                '鼓点为瞬态起音估计，不等同于节拍或 BPM。']
    # Keep intermediates inside the job folder so the parent can remove them
    # even when cancellation terminates this process before context cleanup.
    with tempfile.TemporaryDirectory(dir=Path(output_path).parent, prefix='hya-ml-') as temporary:
        folder = Path(temporary)
        audio = decode(input_path, folder / 'decoded.wav')
        duration = len(audio) / RATE
        report(stage='separating', message='正在分离人声、低音、钢琴、吉他、鼓与其他声部', progress=.12)
        from demucs.pretrained import get_model
        from demucs.apply import apply_model, BagOfModels
        weights = MODEL_REPO / '5c90dfd2.safetensors'
        if weights.is_file():
            from demucs.hf import load_safetensors_model
            model = BagOfModels([load_safetensors_model(weights)]).eval()
        elif (MODEL_REPO / 'htdemucs_6s.yaml').is_file() and list(MODEL_REPO.glob('5c90dfd2*.th')):
            model = get_model('htdemucs_6s', repo=MODEL_REPO)
        else:
            raise RuntimeError('缺少本地 Demucs 六轨模型，请按 AUDIO_TOOLS.md 准备 htdemucs_6s。')
        if set(model.sources) != set(STEMS):
            raise ValueError('Demucs 模型必须包含完整六轨。')
        signal = torch.from_numpy(audio.T.copy())
        # Use one common gain for all channels/stems; avoid mono cancellation.
        mean, scale = signal.mean(), signal.std().clamp_min(1e-8)
        def separation_progress(state):
            position = state.get('segment_offset', 0) / max(1, len(audio))
            report(stage='separating', message='正在分离六个声部',
                   progress=.12 + .43 * min(1., position))
        with torch.inference_mode():
            if float(scale) <= 1e-8:
                separated = torch.zeros((len(model.sources), 2, len(audio)))
            else:
                separated = apply_model(model, ((signal - mean) / scale)[None],
                                        device='cpu', shifts=0, split=True, overlap=.25,
                                        progress=False, callback=separation_progress)[0]
                separated = separated * scale + mean
        stems = {name: value.numpy().T for name, value in zip(model.sources, separated)}
        del model, separated, signal
        report(stage='features', message='正在提取各声部能量与鼓点', progress=.57)
        frames = acoustic_frames(audio)
        tracks = {name: {'frames': acoustic_frames(stem)} for name, stem in stems.items()}
        tracks['drums']['onsets'] = drum_onsets(stems['drums'])
        from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
        from basic_pitch.inference import Model, predict
        pitch_model = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
        for index, name in enumerate(PITCHED):
            report(stage='transcribing_' + name,
                   message='正在转写' + dict(vocals='人声', bass='低音', piano='钢琴', guitar='吉他')[name] + '音符',
                   progress=.62 + index * .09)
            stem = stems[name]
            # Use the stronger channel to prevent phase cancellation when downmixing.
            channel = int(np.argmax(np.mean(stem.astype(np.float64) ** 2, axis=0)))
            stem_path = folder / (name + '.wav')
            sf.write(stem_path, stem[:, channel], RATE, subtype='FLOAT')
            if np.max(np.abs(stem)) < 1e-7:
                events = []
            else:
                _outputs, _midi, events = predict(stem_path, pitch_model)
            tracks[name]['notes'] = clean_notes(events, duration)
        result = {
            'version': VERSION, 'duration': duration, 'rate': RATE, 'window': WINDOW, 'hop': HOP,
            'frames': frames, 'tracks': tracks, 'warnings': warnings,
            'provenance': {'demucs': importlib.metadata.version('demucs'),
                           'demucs_model': 'htdemucs_6s/5c90dfd2', 'demucs_shifts': 0,
                           'basic_pitch': importlib.metadata.version('basic-pitch'),
                           'basic_pitch_backend': 'onnx', 'device': 'cpu',
                           'normalization': 'shared stereo gain; no per-stem rescaling',
                           'pitch_input': 'stronger channel of each stem',
                           'onsets': 'positive spectral flux; within-track relative strength'},
        }
        Path(output_path).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    report(stage='complete', message='分析完成', progress=1.)
    return result


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: ml_pipeline.py INPUT OUTPUT_JSON')
    protocol = sys.stdout
    def report(**event):
        print(json.dumps(event, ensure_ascii=False), file=protocol, flush=True)
    # Libraries may print status to stdout; keep worker protocol unambiguous.
    try:
        with contextlib.redirect_stdout(sys.stderr):
            run_pipeline(Path(sys.argv[1]), Path(sys.argv[2]), report)
    except Exception as exc:
        report(stage='failed', message=str(exc), error=str(exc), progress=0.)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
