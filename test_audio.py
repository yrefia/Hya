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
if __name__=='__main__':unittest.main()
