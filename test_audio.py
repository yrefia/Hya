import unittest, tempfile, wave, struct, math
from pathlib import Path
from audio_analysis import analyze, RATE
class AnalysisTests(unittest.TestCase):
    def analyze_signal(self,freq):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.wav'
            with wave.open(str(p),'wb') as f:
                f.setparams((1,2,RATE,0,'NONE','not compressed'))
                data=[int(10000*math.sin(2*math.pi*freq*i/RATE)) if freq else 0 for i in range(RATE//4)]
                f.writeframes(struct.pack('<'+'h'*len(data),*data))
            a=analyze(p); self.assertEqual(a,analyze(p));return a
    def test_silence(self):
        a=self.analyze_signal(0);self.assertTrue(all(f['energy']==0 and f['centroid']==0 for f in a['frames']))
    def test_frequency_and_difference(self):
        low=self.analyze_signal(220);high=self.analyze_signal(2200)
        self.assertAlmostEqual(low['frames'][0]['centroid'],220,delta=25)
        self.assertAlmostEqual(high['frames'][0]['centroid'],2200,delta=25)
        self.assertGreater(low['frames'][0]['bands'][0],high['frames'][0]['bands'][0])

class MusicTests(unittest.TestCase):
    def test_polyphonic_tracking_and_silence(self):
        from audio_analysis import WINDOW,fft
        from music_features import voices
        def spectrum(freqs):
            x=[sum(a*math.sin(2*math.pi*hz*i/RATE) for hz,a in freqs)*(.5-.5*math.cos(2*math.pi*i/(WINDOW-1))) for i in range(WINDOW)]
            return [abs(z)**2 for z in fft(x)[:WINDOW//2+1]]
        track=voices(spectrum([(523.25,.4),(130.81,.16),(164.81,.12),(196,.1)]),RATE,WINDOW)
        self.assertAlmostEqual(track[0]['pitch'],72,delta=.6)
        self.assertGreaterEqual(sum(v['pitch'] is not None for v in track),3)
        changed=voices(spectrum([(659.25,.4),(130.81,.16),(164.81,.12),(196,.1)]),RATE,WINDOW,track)
        self.assertAlmostEqual(changed[0]['pitch'],76,delta=.6)
        self.assertTrue(all(v['pitch'] is None for v in voices([0]*1025,RATE,WINDOW)))

if __name__=='__main__':unittest.main()
