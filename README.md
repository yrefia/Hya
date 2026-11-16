# Hya · 声音的层次

本机音频可视化 MVP。Python 服务 + 浏览器 Canvas：先分析整曲，再跟随原曲播放时钟显示人声音符、低音音符与鼓点。默认使用 Demucs 分轨和 Basic Pitch ONNX 转写；也保留无需第三方依赖的快速音高估计。

## 启动

双击 `启动 Hya.command`，或运行：

```sh
cd /Users/lightscape/Projects/hya
python3 app.py
```

浏览器自动打开带会话 token 的本机地址。导入音频或点击「体验示例声音」，等待分析完成后播放。示例是合成旋律与和弦，没有真实人声，不适合评估人声分离准确率。关闭终端或 Control+C 停止服务，并取消后台任务。

- 上限：128 MB、10 分钟；模型任务最长运行 30 分钟。
- 默认「分轨分析」使用项目 `.venv/bin/python`，环境与模型准备见 [AUDIO_TOOLS.md](AUDIO_TOOLS.md)。现有机器已准备好模型，不需要账号或联网推理。
- 「快速音高估计」调用 macOS `afconvert` + 标准库 FFT，不做分轨。
- 播放器播放原始文件；系统能解码的格式不一定能被浏览器播放，必要时先转换成 WAV / MP3。
- 可选测试入口：`HYA_TEST_AUDIO='/absolute/path/song.wav' python3 app.py`。

## 分轨分析如何工作

1. 上传到仅监听 `127.0.0.1` 的 Python 服务，返回任务 ID。
2. 用音频内容、分析代码、依赖锁定文件及 Demucs 权重/配置生成缓存键；命中则直接读取 JSON。
3. 单个后台工作进程使用 FFmpeg 解码为 44100 Hz 立体声，验证时长。
4. 本地 `htdemucs` 分离 vocals / bass / drums / other。使用同一增益处理，不分别归一化各声部。
5. 对原曲和四个声部计算 RMS、固定 −60…0 dBFS 能量映射及功率加权频谱重心。4096 点窗口，2205 点步长（20 帧/秒）；逐声道功率平均，避免反相立体声能量抵消。
6. Basic Pitch 的 ONNX 后端转写人声、低音，保留音符起止、MIDI 音高、模型振幅分数。选择各声部较强的声道作为转写输入。鼓轨使用正向频谱通量提取瞬态起音，不宣称检测了节拍/BPM。
7. 前端轮询任务进度。完成后以播放器 `currentTime` 显示 12 秒历史：金色人声音符条、绿色低音音符条、珊瑚色鼓点。暂停和跳转保持历史形状一致；关闭连续滚动后按 12 秒分页。
8. 可导出完整 JSON 和整曲音符/起音 PNG。原曲能量/重心在独立面板显示。

分轨是估计，可能串音。人声可能包含和声，other 不是一种独立乐器。Basic Pitch 音符条不表达完整连续滑音，振幅分数也不是校准置信度。鼓点强度在鼓轨内归一化，不用于跨曲比较。

## 后台任务与存储

- `POST /jobs`：原始音频 body，返回 202 和任务状态。
- `GET /jobs/{id}`：状态、阶段、进度、错误信息。
- `GET /jobs/{id}/result`：完成后的 JSON；未完成返回 409。
- `DELETE /jobs/{id}`：取消排队或运行中的任务。
- 上述接口均要求 `X-Hya-Token`。`/analyze` 保留快速分析接口。
- 一次运行一个模型任务，最多四个未完成任务。任务状态仅在当前进程内保存，最多保留 32 条；重启后重新导入可复用磁盘缓存。
- 原始上传和中间音频只存在任务临时目录，完成、失败或取消后清理。分析 JSON 保存在 `outputs/cache/`，包含音符与声学信息；退出后仍保留。需要清理时可删除此目录，下次重新分析。
- `.venv`、`.models`、音频与 `outputs` 均不提交 Git。

## 代码结构

| 文件 | 职责 |
|---|---|
| `app.py` | 本机 HTTP 路由、会话校验、快速分析入口 |
| `jobs.py` | 有界队列、子进程、进度、取消、超时、缓存 |
| `ml_pipeline.py` | 解码、分轨、转写、声学特征和鼓点 |
| `audio_analysis.py` / `music_features.py` | 旧版快速 FFT 和音高候选算法 |
| `ui.html` | 播放、音符/鼓点绘制、任务状态与导出 |

## 验证

```sh
.venv/bin/python -m unittest -v test_audio test_ml_pipeline test_jobs
node test_render.js
node test_ui.js
```

自动化检查信号、反相立体声、音符边界、鼓点时刻，以及任务鉴权、缓存、取消、失败/超时、绘图历史稳定性和界面状态恢复。

实际模型冒烟测试：

```sh
.venv/bin/python ml_pipeline.py /absolute/path/short.wav /tmp/hya-result.json
```

短合成音频只能验证流水线可运行；复杂音乐的分离/转写准确率仍需真实样本评估。处理流程见 [docs/processing-flow.md](docs/processing-flow.md)。
