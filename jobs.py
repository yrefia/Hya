"""Bounded local analysis jobs; isolated ML workers and versioned result cache."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import os
import secrets
import signal
import subprocess
import tempfile
import threading
import time
from ml_pipeline import VERSION, STEMS, PITCHED

ROOT = Path(__file__).resolve().parent
TERMINAL = {'done', 'error', 'cancelled'}


def valid_result(data):
    """Old/partial results must never satisfy a six-track cache request."""
    if not isinstance(data, dict) or data.get('version') != VERSION or data.get('duration', 0) <= 0:
        return False
    tracks = data.get('tracks')
    return (isinstance(tracks, dict) and set(tracks) == set(STEMS)
            and isinstance(data.get('frames'), list)
            and all(isinstance(tracks[name], dict) and isinstance(tracks[name].get('frames'), list)
                    for name in STEMS)
            and all(isinstance(tracks[name].get('notes'), list) for name in PITCHED)
            and isinstance(tracks['drums'].get('onsets'), list))


class JobManager:
    def __init__(self, root=ROOT, cache=None, command=None, timeout=1800):
        self.root = Path(root)
        self.cache = Path(cache or self.root / 'outputs' / 'cache')
        self.command = command or [str(self.root / '.venv/bin/python'), str(self.root / 'ml_pipeline.py')]
        self.timeout = timeout
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hya-analysis')
        self.jobs = {}
        self.closed = False
        signature = hashlib.sha256(b'hya-cache-v1')
        for name in ('ml_pipeline.py', 'requirements-audio.lock.txt'):
            path = self.root / name
            if path.exists():
                signature.update(path.read_bytes())
        for path in sorted((self.root / '.models/audio-separator').glob('*')):
            if path.suffix in {'.th', '.yaml', '.safetensors'}:
                signature.update(path.name.encode())
                signature.update(path.read_bytes())
        self.signature = signature.digest()

    def snapshot(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            return {key: job[key] for key in ('id', 'state', 'stage', 'progress', 'message', 'cached', 'error') if key in job}

    def cached_result(self, source):
        """Read a prepared result without queueing work or uploading audio."""
        digest = hashlib.sha256(self.signature)
        with Path(source).open('rb') as audio:
            for chunk in iter(lambda: audio.read(1024 * 1024), b''):
                digest.update(chunk)
        path = self.cache / (digest.hexdigest() + '.json')
        try:
            body = path.read_bytes()
            if valid_result(json.loads(body)):
                return body
        except (OSError, ValueError, TypeError, KeyError):
            pass
        raise ValueError('默认曲目的六轨缓存缺失或已过期，请在电脑上运行 precache.py；音频仍可播放。')

    def submit(self, body):
        digest = hashlib.sha256(self.signature + body).hexdigest()
        with self.lock:
            if self.closed:
                raise ValueError('服务正在关闭。')
            if sum(j['state'] not in TERMINAL for j in self.jobs.values()) >= 4:
                raise ValueError('任务队列已满，请等待当前分析完成。')
            for key, job in list(self.jobs.items()):
                if len(self.jobs) < 32:
                    break
                if job['state'] in TERMINAL:
                    del self.jobs[key]
            job_id = secrets.token_hex(16)
            self.cache.mkdir(parents=True, exist_ok=True)
            result = self.cache / (digest + '.json')
            valid = False
            if result.exists():
                try:
                    parsed = json.loads(result.read_text())
                    valid = valid_result(parsed)
                except (ValueError, KeyError, OSError, TypeError):
                    pass
            job = dict(id=job_id, state='done' if valid else 'queued', stage='done' if valid else 'queued',
                       progress=1 if valid else 0, message='已载入缓存' if valid else '等待分析', cached=valid,
                       result=result, cancel=threading.Event(), process=None)
            self.jobs[job_id] = job
            if not valid:
                folder = tempfile.TemporaryDirectory(prefix='hya-job-')
                job['folder'] = folder
                try:
                    (Path(folder.name) / 'input').write_bytes(body)
                    job['future'] = self.executor.submit(self._run, job)
                except Exception:
                    folder.cleanup()
                    del self.jobs[job_id]
                    raise
            return self.snapshot(job_id)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job['state'] not in TERMINAL:
                job['cancel'].set()
                job.update(state='cancelled', stage='cancelled', message='分析已取消')
                future = job.get('future')
                if future is not None and future.cancel():
                    job['folder'].cleanup()
            return self.snapshot(job_id)

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass

    def _run(self, job):
        folder = Path(job['folder'].name)
        process = None
        try:
            with self.lock:
                if job['cancel'].is_set():
                    return
                job.update(state='running', stage='starting', message='启动本机分析模型')
            env = os.environ.copy()
            env.update(TORCH_HOME=str(self.root / '.models/torch'), PYTHONUNBUFFERED='1',
                       NUMBA_CACHE_DIR=str(folder / 'numba'), MPLCONFIGDIR=str(folder / 'matplotlib'))
            output = folder / 'result.json'
            with (folder / 'worker.log').open('w+') as log:
                process = subprocess.Popen(self.command + [str(folder / 'input'), str(output)],
                                           stdout=log, stderr=subprocess.STDOUT, cwd=self.root,
                                           env=env, start_new_session=True)
                job['process'] = process
                began = time.monotonic()
                with (folder / 'worker.log').open() as reader:
                    while True:
                        for line in reader:
                            try:
                                update = json.loads(line)
                            except ValueError:
                                continue
                            if isinstance(update, dict) and 'stage' in update:
                                with self.lock:
                                    if not job['cancel'].is_set():
                                        job.update({k: update[k] for k in ('stage', 'message', 'progress') if k in update})
                        if job['cancel'].is_set():
                            self._stop(process)
                            return
                        if time.monotonic() - began > self.timeout:
                            self._stop(process)
                            raise ValueError('分析超时，请裁剪音频后重试。')
                        if process.poll() is not None:
                            break
                        time.sleep(.1)
            if process.returncode:
                detail = (folder / 'worker.log').read_text(errors='replace')[-2000:]
                # The worker's explicit error is readable; import failures retain a useful tail.
                message = detail.strip().splitlines()[-1] if detail.strip() else '模型分析失败'
                try:
                    message = json.loads(message).get('error', message)
                except ValueError:
                    pass
                raise ValueError(message)
            data = json.loads(output.read_text())
            if not valid_result(data):
                raise ValueError('分析结果不完整，请重试。')
            with self.lock:
                if job['cancel'].is_set():
                    return
                # Atomic publish: interrupted jobs never leave a valid-looking cache entry.
                temporary = job['result'].with_suffix('.tmp')
                temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False))
                temporary.replace(job['result'])
                job.update(state='done', stage='done', progress=1, message='分析完成')
        except Exception as exc:
            with self.lock:
                if not job['cancel'].is_set():
                    message = str(exc)
                    if isinstance(exc, FileNotFoundError):
                        message = '缺少模型运行环境或输出。请检查 .venv 与 AUDIO_TOOLS.md，或切换快速分析。'
                    job.update(state='error', stage='error', message='分析失败', error=message)
        finally:
            if process is not None:
                self._stop(process)
            job['process'] = None
            job['folder'].cleanup()

    def result(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job['state'] != 'done':
                raise ValueError('分析结果尚未就绪。')
            return job['result'].read_bytes()

    def close(self):
        with self.lock:
            self.closed = True
            for job_id in self.jobs:
                self.cancel(job_id)
        self.executor.shutdown(wait=True)
