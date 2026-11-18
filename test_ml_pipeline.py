"""Signal-level checks, independent of model downloads and inference time."""
import math
import unittest

try:
    import numpy as np
except ImportError:
    np = None

from ml_pipeline import PITCHED, RATE, acoustic_frames, clean_notes, drum_onsets, screen_drum_onsets, screen_notes


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

    def test_weak_duplicate_is_flagged_but_independent_attack_survives(self):
        def frames(levels):
            return [dict(t=i * .05, rms=level) for i, level in enumerate(levels)]
        piano = [.1, .08, .06, .04, .02, .01, .05]
        note = dict(start=0, end=.3, pitch=60, amplitude=.5)
        tracks = {name: dict(notes=[], frames=frames([0] * len(piano))) for name in PITCHED}
        tracks['piano'] = dict(notes=[note], frames=frames(piano))
        tracks['vocals'] = dict(notes=[note], frames=frames([.01 * level for level in piano]))
        tracks['guitar'] = dict(notes=[{**note, 'pitch': 72}], frames=frames([0, 0, 0, .01, 0, 0, 0]))
        screen_notes(frames(piano), tracks)
        self.assertEqual(tracks['vocals']['notes'], [])
        self.assertEqual(tracks['vocals']['note_candidates'][0]['status'], 'suspected_bleed')
        self.assertEqual(len(tracks['guitar']['notes']), 1)

    def test_drum_screen_uses_local_mix_and_absolute_level(self):
        mix = np.full(RATE, .1)
        drums = np.full(RATE, .0001)
        drums[RATE // 2:RATE // 2 + RATE // 50] = .005
        faint, hit = dict(t=.25, strength=1), dict(t=.5, strength=.2)
        kept, candidates = screen_drum_onsets([faint, hit], drums, mix)
        self.assertEqual(kept, [hit])
        self.assertEqual(candidates, [{**faint, 'status': 'insufficient_evidence'}])


if __name__ == '__main__':
    unittest.main()
