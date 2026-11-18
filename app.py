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
import mimetypes
import gzip
import re
from hya.audio_analysis import analyze
from hya.jobs import JobManager
from hya.default_audio import default_audio, default_option, default_piano_solo, playback_audio
from hya import local_demos, rubia

TOKEN = secrets.token_urlsafe(24)
ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 128 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, data, kind='application/json'):
        compressed = (kind == 'application/json' and len(data) > 1024
                      and re.search(r'(?:^|,)\s*gzip\s*(?:,|$)', self.headers.get('Accept-Encoding', '')))
        if compressed:
            data = gzip.compress(data, compresslevel=5)
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Vary', 'Accept-Encoding')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        try:
            if self.command != 'HEAD':
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, code, data):
        self.reply(code, json.dumps(data, ensure_ascii=False).encode())

    def authorized(self):
        return self.headers.get('X-Hya-Token') == TOKEN

    def media(self, path):
        """Serve seekable audio without buffering the entire file in memory."""
        with path.open('rb') as audio:
            stat = os.fstat(audio.fileno())
            size = stat.st_size
            etag = f'"{stat.st_mtime_ns:x}-{size:x}"'
            start, end, code = 0, size - 1, 200
            requested = self.headers.get('Range') if self.command != 'HEAD' else None
            if self.headers.get('If-Range', etag) != etag:
                requested = None
            if self.headers.get('If-None-Match') == etag and not requested:
                self.send_response(304)
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'private, max-age=0, must-revalidate')
                self.end_headers()
                return
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                # Unsupported/multiple ranges are ignored, as allowed by HTTP.
                if match and any(match.groups()):
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        start = max(0, size - int(last))
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    code = 206
            self.send_response(code)
            self.send_header('Content-Type', 'audio/mp4' if path.suffix.lower() == '.m4a'
                             else mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', 'private, max-age=0, must-revalidate')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if code == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            audio.seek(start)
            remaining = end - start + 1
            try:
                while remaining > 0:
                    chunk = audio.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def local_demo(self, path):
        if path == '/demo-tracks':
            self.json(200, local_demos.available_tracks())
            return
        parts = path.split('/')
        if len(parts) != 4 or parts[2] not in local_demos.TRACKS or parts[3] not in ('audio', 'result'):
            self.json(404, {'error': '演示曲目不存在。'})
            return
        filename, _, piano_solo = local_demos.TRACKS[parts[2]]
        source = local_demos.INPUT_DIR / filename
        if not source.is_file():
            self.json(404, {'error': '本机演示曲目的原始音频缺失。'})
            return
        try:
            if parts[3] == 'audio':
                self.media(local_demos.playback_path(source))
            else:
                background = self.server.jobs.cached_result(source, piano_solo=piano_solo)
                if parts[2] == 'rubia':
                    background = rubia.cached_result(self.server.jobs.cache, background)
                self.reply(200, background)
        except OSError:
            self.json(404, {'error': '演示曲目的本地文件缺失。'})
        except ValueError:
            self.json(409, {'error': '演示曲目的缓存缺失或已过期，请在电脑上运行 precache.py --demos。'})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query_token = urllib.parse.parse_qs(parsed.query).get('token') == [TOKEN]
        if parsed.path == '/' and query_token:
            self.reply(200, (ROOT / 'web' / 'ui.html').read_bytes(), 'text/html; charset=utf-8')
        elif parsed.path == '/assets/moonlit-lake.jpg':
            self.reply(200, (ROOT / 'assets' / 'moonlit-lake.jpg').read_bytes(), 'image/jpeg')
        elif parsed.path == '/demo-tracks' or parsed.path.startswith('/demo-tracks/'):
            if not (self.authorized() or query_token):
                self.json(403, {'error': '会话无效，请从启动地址重新打开。'})
                return
            self.local_demo(parsed.path)
        elif parsed.path in {f'/demos/{name}.{extension}'
                             for name in ('pure', 'louder-bass') for extension in ('wav', 'json')}:
            if not (self.authorized() or query_token):
                self.json(403, {'error': '会话无效，请从启动地址重新打开。'})
                return
            path = ROOT / 'assets' / 'demos' / parsed.path.rsplit('/', 1)[1]
            try:
                if path.suffix == '.wav':
                    self.media(path)
                else:
                    self.reply(200, path.read_bytes())
            except OSError:
                self.json(404, {'error': '标准示范文件缺失，请重新生成。'})
        elif parsed.path in ('/default', '/default/result', '/sample'):
            if not (self.authorized() or query_token):
                self.json(403, {'error': '会话无效，请从启动地址重新打开。'})
                return
            try:
                sample, name = default_audio()
                if sample.stat().st_size > MAX_UPLOAD:
                    raise ValueError('默认曲目超过 128 MB。')
                if parsed.path == '/default':
                    self.json(200, {'name': name, 'playback': playback_audio() != sample})
                elif parsed.path == '/default/result':
                    try:
                        result = self.server.jobs.cached_result(sample, piano_solo=default_piano_solo(sample))
                        if default_option(sample, 'rubia'):
                            result = rubia.cached_result(self.server.jobs.cache, result)
                        self.reply(200, result)
                    except ValueError as exc:
                        self.json(409, {'error': str(exc)})
                else:
                    if urllib.parse.parse_qs(parsed.query).get('playback') == ['1']:
                        sample = playback_audio()
                    self.media(sample)
            except (OSError, ValueError, KeyError) as exc:
                self.json(404, {'error': str(exc)})
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
