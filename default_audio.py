"""Local default song discovery and durable installation (audio is Git-ignored)."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT / 'outputs' / 'default'
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.aiff', '.aif', '.flac', '.ogg', '.aac'}


def default_audio():
    override = os.environ.get('HYA_DEFAULT_AUDIO') or os.environ.get('HYA_TEST_AUDIO')
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path, path.stem
        raise FileNotFoundError('指定的默认曲目不存在：' + str(path))
    manifest = DEFAULT_DIR / 'track.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text())
        path = DEFAULT_DIR / Path(data['file']).name
        if path.is_file():
            return path, data['name']
    desktop = Path.home() / 'Desktop'
    matches = sorted(path for path in desktop.glob('*')
                     if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
                     and 'myheartwillgoon' in re.sub(r'[^a-z]', '', path.stem.lower()))
    if matches:
        return matches[0], matches[0].stem
    raise FileNotFoundError('未找到默认曲目 My heart will go on，请放到桌面或导入音频。')


def install_default(source):
    source = Path(source).expanduser().resolve(strict=True)
    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    target = DEFAULT_DIR / source.name
    if source != target:
        temporary = target.with_suffix(target.suffix + '.tmp')
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    data = {'file': target.name, 'name': source.stem}
    if source.suffix.lower() not in {'.mp3', '.m4a'}:
        playback = DEFAULT_DIR / (source.stem + '.playback.m4a')
        temporary = playback.with_suffix('.tmp.m4a')
        try:
            subprocess.run([str(ROOT / '.venv/bin/ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-y', '-i', str(target), '-map', '0:a:0', '-ac', '2', '-ar', '44100',
                            '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(temporary)],
                           check=True, capture_output=True, timeout=90)
            temporary.replace(playback)
        finally:
            temporary.unlink(missing_ok=True)
        data['playback'] = playback.name
    temporary = DEFAULT_DIR / 'track.json.tmp'
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.replace(DEFAULT_DIR / 'track.json')
    return target


def playback_audio():
    source, _name = default_audio()
    manifest = DEFAULT_DIR / 'track.json'
    if not (os.environ.get('HYA_DEFAULT_AUDIO') or os.environ.get('HYA_TEST_AUDIO')) and manifest.is_file():
        data = json.loads(manifest.read_text())
        if data.get('playback'):
            playback = DEFAULT_DIR / Path(data['playback']).name
            if playback.is_file():
                return playback
    return source
