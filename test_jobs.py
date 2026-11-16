"""Exercise job/process lifecycle and HTTP contract without loading ML models."""
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

import app
from jobs import JobManager, TERMINAL


WORKER = '''import json, pathlib, sys, time
source, output = map(pathlib.Path, sys.argv[1:])
mode = source.read_text()
print(json.dumps(dict(stage="separating", message="working", progress=.25)), flush=True)
if mode == "wait":
    time.sleep(30)
if mode == "fail":
    print(json.dumps(dict(error="fixture decode failure")), flush=True)
    sys.exit(1)
if mode == "invalid":
    output.write_text("{}")
else:
    output.write_text(json.dumps(dict(version="hya-ml-1", duration=1.0, tracks=dict(vocals=dict(notes=[])), frames=[])))
'''


class JobFixture:
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='hya-test-')
        self.root = Path(self.folder.name)
        self.worker = self.root / 'worker.py'
        self.worker.write_text(WORKER)
        self.managers = []
        self.manager = self.make_manager()

    def make_manager(self, **kwargs):
        manager = JobManager(root=self.root, command=[sys.executable, str(self.worker)], **kwargs)
        self.managers.append(manager)
        return manager

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.folder.cleanup()

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.02)
        self.fail('Timed out waiting for job lifecycle transition')

    def terminal(self, job):
        return self.wait_for(lambda: (s if s['state'] in TERMINAL else None)
                             if (s := self.manager.snapshot(job['id'])) else None)


class JobTests(JobFixture, unittest.TestCase):
    def test_success_progress_cache_and_cleanup(self):
        job = self.manager.submit(b'wait')
        self.wait_for(lambda: self.manager.snapshot(job['id'])['stage'] == 'separating')
        self.assertEqual(self.manager.snapshot(job['id'])['progress'], .25)
        self.manager.cancel(job['id'])
        success = self.manager.submit(b'ok')
        state = self.terminal(success)
        self.assertEqual(state['state'], 'done')
        self.assertEqual(state['progress'], 1)
        result = json.loads(self.manager.result(success['id']))
        self.assertEqual(result['duration'], 1)
        folder = Path(self.manager.jobs[success['id']]['folder'].name)
        self.wait_for(lambda: not folder.exists())
        cached = self.manager.submit(b'ok')
        self.assertEqual(cached['state'], 'done')
        self.assertTrue(cached['cached'])
        self.assertEqual(self.manager.result(cached['id']), self.manager.result(success['id']))
        self.assertNotIn('result', cached)
        self.assertNotIn('process', cached)

    def test_source_change_invalidates_cache(self):
        first = self.manager.submit(b'ok')
        self.assertEqual(self.terminal(first)['state'], 'done')
        (self.root / 'ml_pipeline.py').write_text('# new model settings')
        new = self.make_manager()
        self.assertNotEqual(new.signature, self.manager.signature)
        self.assertFalse(new.submit(b'ok')['cached'])

    def test_corrupt_cache_recomputed(self):
        first = self.manager.submit(b'ok')
        self.terminal(first)
        cache = self.manager.jobs[first['id']]['result']
        cache.write_text('{incomplete')
        second = self.manager.submit(b'ok')
        self.assertFalse(second['cached'])
        self.assertEqual(self.terminal(second)['state'], 'done')

    def test_empty_tracks_cache_recomputed(self):
        first = self.manager.submit(b'ok')
        self.terminal(first)
        cache = self.manager.jobs[first['id']]['result']
        cache.write_text(json.dumps(dict(version='hya-ml-1', duration=1, tracks={})))
        second = self.manager.submit(b'ok')
        self.assertFalse(second['cached'])
        self.assertEqual(self.terminal(second)['state'], 'done')

    def test_worker_error_and_invalid_output_are_not_cached(self):
        for body, expected in ((b'fail', 'fixture decode failure'), (b'invalid', '分析结果不完整')):
            with self.subTest(body=body):
                job = self.manager.submit(body)
                state = self.terminal(job)
                self.assertEqual(state['state'], 'error')
                self.assertIn(expected, state['error'])
                self.assertFalse(self.manager.jobs[job['id']]['result'].exists())
                with self.assertRaises(ValueError):
                    self.manager.result(job['id'])

    def test_cancel_running_and_queued_cleans_uploads(self):
        running = self.manager.submit(b'wait')
        self.wait_for(lambda: self.manager.snapshot(running['id'])['stage'] == 'separating')
        queued = self.manager.submit(b'ok')
        self.assertEqual(queued['state'], 'queued')
        folders = [Path(self.manager.jobs[j['id']]['folder'].name) for j in (running, queued)]
        self.assertEqual(self.manager.cancel(queued['id'])['state'], 'cancelled')
        self.assertFalse(folders[1].exists(), 'Queued cancellation must immediately release upload storage')
        self.assertEqual(self.manager.cancel(running['id'])['state'], 'cancelled')
        for folder in folders:
            self.wait_for(lambda: not folder.exists())
        for job in (running, queued):
            self.assertFalse(self.manager.jobs[job['id']]['result'].exists())
            self.assertIsNone(self.manager.jobs[job['id']]['process'])

    def test_queue_limit_and_close(self):
        self.manager.submit(b'wait')
        for index in range(3):
            self.manager.submit(('queued-' + str(index)).encode())
        with self.assertRaisesRegex(ValueError, '队列已满'):
            self.manager.submit(b'excess')
        self.manager.close()
        with self.assertRaisesRegex(ValueError, '关闭'):
            self.manager.submit(b'closed')

    def test_timeout_terminates_process(self):
        self.manager.timeout = .2
        job = self.manager.submit(b'wait')
        state = self.terminal(job)
        self.assertEqual(state['state'], 'error')
        self.assertIn('超时', state['error'])
        self.wait_for(lambda: self.manager.jobs[job['id']]['process'] is None)

    def test_unknown_and_pending_result(self):
        with self.assertRaises(KeyError):
            self.manager.snapshot('missing')
        job = self.manager.submit(b'wait')
        with self.assertRaises(ValueError):
            self.manager.result(job['id'])


