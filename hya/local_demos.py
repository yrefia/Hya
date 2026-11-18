"""The local recordings offered in Hya's demo picker."""
from .default_audio import ROOT

INPUT_DIR = ROOT / 'inputs'
PLAYBACK_DIR = ROOT / 'outputs' / 'demos'
TRACKS = {
    'rubia': ('周深-Rubia.flac', '周深 · Rubia', False),
    'with-all-my-heart': ('ILLENIUM,JVKE-With All My Heart.flac', 'ILLENIUM、JVKE · With All My Heart', False),
    'million-days': ('SABAI,Hoang,Ridgely-Million Days.flac', 'SABAI、Hoang、Ridgely · Million Days', False),
    'million-days-acoustic': ('SABAI,Hoang,Ridgely-Million Days (Acoustic).flac', 'SABAI、Hoang、Ridgely · Million Days (Acoustic)', False),
    'distant-silence': ('林海-远方的寂静.flac', '林海 · 远方的寂静', True),
}


def playback_path(source):
    return PLAYBACK_DIR / (source.stem + '.playback.m4a')


def available_tracks():
    return [{'id': track_id, 'name': name} for track_id, (filename, name, _) in TRACKS.items()
            if (INPUT_DIR / filename).is_file() and playback_path(INPUT_DIR / filename).is_file()]
