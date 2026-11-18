"""Prepare local analysis caches and browser playback copies."""
import argparse
from pathlib import Path
import time

from hya import local_demos
from hya.default_audio import default_audio, default_piano_solo, install_default, prepare_playback
from hya.jobs import JobManager, TERMINAL


def warm_cache(manager, source, *, piano_solo):
    if not 0 < source.stat().st_size <= 128 * 1024 * 1024:
        raise SystemExit('音频必须非空且不大于 128 MB。')
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
    print(f'分析缓存：{manager.jobs[job["id"]]["result"]}', flush=True)


def main():
    parser = argparse.ArgumentParser(description='预缓存 Hya 默认曲目或本机演示曲目')
    parser.add_argument('audio', nargs='?', type=Path, help='省略时查找当前默认曲目或桌面 My heart will go on')
    parser.add_argument('--piano-solo', action='store_true', help='已确认是钢琴独奏，直接转写原曲')
    parser.add_argument('--demos', action='store_true', help='预缓存 inputs/ 中的演示曲目')
    args = parser.parse_args()
    if args.demos and (args.audio or args.piano_solo):
        parser.error('--demos 按曲目配置分析，不能同时指定音频或 --piano-solo。')
    manager = JobManager()
    try:
        if args.demos:
            for filename, name, piano_solo in local_demos.TRACKS.values():
                source = local_demos.INPUT_DIR / filename
                if not source.is_file():
                    raise SystemExit(f'缺少输入音频：{source}')
                print(f'演示曲目：{name}', flush=True)
                warm_cache(manager, source, piano_solo=piano_solo)
                manager.cached_result(source, piano_solo=piano_solo)
                print(f'播放副本：{prepare_playback(source, local_demos.PLAYBACK_DIR)}', flush=True)
        else:
            source = args.audio or default_audio()[0]
            piano_solo = args.piano_solo or (args.audio is None and default_piano_solo(source))
            warm_cache(manager, source, piano_solo=piano_solo)
            installed = install_default(source, piano_solo=piano_solo)
            manager.cached_result(installed, piano_solo=piano_solo)
            print(f'默认曲目：{installed}', flush=True)
        print('分析缓存复用验证通过。', flush=True)
    finally:
        manager.close()


if __name__ == '__main__':
    main()