class HTTPTests(JobFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server.daemon_threads = True
        self.server.jobs = self.manager
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, path, body=None, authorized=True, extra=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'X-Hya-Token': app.TOKEN} if authorized else {}
        headers.update(extra or {})
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        payload = response.read()
        status = response.status
        connection.close()
        return status, json.loads(payload)

    def test_http_authorization_and_routes(self):
        for method, path, body in (('POST', '/jobs', b'ok'), ('GET', '/jobs/missing', None),
                                   ('GET', '/jobs/missing/result', None), ('DELETE', '/jobs/missing', None)):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path, body, authorized=False)[0], 403)
        for method, path in (('GET', '/jobs/missing'), ('DELETE', '/jobs/missing'),
                             ('POST', '/unknown'), ('GET', '/jobs/id/unknown')):
            self.assertEqual(self.request(method, path)[0], 404)

    def test_http_submit_poll_result_cancel_and_cached(self):
        code, job = self.request('POST', '/jobs', b'wait')
        self.assertEqual(code, 202)
        self.assertEqual(self.request('GET', '/jobs/' + job['id'] + '/result')[0], 409)
        self.assertEqual(self.request('GET', '/jobs/' + job['id'])[0], 200)
        self.assertEqual(self.request('DELETE', '/jobs/' + job['id'])[1]['state'], 'cancelled')
        _, success = self.request('POST', '/jobs', b'ok')
        self.assertEqual(self.terminal(success)['state'], 'done')
        code, result = self.request('GET', '/jobs/' + success['id'] + '/result')
        self.assertEqual(code, 200)
        self.assertEqual(result['version'], 'hya-ml-1')
        self.assertTrue(self.request('POST', '/jobs', b'ok')[1]['cached'])

    def test_http_empty_and_oversize_upload(self):
        self.assertEqual(self.request('POST', '/jobs', b'')[0], 400)
        self.assertEqual(self.request('POST', '/jobs', b'', extra={'Content-Length': str(app.MAX_UPLOAD + 1)})[0], 400)
        self.assertEqual(self.request('POST', '/jobs', b'', extra={'Content-Length': 'broken'})[0], 400)

    def test_http_truncated_upload(self):
        with socket.create_connection(('127.0.0.1', self.server.server_port), timeout=3) as sock:
            request = ('POST /jobs HTTP/1.0\r\nHost: localhost\r\nX-Hya-Token: ' + app.TOKEN +
                       '\r\nContent-Length: 20\r\n\r\nshort').encode()
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            received = bytearray()
            while chunk := sock.recv(4096):
                received.extend(chunk)
        self.assertIn(b'400 Bad Request', received)
        self.assertIn('上传不完整', received.decode())


if __name__ == '__main__':
    unittest.main()
