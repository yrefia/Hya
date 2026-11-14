"""Local-only Python UI server. No third-party dependencies."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import tempfile, subprocess, json, webbrowser, threading, secrets, urllib.parse
from audio_analysis import analyze

TOKEN=secrets.token_urlsafe(24)
ROOT=Path(__file__).parent
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,data,kind='application/json'):
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        if parsed.path=='/' and urllib.parse.parse_qs(parsed.query).get('token')==[TOKEN]:
            self.reply(200,(ROOT/'ui.html').read_bytes(),'text/html; charset=utf-8')
        else:self.reply(404,b'{}')
    def do_POST(self):
        if self.path!='/analyze' or self.headers.get('X-Hya-Token')!=TOKEN:
            self.reply(403,b'{}');return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=32*1024*1024:raise ValueError('请选择小于 32 MB 的音频。')
            body=self.rfile.read(size)
            with tempfile.TemporaryDirectory(prefix='hya-') as folder:
                source=Path(folder)/'input';target=Path(folder)/'audio.wav';source.write_bytes(body)
                conversion=subprocess.run(['/usr/bin/afconvert','-f','WAVE','-d','LEI16@22050','-c','1',str(source),str(target)],capture_output=True,timeout=45)
                if conversion.returncode:raise ValueError('无法解码此音频。请尝试 WAV、MP3、M4A 或 AIFF 文件。')
                result=analyze(target)
            self.reply(200,json.dumps(result).encode())
        except Exception as exc:self.reply(400,json.dumps({'error':str(exc)},ensure_ascii=False).encode())

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}/?token={TOKEN}'
    print('Hya 已启动。关闭本终端或按 Control+C 停止。',flush=True)
    print(url,flush=True)
    threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
