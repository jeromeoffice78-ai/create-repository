import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import worker


class ManifestTests(unittest.TestCase):
    def base(self):
        return {'duration': 2, 'fps': 24, 'resolution': '1280x720',
                'shots': [{'source': 'https://media.cdn.bubble.io/a.mp4', 'duration': 1, 'start': 0},
                          {'source': 'https://media.cdn.bubble.io/b.mp4', 'duration': 1, 'start': 1}],
                'audio': [{'source': 'https://media.cdn.bubble.io/a.wav', 'gain': .5}]}

    def test_rejects_missing_footage_and_runtime_mismatch(self):
        for mutation in ('missing', 'runtime', 'gap', 'transition', 'nan'):
            m = self.base()
            if mutation == 'missing': m['shots'][0]['source'] = ''
            elif mutation == 'runtime': m['duration'] = 3
            elif mutation == 'gap': m['shots'][1]['start'] = 1.5
            elif mutation == 'transition': m['shots'][0]['transition'] = 'dissolve'
            else: m['shots'][0]['duration'] = float('nan')
            with self.subTest(mutation=mutation), self.assertRaises(worker.MediaError):
                worker.manifest(m)

    def test_actual_bubble_text_manifest(self):
        text = ('Target: 2 seconds, 24 fps, 1080p\nSHOTS\n'
                'shot=one | position=1 | start=0 | duration=1 | trim=0..1 | transition=Cut | source=https://media.cdn.bubble.io/one.mp4 | caption=One | caption_start=0 | caption_end=1\n'
                'shot=two | position=2 | start=1 | duration=1 | trim=0..1 | transition=Cut | source=https://media.cdn.bubble.io/two.mp4 | caption=Two | caption_start=0 | caption_end=1\nAUDIO\n'
                'track=a | start=0 | trim=0..2 | gain=1 | source=https://media.cdn.bubble.io/test.wav')
        m = worker.manifest(text)
        self.assertEqual((m['frames'], m['width'], m['height']), (48, 1920, 1080))
        self.assertEqual(m['shots'][1]['caption'], 'Two')
        self.assertEqual(m['audio'][0]['gain'], 1)

    def test_download_guards(self):
        for url in ['file:///etc/passwd', 'http://localhost/a', 'https://127.0.0.1/a',
                    'https://user:password@media.cdn.bubble.io/a', 'https://evil.invalid/a']:
            with self.subTest(url=url), self.assertRaises(worker.MediaError):
                worker.safe_url(url)
        with patch('worker.socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(worker.MediaError):
                worker.safe_url('https://media.cdn.bubble.io/a')


class RenderTests(unittest.TestCase):
    def test_real_two_shot_render_and_audio_mix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / 'input.mp4'
            sound = root / 'input.wav'
            worker.command(worker.ffmpeg_args() + ['-f','lavfi','-i','testsrc2=size=320x240:rate=24',
                '-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(video)])
            worker.command(worker.ffmpeg_args() + ['-f','lavfi','-i','sine=frequency=440:sample_rate=24000',
                '-t','2',str(sound)])
            def fetch(url, destination):
                shutil.copyfile(sound if url == 'audio' else video, destination)
            m = {'duration': 2, 'fps': 24, 'resolution': '320x240',
                 'shots': [{'source': 'video', 'duration':1, 'start':0, 'trim_in':0,
                            'caption':'Verification: first shot', 'caption_end':1},
                           {'source':'video','duration':1,'start':1,'trim_in':1}],
                 'audio': [{'source':'audio','gain':.5,'start':0,'trim_in':0,'trim_out':2}]}
            output_dir = root / 'job'
            output_dir.mkdir()
            path, data = worker.assemble(copy.deepcopy(m), output_dir, fetch)
            self.assertTrue(path.is_file())
            self.assertEqual(data['frames'], 48)
            self.assertEqual(data['fps'], 24)
            self.assertTrue(data['has_audio'])
            self.assertLess(abs(data['duration'] - 2), .06)
            # The normalized footage is independently decodable.
            worker.command(['ffmpeg','-v','error','-i',str(path),'-f','null','-'])

    def test_rejects_short_source_without_padding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / 'input.mp4'
            worker.command(worker.ffmpeg_args() + ['-f','lavfi','-i','color=size=320x240:rate=24',
                '-t','0.5','-c:v','libx264',str(video)])
            m = {'duration': 2,'fps':24,'resolution':'320x240','shots':[{'source':'video','duration':2}], 'allow_silent':True}
            with self.assertRaises(worker.MediaError):
                worker.assemble(m, root, lambda url,dest: shutil.copyfile(video,dest))


if __name__ == '__main__':
    unittest.main()
