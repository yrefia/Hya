"""Analyze a song once, then install it as the default only after success."""
import argparse
from pathlib import Path
import time

from hya.default_audio import default_audio, default_piano_solo, install_default
from hya.jobs import JobManager, TERMINAL


def main():
    parser = argparse.ArgumentParser(description='预缓存并设置 Hya 默认曲目')
    parser.add_argument('audio', nargs='?', type=Path, help='省略时查找当前默认曲目或桌面 My heart will go on')
    parser.add_argument('--piano-solo', action='store_true', help='已确认是钢琴独奏，直接转写原曲')
    args = parser.parse_args()
    source = args.audio or default_audio()[0]
    piano_solo = args.piano_solo or (args.audio is None and default_piano_solo(source))
    if not 0 < source.stat().st_size <= 128 * 1024 * 1024:
        raise SystemExit('音频必须非空且不大于 128 MB。')
    manager = JobManager()
    try:
        job = manager.submit(source.read_bytes(), piano_solo=piano_solo)
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
        installed = install_default(source, piano_solo=piano_solo)
        print(f'默认曲目：{installed}\n分析缓存：{manager.jobs[job["id"]]["result"]}', flush=True)
        cached = manager.submit(installed.read_bytes(), piano_solo=piano_solo)
        if not cached['cached']:
            raise SystemExit('缓存复用验证失败')
        print('分析缓存复用验证通过。', flush=True)
    finally:
        manager.close()


if __name__ == '__main__':
    main()
