"""Local-only UI server. ML runs in a separate project-venv process."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import os
import tempfile
import subprocess
import json
import webbrowser
import threading
import secrets
import urllib.parse
from audio_analysis import analyze
from jobs import JobManager

TOKEN = secrets.token_urlsafe(24)
ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 128 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, data, kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, code, data):
        self.reply(code, json.dumps(data, ensure_ascii=False).encode())

    def authorized(self):
        return self.headers.get('X-Hya-Token') == TOKEN

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query_token = urllib.parse.parse_qs(parsed.query).get('token') == [TOKEN]
        if parsed.path == '/' and query_token:
            self.reply(200, (ROOT / 'ui.html').read_bytes(), 'text/html; charset=utf-8')
        elif parsed.path == '/sample' and query_token:
            sample = os.environ.get('HYA_TEST_AUDIO')
            if sample and Path(sample).is_file():
                self.reply(200, Path(sample).read_bytes(), 'application/octet-stream')
            else:
                self.json(404, {'error': '请设置 HYA_TEST_AUDIO 或导入音频。'})
        elif parsed.path.startswith('/jobs/'):
            if not self.authorized():
                self.json(403, {'error': '会话无效，请从启动地址重新打开。'})
                return
            parts = parsed.path.strip('/').split('/')
            try:
                if len(parts) == 2:
                    self.json(200, self.server.jobs.snapshot(parts[1]))
                elif len(parts) == 3 and parts[2] == 'result':
                    self.reply(200, self.server.jobs.result(parts[1]))
                else:
                    self.json(404, {'error': '接口不存在。'})
            except KeyError:
                self.json(404, {'error': '任务不存在，请重新导入音频。'})
            except ValueError as exc:
                self.json(409, {'error': str(exc)})
        else:
            self.json(404, {'error': '页面不存在。'})

    def do_POST(self):
        if not self.authorized():
            self.json(403, {'error': '会话无效，请从启动地址重新打开。'})
            return
        if self.path not in ('/jobs', '/analyze'):
            self.json(404, {'error': '接口不存在。'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_UPLOAD:
                raise ValueError('请选择非空且不大于 128 MB 的音频。')
            self.connection.settimeout(60)
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError('音频上传不完整。')
            if self.path == '/jobs':
                self.json(202, self.server.jobs.submit(body))
                return
            with tempfile.TemporaryDirectory(prefix='hya-') as folder:
                source = Path(folder) / 'input'
                target = Path(folder) / 'audio.wav'
                source.write_bytes(body)
                conversion = subprocess.run(['/usr/bin/afconvert', '-f', 'WAVE', '-d', 'LEI16@22050',
                                             '-c', '1', str(source), str(target)], capture_output=True, timeout=45)
                if conversion.returncode:
                    raise ValueError('无法解码此音频。请尝试 WAV、MP3、M4A 或 AIFF 文件。')
                result = analyze(target)
            self.json(200, result)
        except Exception as exc:
            self.json(400, {'error': str(exc)})

    def do_DELETE(self):
        if not self.authorized():
            self.json(403, {'error': '会话无效。'})
            return
        parts = self.path.strip('/').split('/')
        if len(parts) != 2 or parts[0] != 'jobs':
            self.json(404, {'error': '接口不存在。'})
            return
        try:
            self.json(200, self.server.jobs.cancel(parts[1]))
        except KeyError:
            self.json(404, {'error': '任务不存在。'})


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.jobs = JobManager()
    url = f'http://127.0.0.1:{server.server_port}/?token={TOKEN}'
    print('Hya 已启动。关闭本终端或按 Control+C 停止。', flush=True)
    print(url, flush=True)
    threading.Timer(.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.jobs.close()


if __name__ == '__main__':
    main()
