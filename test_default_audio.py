"""Default-song copies survive removal of the original; overrides remain explicit."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

import default_audio as defaults


class DefaultAudioTests(unittest.TestCase):
    def test_installed_copy_survives_missing_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / '远方的寂静.mp3'
            source.write_bytes(b'original-audio')
            with patch.object(defaults, 'DEFAULT_DIR', root / 'project'), patch.dict(os.environ, {}, clear=True):
                installed = defaults.install_default(source)
                self.assertEqual(installed.read_bytes(), source.read_bytes())
                source.unlink()
                self.assertEqual(defaults.default_audio(), (installed, '远方的寂静'))
                defaults.install_default(installed)  # Precopied project audio is valid too.
                self.assertEqual(defaults.default_audio(), (installed, '远方的寂静'))

    def test_wav_gets_small_seekable_faststart_playback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'song.wav'
            with wave.open(str(source), 'wb') as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(44100)
                audio.writeframes(b'\0' * 44100 * 4)
            original = source.read_bytes()
            with patch.object(defaults, 'DEFAULT_DIR', root / 'project'), patch.dict(os.environ, {}, clear=True):
                installed = defaults.install_default(source)
                playback = defaults.playback_audio()
                self.assertEqual(installed.read_bytes(), original)
                self.assertEqual(playback.suffix, '.m4a')
                body = playback.read_bytes()
                self.assertLess(len(body), len(original))
                self.assertLess(body.index(b'moov'), body.index(b'mdat'))

    def test_explicit_override_and_missing_override(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'override.wav'
            source.write_bytes(b'override')
            with patch.dict(os.environ, {'HYA_DEFAULT_AUDIO': str(source)}):
                self.assertEqual(defaults.default_audio(), (source, 'override'))
                source.unlink()
                with self.assertRaises(FileNotFoundError):
                    defaults.default_audio()

    def test_desktop_discovery_ignores_non_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            desktop = root / 'Desktop'
            desktop.mkdir()
            (desktop / 'My heart will go on.txt').write_text('not audio')
            source = desktop / 'Celine Dion - My Heart Will Go On.mp3'
            source.write_bytes(b'audio')
            with patch.object(defaults, 'DEFAULT_DIR', root / 'unconfigured'), patch.object(Path, 'home', return_value=root), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(defaults.default_audio(), (source, source.stem))


if __name__ == '__main__':
    unittest.main()
