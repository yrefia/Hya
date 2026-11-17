"""Analyze a song once, then install it as the default only after success."""
import argparse
from pathlib import Path
import time

from default_audio import default_audio, install_default
from jobs import JobManager, TERMINAL


def main():
    parser = argparse.ArgumentParser(description='预缓存并设置 Hya 默认曲目')
    parser.add_argument('audio', nargs='?', type=Path, help='省略时查找当前默认曲目或桌面 My heart will go on')
    args = parser.parse_args()
    source = args.audio or default_audio()[0]
    if not 0 < source.stat().st_size <= 128 * 1024 * 1024:
        raise SystemExit('音频必须非空且不大于 128 MB。')
    manager = JobManager()
    try:
        job = manager.submit(source.read_bytes())
        previous = None
        while True:
            state = manager.snapshot(job['id'])
            display = (state['stage'], round(state['progress'] * 100))
            if display != previous:
                print(f"{display[1]:3d}% {state['message']}", flush=True)
                previous = display
            if state['state'] in TERMINAL:
                break
            time.sleep(.5)
        if state['state'] != 'done':
            raise SystemExit(state.get('error', state['message']))
        installed = install_default(source)
        print(f'默认曲目：{installed}\n分析缓存：{manager.jobs[job["id"]]["result"]}', flush=True)
        cached = manager.submit(installed.read_bytes())
        if not cached['cached']:
            raise SystemExit('缓存复用验证失败')
        print('六轨缓存复用验证通过。', flush=True)
    finally:
        manager.close()


if __name__ == '__main__':
    main()
