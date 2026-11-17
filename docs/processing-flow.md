# Hya MVP 处理流程

```mermaid
flowchart LR
    source["导入原曲"] --> submit["提交后台任务"]
    submit --> cache{"有效缓存？"}
    cache -->|"命中"| result["分析 JSON"]
    cache -->|"未命中"| decode["解码立体声"]
    decode --> demucs["Demucs 六声部分离"]
    demucs --> pitch["人声、低音、钢琴、吉他：Basic Pitch ONNX"]
    demucs --> drums["鼓轨：瞬态起音"]
    demucs --> features["六声部：声学特征"]
    decode --> mix["原曲：能量与频谱重心"]
    pitch --> store["保存结果缓存"]
    drums --> store
    features --> store
    mix --> store
    store --> result
    result --> canvas["同窗六轨：音符、鼓点、能量带"]
    source --> player["原曲播放器"]
    default["预缓存默认曲目"] -->|"GET /default/result + gzip"| result
    default -->|"AAC/M4A + HTTP Range"| player
    player -->|"currentTime"| canvas
    canvas --> exportFile["导出 JSON 与 PNG"]
    style demucs fill:#C2E5FF,stroke:#3DADFF
    style pitch fill:#DCCCFF,stroke:#874FFF
    style canvas fill:#CDF4D3,stroke:#66D575
```

所有分析在本机完成。后台单进程顺序执行模型任务，界面轮询阶段进度；可取消或超时结束。原始上传及中间音频随任务清理，分析 JSON 留在 `outputs/cache/`。

六声部都保存声学特征；主视图同步显示人声、低音、钢琴、吉他、鼓点及其他声部。播放采用原曲 `currentTime`，不重新合成 MIDI，也不同时播放六条分轨。快速分析模式独立走旧版 FFT 管线。

默认曲目通过 `precache.py` 先完成分析，再写入 `outputs/default/` 的音频副本与配置。页面打开时直接设置轻量 AAC/M4A 播放地址，并独立读取 `outputs/cache/`；不传输原曲到浏览器再上传，不重新提交任务。播放器通过 Range / HEAD 支持移动 Safari 的按需加载与跳转；缓存返回 gzip 压缩 JSON。可视化加载失败不移除音频地址。
