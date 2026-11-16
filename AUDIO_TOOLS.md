# 本机音频工具

环境：Apple Silicon，项目内 Python 3.11 和 `.venv`。独立于 Hya 原有启动方式；当前尚未接入图形界面。

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
