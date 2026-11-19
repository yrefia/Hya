import unittest

from hya.rubia import PROFILES, STEP, estimate

try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None, 'audio environment required')
class RubiaTests(unittest.TestCase):
    def test_chord_attack_over_decay_and_silence(self):
        t = np.arange(44100) / 44100
        signal = .4*np.exp(-2*t)*np.sin(2*np.pi*220*t)
        signal += .2*np.sin(2*np.pi*277.18*t)*(t >= .3)
        signal[t >= .8] = 0
        stereo = np.column_stack((signal, -signal))
        for name, (limit, _, _, bend, _) in PROFILES.items():
            notes = estimate(stereo, name)['notes']
            chord = [n['pitch'] for n in notes if n['start'] <= .5 < n['end']]
            if name == 'vocals':
                self.assertEqual(len(chord), 1)
            else:
                self.assertCountEqual(chord, [57, 61])
                attack = next(n for n in notes if n['pitch'] == 61)
                self.assertAlmostEqual(attack['start'], .3, delta=.061)
            for note in notes:
                self.assertLessEqual(note['end'], .82)
                self.assertEqual(len(note['samples']), round((note['end']-note['start'])/STEP))
                self.assertTrue(all(abs(p-note['pitch']) <= bend+.001 for p in note['samples']))
            for time in np.arange(0, 1, STEP):
                self.assertLessEqual(sum(n['start'] <= time < n['end'] for n in notes), limit)
