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


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(worker, 'ROOT', Path(self.temp.name))
        self.root_patch.start()
    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def request(self):
        return {'job':'restart-regression','kind':'Assembly','payload': {
            'duration':1,'fps':24,'resolution':'1920x1080',
            'shots':[{'source':'video','duration':1}], 'audio':[{'source':'audio'}]}}

    def test_restart_resumes_same_id_and_renders_real_1080p(self):
        root = Path(self.temp.name)
        video, audio = root/'source.mp4', root/'source.wav'
        worker.command(worker.ffmpeg_args()+['-f','lavfi','-i','testsrc2=size=320x240:rate=24','-t','1','-c:v','libx264','-threads','1',str(video)])
        worker.command(worker.ffmpeg_args()+['-f','lavfi','-i','sine=frequency=440:sample_rate=24000','-t','1',str(audio)])
        original = worker.assemble
        def assemble(payload, folder):
            def fetch(url,destination): shutil.copyfile(audio if url=='audio' else video,destination)
            return original(payload,folder,fetch)
        request=self.request()
        with patch.object(worker.POOL,'submit'):
            job=worker.enqueue(request)
            # Input objects are not modified by validation or normalization.
            self.assertNotIn('frames',request['payload']['shots'][0])
            worker.update(job,status='Processing')
        with patch.object(worker,'assemble',side_effect=assemble), patch.object(worker,'notify'), patch.object(worker.POOL,'submit',side_effect=lambda fn,*args:fn(*args)):
            self.assertEqual(worker.recover_jobs(),1)
        state=worker.get_job(job)
        self.assertEqual(state['status'],'Completed')
        data=json.loads(state['result'])
        self.assertEqual((data['frames'],data['fps'],data['width'],data['height']),(24,24,1920,1080))
        self.assertTrue(data['has_audio'])
        with patch.object(worker.POOL,'submit') as submit:
            self.assertEqual(worker.recover_jobs(),0)
            self.assertEqual(worker.enqueue(request),job)
            submit.assert_not_called()
        worker.command(['ffmpeg','-v','error','-i',str(root/job/'output.mp4'),'-f','null','-'])
        (root/job/'output.mp4').unlink()
        worker.recover_jobs()
        self.assertEqual(worker.get_job(job)['status'],'Failed')

    def test_legacy_database_migrates_and_interrupted_jobs_are_explicit(self):
        import sqlite3
        with sqlite3.connect(Path(self.temp.name)/'jobs.sqlite3') as c:
            c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,source_job TEXT,digest TEXT,status TEXT,result TEXT,error TEXT,created REAL,callback_error TEXT)')
            c.execute("INSERT INTO jobs VALUES('legacy','source','hash','Processing','{}','',0,'')")
        self.assertEqual(worker.recover_jobs(),0)
        state=worker.get_job('legacy')
        self.assertEqual(state['status'],'Failed')
        self.assertIn('no saved request',state['error'])
        self.assertIn('request_json',state)

    def test_failed_fixed_callback_is_retried_and_cleared(self):
        import urllib.error
        from unittest.mock import MagicMock
        with patch.object(worker.POOL,'submit'):
            job=worker.enqueue(self.request())
        worker.update(job,status='Failed',error='Test error')
        ok=MagicMock();ok.__enter__.return_value.status=200
        with patch.object(worker,'CALLBACK','https://the-last-repair-studio.bubbleapps.io/version-test/api/1.1/wf/production_webhook'),patch.object(worker,'CALLBACK_TOKEN','test-token'),patch('worker.urllib.request.urlopen',side_effect=[urllib.error.URLError('temporary'),ok]) as send:
            worker.notify(job,self.request(),'Failed',error='Test error')
            state=worker.get_job(job)
            self.assertEqual(state['callback_attempts'],1)
            self.assertTrue(state['callback_error'])
            worker.update(job,callback_next=0)
            self.assertEqual(worker.retry_callbacks(),1)
            state=worker.get_job(job)
            self.assertEqual(state['callback_attempts'],2)
            self.assertEqual(state['callback_error'],'')
            self.assertEqual(state['callback_next'],0)
            self.assertEqual(worker.retry_callbacks(),0)
            self.assertEqual(send.call_count,2)


    def test_authenticated_status_polling_by_bubble_source_id(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from threading import Thread
        from urllib.parse import quote

        source_job = 'episode-two-render'
        original = self.request()
        original['job'] = source_job
        with patch.object(worker.POOL, 'submit'):
            first = worker.enqueue(original)
        (Path(self.temp.name) / first).mkdir()
        (Path(self.temp.name) / first / 'output.mp4').write_bytes(b'fixture')
        worker.update(first, status='Completed', result=json.dumps({
            'duration': 1, 'fps': 24, 'frames': 24,
            'width': 1920, 'height': 1080, 'has_audio': True
        }))

        # A second request with the same stable Bubble job ID is the newest.
        changed = self.request()
        changed['job'] = source_job
        changed['payload']['shots'][0]['caption'] = 'Updated storyboard'
        with patch.object(worker.POOL, 'submit'):
            second = worker.enqueue(changed)
        self.assertNotEqual(first, second)

        with patch.object(worker, 'TOKEN', 'test-private-token'):
            server = ThreadingHTTPServer(('127.0.0.1', 0), worker.Handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'

            def read(path, authenticated=True):
                headers = {'Authorization': 'Bearer test-private-token'} if authenticated else {}
                with urlopen(Request(base + path, headers=headers), timeout=10) as response:
                    return json.load(response)

            try:
                path = '/jobs/latest?source_job=' + quote(source_job)
                with self.assertRaises(HTTPError) as unauthorized:
                    read(path, authenticated=False)
                self.assertEqual(unauthorized.exception.code, 401)
                self.assertEqual(read(path)['job_id'], second)
                self.assertEqual(read(path)['status'], 'Queued')
                self.assertEqual(read('/jobs/' + first)['status'], 'Completed')
                with self.assertRaises(HTTPError) as missing:
                    read('/jobs/latest?source_job=does-not-exist')
                self.assertEqual(missing.exception.code, 404)
                with self.assertRaises(HTTPError) as malformed:
                    read('/jobs/latest')
                self.assertEqual(malformed.exception.code, 422)

                # A vanished output must not be advertised to Bubble.
                (Path(self.temp.name) / first / 'output.mp4').unlink()
                state = read('/jobs/' + first)
                self.assertEqual(state['status'], 'Failed')
                self.assertEqual(state['output'], '')
                self.assertIn('missing', state['error'])
                self.assertEqual(state['source_job'], source_job)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=10)



if __name__ == '__main__':
    unittest.main()
