# 本机音频工具

环境：Apple Silicon，项目内 Python 3.11 和 `.venv`。已接入 Hya 图形界面的「分轨分析」模式。服务仍可由系统 Python 启动，后台工作进程显式使用 `.venv/bin/python`。

## 使用

```sh
cd /Users/lightscape/Projects/hya
source .venv/bin/activate
export TORCH_HOME="$PWD/.models/torch"

# 分离为 vocals / drums / bass / other
 demucs -n htdemucs -d cpu -o outputs/demucs /绝对路径/song.wav

# 转 MIDI：显式使用已验证的 ONNX 后端
mkdir -p outputs/midi
basic-pitch --model-serialization onnx outputs/midi /绝对路径/instrument.wav

# 多模型分离工具；已下载 htdemucs 配置，其他模型首次使用需要联网
 audio-separator /绝对路径/song.wav -m htdemucs.yaml \
  --model_file_dir "$PWD/.models/audio-separator" \
  --output_dir outputs/separator --output_format WAV --use_soundfile
```

FFmpeg 由 imageio-ffmpeg 提供，已链接到 `.venv/bin/ffmpeg`，激活环境后可用。未安装独立 ffprobe；上述 WAV 流程不需要它。

Basic Pitch 会提示未安装 TensorFlow/TFLite，以及 CoreML 转换依赖版本警告；上述 ONNX 推理不使用这些后端。resampy 依赖旧的 pkg_resources，因此 setuptools 固定在 81 以下。不要单独升级它。

已安装的完整版本快照见 `requirements-audio.lock.txt`（当前 macOS ARM 环境专用）。`.venv`、`.python` 和 `.models` 不纳入 Git。不要移动这些目录，否则需重建环境。


## Hya MVP 所需资源

运行时直接从 `.models/audio-separator/htdemucs.yaml` 和
`.models/audio-separator/955717e8-8726e21a.th` 加载 Demucs，不会自动下载模型。
Basic Pitch 使用安装包附带的 ONNX 模型，不依赖 TensorFlow 或 CoreML。
FFmpeg 通过 `imageio_ffmpeg.get_ffmpeg_exe()` 定位，无需修改 PATH。

当前机器的环境可直接使用。新机器（相同 macOS ARM / Python 3.11）可先准备：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-audio.lock.txt
```

还需将可信的 `htdemucs.yaml` 与对应 `955717e8` 权重放到上述目录；可复用
上文 audio-separator 命令首次联网获取的模型。本仓库不包含权重；锁定文件是现有环境
快照，新机器安装尚未验证。缺少环境或模型时，界面显示错误，可主动切换快速音高估计。

后台管线采用 Demucs CPU、`shifts=0`、`overlap=0.25`；Basic Pitch 使用默认音符检测参数。
更改这些参数需修改 `ml_pipeline.py`，缓存键随文件内容变化而失效。
分轨 WAV 仅为临时计算资源，不提供持久化播放或下载；MVP 仍播放原曲。
