# 五首演示曲目的分轨与转写

本机导出位置是 `outputs/exports/htdemucs_6s/`。每首曲目使用与 `inputs/` 原始 FLAC 相同的文件名（去掉扩展名）作为目录名。

| 曲目 | 目录名 |
|---|---|
| 周深《Rubia》 | `周深-Rubia/` |
| ILLENIUM、JVKE《With All My Heart》 | `ILLENIUM,JVKE-With All My Heart/` |
| SABAI、Hoang、Ridgely《Million Days》 | `SABAI,Hoang,Ridgely-Million Days/` |
| SABAI、Hoang、Ridgely《Million Days (Acoustic)》 | `SABAI,Hoang,Ridgely-Million Days (Acoustic)/` |
| 林海《远方的寂静》 | `林海-远方的寂静/` |

- `stems/` 包含 `vocals.wav`、`bass.wav`、`piano.wav`、`guitar.wav`、`drums.wav` 和 `other.wav`。全部是 44.1 kHz 的立体声 32 位浮点 WAV，从原曲起点同步，无单轨归一化。
- `basic-pitch/` 包含人声、低音、钢琴、吉他和其他声部各自的 `.mid` 和音符事件 `.csv`，以及按声部命名的合并 MIDI `combined_pitched_stems.mid`。鼓点不作为有音高的 MIDI 转写。

五首均使用本机 `htdemucs_6s/5c90dfd2` 分轨，包括平时在 Hya 中按钢琴独奏处理的《远方的寂静》。Basic Pitch ONNX 采用各声部能量较高的声道转写。导出的 MIDI 和 CSV 保留模型候选音符，可能含串音、漏音和误音。MIDI 的 120 BPM 用于表示时间，不能据此推断原曲速度。

导出文件独立于 Hya 页面使用的分析缓存，仅保存在本机。导出目录由 Git 忽略。
