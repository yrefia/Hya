"""Signal-level checks, independent of model downloads and inference time."""
import math
import unittest

try:
    import numpy as np
except ImportError:
    np = None

from ml_pipeline import RATE, acoustic_frames, clean_notes, drum_onsets


@unittest.skipIf(np is None, 'run with .venv/bin/python for audio dependencies')
class FeatureTests(unittest.TestCase):
    def test_antiphase_stereo_keeps_energy_and_frequency(self):
        t = np.arange(RATE // 2) / RATE
        tone = .2 * np.sin(2 * np.pi * 440 * t)
        frames = acoustic_frames(np.stack((tone, -tone), axis=1))
        self.assertAlmostEqual(frames[0]['rms'], .2 / math.sqrt(2), delta=.002)
        self.assertAlmostEqual(frames[0]['centroid'], 440, delta=5)
        self.assertTrue(all(0 <= frame['energy'] <= 1 for frame in frames))
        self.assertTrue(all(0 <= frame['t'] <= .5 for frame in frames))

    def test_silence_has_no_features_or_onsets(self):
        silence = np.zeros((RATE, 2))
        self.assertTrue(all(frame['rms'] == frame['energy'] == frame['centroid'] == 0
                            for frame in acoustic_frames(silence)))
        self.assertEqual(drum_onsets(silence), [])

    def test_transients_follow_input_times(self):
        signal = np.zeros(RATE * 2)
        rng = np.random.default_rng(4)
        for onset in (.4, 1.2):
            index = int(onset * RATE)
            n = int(.08 * RATE)
            signal[index:index+n] = rng.standard_normal(n) * np.exp(-np.arange(n) / 500)
        onsets = drum_onsets(signal)
        self.assertEqual(len(onsets), 2)
        for event, expected in zip(onsets, (.4, 1.2)):
            self.assertAlmostEqual(event['t'], expected, delta=.03)

    def test_notes_clamp_to_source_timeline_and_reject_nan(self):
        notes = clean_notes([(-.1, .3, 60, .8, None), (.8, 2., 64, 2., None),
                             (2., 3., 60, .3, None), (0., .4, 60, float('nan'), None)], 1.)
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0]['start'], 0)
        self.assertEqual(notes[1]['end'], 1)
        self.assertEqual(notes[1]['amplitude'], 1)


if __name__ == '__main__':
    unittest.main()
