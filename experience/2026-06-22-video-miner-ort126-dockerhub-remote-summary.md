# 2026-06-22 Video Miner ORT 1.26 镜像发布与远端性能记录

## 目标

- 将 VidGo / Video Miner CUDA 镜像升级到 Python 3.12 + `onnxruntime-gpu==1.26.0`。
- 保持镜像约 5GB。
- 推送到 Docker Hub：`jaceju68/video-miner:cuda-latest`。
- 远端 4090 服务器拉取新镜像并 `docker compose up -d`。
- 验证远端 vLLM 视频 summary 与 MiniCPM caption 性能。
- 修复 Web summary 路径中 GLM-OCR ONNX worker 显存不释放的问题，同时保留主进程 GLM-OCR decoder 复用。

## 本地镜像改动

主要文件：

- `Dockerfile`
- `backend/requirements.txt`
- `backend/video/tasks.py`

关键变更：

- Docker base 改为 `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04`。
- Python 改为 `3.12`。
- `backend/requirements.txt` 固定：
  - `onnxruntime-gpu==1.26.0; python_version >= "3.11"`
  - `onnxruntime-gpu==1.23.2; python_version < "3.11"`
- Dockerfile build 阶段增加 ORT 版本校验：

```bash
python3 -c 'import onnxruntime as ort; print("onnxruntime", ort.__version__, ort.get_available_providers()); assert ort.__version__ == "1.26.0", ort.__version__'
```

- Docker runtime 默认：

```bash
VIDUNDER_MINICPM_ONNX_PROVIDER=cuda
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6
```

- Ubuntu 24.04 CUDA base 已有 `ubuntu:1000`，Dockerfile 中改为复用/重命名 UID 1000 为 `vidgo`，避免 `useradd --uid 1000` 失败。

## GLM-OCR Worker 释放修复

现象：

- 本地 Django runserver 中出现约 10GB 显存占用。
- `nvidia-smi` 看到：
  - Django 主进程约 1.5GB，加载 GLM-OCR GGUF decoder。
  - 一个 `multiprocessing.spawn` 子进程约 7.7GB，加载 ORT CUDA/cuDNN/cuBLAS。

结论：

- `VIDUNDER_GLM_OCR_WORKER_TIMEOUT=180` 只是单次请求等待超时，不是空闲自动退出。
- 当前代码里 GLM-OCR ONNX worker 没有 idle watcher。
- CLI `main.py extract` 有 `finally: shutdown_glm_ocr_workers()`，但 Web summary 的 `generate_summary_for_video()` 直接调用 `cmd_extract()`，调用后没有释放 ONNX worker。

修复：

```python
try:
    cmd_extract(video_path, srt_path=srt_path, output_dir=extract_output, progress_cb=_extract_progress)
finally:
    from external_api import shutdown_glm_ocr_workers
    shutdown_glm_ocr_workers(stop_decoder=False)
```

含义：

- 只停止 GLM-OCR ONNX worker 子进程，释放 ORT CUDA 显存。
- 保留主进程 GLM-OCR decoder，后续 OCR 可复用。

验证：

- 手动杀掉旧 ONNX worker 后，GPU compute 进程只剩 Django 主进程约 1.5GB。
- 新代码会在下一次 Web summary extract 结束后自动执行同样释放逻辑。

## 本地构建与校验

构建命令：

```bash
DOCKER_BUILDKIT=1 docker build --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:36990 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:36990 \
  --build-arg http_proxy=http://127.0.0.1:36990 \
  --build-arg https_proxy=http://127.0.0.1:36990 \
  --build-arg NO_PROXY=localhost,127.0.0.1,host.docker.internal \
  --build-arg no_proxy=localhost,127.0.0.1,host.docker.internal \
  -t jaceju68/video-miner:cuda-latest .
```

构建后未 flatten 镜像约 6.22GB。原因是 Docker 层叠加：Dockerfile 中 `RUN rm -f` 删除 CUDA 库后，底层文件仍计入镜像大小。

按项目规范执行 flatten：

```bash
image=jaceju68/video-miner:cuda-latest
cid=$(docker create "$image")

# 从 docker inspect 读取并重新写回 ENV / EXPOSE / VOLUME / USER / WORKDIR / ENTRYPOINT / CMD
# 注意：LABEL 可跳过，NVIDIA maintainer label 含空格，docker import --change LABEL 容易解析失败。

docker export "$cid" | docker import "${changes[@]}" - "$image"
docker rm "$cid"
```

flatten 后本地镜像：

```text
jaceju68/video-miner:cuda-latest
image id: 542bcd3d1399
size: 5.09GB
```

本地校验：

```bash
docker run --rm --entrypoint python3 jaceju68/video-miner:cuda-latest -c \
  "import sys, os, onnxruntime as ort; print(sys.version); print('ort', ort.__version__, ort.get_available_providers(), ort.get_device()); print('LD_PRELOAD', os.environ.get('LD_PRELOAD'))"
```

结果：

```text
Python 3.12.3
onnxruntime-gpu 1.26.0
providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
device: GPU
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6
```

`manage.py check` 通过。

## Docker Proxy 与 Push

本机两个代理端口均可用：

```bash
curl -x 127.0.0.1:36990 google.com
curl -x 127.0.0.1:7890 google.com
```

Docker Engine proxy 配置位置：

```bash
/etc/systemd/system/docker.service.d/http-proxy.conf
```

切换到 `36990`：

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d

sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf >/dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:36990"
Environment="HTTPS_PROXY=http://127.0.0.1:36990"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker

docker info | grep -i 'Proxy'
```

确认：

```text
HTTP Proxy: http://127.0.0.1:36990
HTTPS Proxy: http://127.0.0.1:36990
No Proxy: localhost,127.0.0.1
```

Push 命令：

```bash
docker push jaceju68/video-miner:cuda-latest
```

重要现象：

- flatten 后镜像是单个大层。
- `docker push` 长时间停在：

```text
abfc323300c4: Preparing
```

- 这不是代理不可用。`dockerd` 有持续 CPU 占用，说明在本地准备 blob、gzip/校验/计算 digest。
- 约十几分钟后才输出最终结果：

```text
abfc323300c4: Pushed
cuda-latest: digest: sha256:92e1653259715f35c7686fb66c46b813836152417094caa9f172fbbfbf376fc3 size: 531
```

Docker Hub manifest：

```text
config digest: sha256:542bcd3d1399f850edf69bc2831208251a0caea5dd1d88c02edacba77089992d
layer digest:  sha256:3be1a840739f1b4e1f16cb07e161c352c7fe7b0d69f2241c6cd60f072e7f89b3
layer size:    2872761749 bytes
```

## 远端部署

远端：

```text
host: 100.64.241.215
user: jjju
compose dir: ~/vidgo-compose-mcp
container: vidgo-app
```

部署命令：

```bash
ssh jjju@100.64.241.215
cd ~/vidgo-compose-mcp
docker compose pull
docker compose up -d
```

远端拉取时下载新层：

```text
3be1a840739f  2.873GB
```

远端确认：

```bash
docker inspect vidgo-app --format 'image={{.Image}}'
docker exec vidgo-app python3 -c "import onnxruntime as ort, sys; print(sys.version); print(ort.__version__); print(ort.get_available_providers()); print(ort.get_device())"
```

结果：

```text
image=sha256:542bcd3d1399f850edf69bc2831208251a0caea5dd1d88c02edacba77089992d
Python 3.12.3
onnxruntime-gpu 1.26.0
providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
device: GPU
```

健康检查：

```bash
curl -sS http://127.0.0.1:8080/api/auth/check-root/
```

返回：

```json
{"root_exists": true, "message": "Use command: python manage.py reset_root_password"}
```

远端 GPU 空闲：

```text
NVIDIA GeForce RTX 4090, driver 570.124.04, 531 MiB, 0%
```

## vLLM 视频 Summary 性能

已有远端文件：

```text
/app/media/saved_video/vLLM_DeepSeek.mp4
/app/media/vidunder/db/vLLM_DeepSeek.json
```

旧 DB：

```text
n_clips: 556
duration: 5551.328s
video_path in DB: /app/vLLM_DeepSeek.mp4
srt_path in DB: /app/empty.srt
```

因为 DB 记录的路径在 `/app`，容器内补了临时入口：

```bash
docker exec -u root vidgo-app bash -lc \
  "ln -sf /app/media/saved_video/vLLM_DeepSeek.mp4 /app/vLLM_DeepSeek.mp4; touch /app/empty.srt; chown -h vidgo:vidgo /app/vLLM_DeepSeek.mp4; chown vidgo:vidgo /app/empty.srt"
```

直接 CLI `cmd_summarize` 会缺少 `VIDUNDER_DEEPSEEK_API_KEY`，因为 compose env 没有保存 summary key；Web task 会从应用设置注入。为了复用设置且不暴露 key，测试命令中调用 Django 配置注入：

```bash
docker exec \
  -e VIDUNDER_VIDEO_PATH=/app/vLLM_DeepSeek.mp4 \
  -e VIDUNDER_SRT_PATH=/app/empty.srt \
  vidgo-app python3 -c "
import os,sys,time
sys.path.insert(0, '/app/vid_under')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vid_go.settings')
import django
django.setup()
from video.tasks import _inject_vidunder_config
_inject_vidunder_config()
from main import cmd_summarize
t=time.time()
cmd_summarize(thinking_budget='low', output_path='/app/media/vidunder/output/vLLM_DeepSeek_summary_ort126.md')
print(f'wall={time.time()-t:.2f} sec')
"
```

结果：

```text
耗时: 299.8s (5.0min)
wall=299.76 sec
output: /app/media/vidunder/output/vLLM_DeepSeek_summary_ort126.md
size: 89K
lines: 1317
```

说明：

- 这是 summarize-only，复用已有 556 clips DB。
- 没有重跑 build/caption/extract。
- 第一次会重新计算 555 条 caption embedding。
- 主要耗时来自外部 LLM API，不是 4090 GPU。
- 运行后 GPU 仍为空闲：

```text
531 MiB, 0%
```

## MiniCPM Caption 性能小测

为了验证 ORT 1.26 + 4090 的实际 MiniCPM caption 路径，截取 vLLM 视频前 100 秒：

```bash
docker exec vidgo-app bash -lc \
  "ffmpeg -y -ss 0 -t 100 -i /app/media/saved_video/vLLM_DeepSeek.mp4 -c copy /tmp/vllm_100s.mp4"
```

运行 build/caption 小测：

```bash
docker exec \
  -e VIDUNDER_VIDEO_PATH=/tmp/vllm_100s.mp4 \
  -e VIDUNDER_SRT_PATH=/app/empty.srt \
  -e VIDUNDER_MODEL_ROOT=/app/models \
  -e VIDUNDER_MINICPM_ONNX_PROVIDER=cuda \
  -e VIDUNDER_N_GPU_LAYERS=99 \
  -e VIDUNDER_N_CTX=4096 \
  -e VIDUNDER_N_BATCH=512 \
  -e VIDUNDER_KV_CACHE_TYPE=q4_0 \
  -e VIDUNDER_HWACCEL=none \
  vidgo-app python3 -c "
import sys,time
sys.path.insert(0, '/app/vid_under')
from video_db import build_database
t=time.time()
build_database('/tmp/vllm_100s.mp4', '/app/empty.srt', db_name='perf_vllm_100s_ort126', clip_secs=10, video_fps=2, frames_per_clip=7)
print(f'wall={time.time()-t:.2f} sec')
"
```

关键日志：

```text
ggml_cuda_init: found 1 CUDA devices:
  Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9

[MiniCPM-V] ONNX worker:
  siglip_providers: ['CUDAExecutionProvider', 'CPUExecutionProvider']
  resampler_providers: ['CUDAExecutionProvider', 'CPUExecutionProvider']

[10/11] 3s/clip  (90s-100s)
数据库已保存: /app/media/vidunder/db/perf_vllm_100s_ort126.json  (10 clips)
wall=47.99 sec
```

结论：

- MiniCPM ONNX 路径确认为 CUDA。
- 100 秒 / 10 clips 总耗时 47.99s。
- 稳定段日志为 3s/clip。
- 跑完后显存回到 531MiB，说明 build 子进程退出后 MiniCPM/ORT 显存正常释放。

按稳定段估算：

- 20 分钟视频约 120 clips，caption 约 6 分钟量级。
- vLLM_DeepSeek 约 556 clips，若完整重跑 build，按 3s/clip 稳定段估算约 28 分钟上下，实际会随每段生成 token 数波动。

## 当前最终状态

远端：

```text
vidgo-app running
image: sha256:542bcd3d1399f850edf69bc2831208251a0caea5dd1d88c02edacba77089992d
onnxruntime-gpu: 1.26.0
GPU idle: 531MiB / 0%
```

Docker Hub：

```text
repository: jaceju68/video-miner
tag: cuda-latest
manifest digest: sha256:92e1653259715f35c7686fb66c46b813836152417094caa9f172fbbfbf376fc3
config digest: sha256:542bcd3d1399f850edf69bc2831208251a0caea5dd1d88c02edacba77089992d
```

输出文件：

```text
/app/media/vidunder/output/vLLM_DeepSeek_summary_ort126.md
/app/media/vidunder/db/perf_vllm_100s_ort126.json
```

## 2026-06-23 实时流转录幻觉修复

触发问题：

- 实时流转录里出现大量同秒短段，例如 `04:02 -> 04:02`。
- GLM-ASR 对这些极短/无效片段输出通用英文模板，例如 `Of course, I can help with that...`。
- DeepSeek 再把这些模板翻译成中文，所以前端看到“请提供你希望转录的讲话内容”一类字幕。
- 中文视频也被前端硬编码为 `source_lang='en'`，导致 DeepSeek 对中文原文给出“文本不是英文”的拒绝式翻译。

排查结论：

- 不是单纯 VAD 模型精度问题。
- `stream_transcriber.py` 的实时链路把 VAD 片段写成 raw float32 `.bin` 后直接传给 GLM-ASR daemon。
- GLM-ASR 自带 orchestrator 普通和 live 路径都是传 16k mono `.wav`，当前 VidGo 实时路径和官方路径输入格式不一致。

本地修改：

- `backend/video/stream_transcriber.py`
  - 临时片段从 raw `.bin` 改为标准 `16k mono PCM16 WAV`。
  - 增加短段过滤：默认丢弃 `<0.7s` 片段，可用 `VIDGO_STREAM_ASR_MIN_SEGMENT_SECONDS` 调整。
  - 增加低能量过滤：默认 RMS `<80` 丢弃，可用 `VIDGO_STREAM_ASR_MIN_RMS` 调整。
  - 增加 ASR 模板幻觉过滤：过滤 `please provide the speech`、`unable to transcribe speech`、`of course, I can help...` 等文本。
  - 增加明显重复跑飞文本过滤，例如短语连续重复多次。
  - 后端翻译语言归一化，`source_lang == target_lang` 或目标语言为空时跳过 DeepSeek。
  - `source_lang=auto` 时 prompt 不再写死英文源语言。
- `frontend/src/views/StreamTranscriptionView.vue`
  - 不再把实时转录源语言硬编码为 `en`。
  - 解析流后自动推断源语言：Bilibili 默认中文，YouTube 优先使用音频语言元数据，否则 Auto。
  - 弹窗新增 Source 选择：Auto / 中文 / English / 日本語。
  - Target 新增 Off，允许只转录不翻译，避免每段调用 DeepSeek。
- `frontend/src/composables/StreamTranscriptionAPI.ts`
  - `ResolvedStream.platform` 类型补齐 `youtube_live` / `bilibili_live`。

验证：

```bash
python -m py_compile backend/video/stream_transcriber.py backend/video/views/stream_transcription.py
npm run type-check
PYTHONPATH=backend DJANGO_SETTINGS_MODULE=vid_go.settings /home/jju/anaconda3/envs/autocut312/bin/python - <<'PY'
import os, tempfile, wave
import django
import numpy as np

django.setup()
from video.stream_transcriber import _is_bad_asr_text, StreamTranscriber, SAMPLE_RATE
assert _is_bad_asr_text('Of course, I can help with that. Please provide the speech you would like me to transcribe into written format.')
assert not _is_bad_asr_text('这是正常的比赛解说内容')
t = StreamTranscriber('', None, {}, lambda s: None, lambda p: None, lambda: None, lambda e: None)
path = os.path.join(tempfile.gettempdir(), 'vidgo_stream_test.wav')
t._write_wav_segment(path, np.zeros(SAMPLE_RATE, dtype=np.int16))
with wave.open(path, 'rb') as f:
    assert f.getnchannels() == 1
    assert f.getframerate() == SAMPLE_RATE
    assert f.getsampwidth() == 2
os.remove(path)
t._cleanup()
print('stream_transcriber helpers ok')
PY
```

结果：

```text
py_compile: pass
vue-tsc --build: pass
stream_transcriber helpers: pass
```

## 2026-06-23 实时流转录提前结束修复

触发问题：

- 前端显示视频 Duration 为 13:46。
- 实时转录显示 100%，但最后一个 segment 只到约 03:26。
- 这说明后端并不是转录了 13:46 后只显示前 3:30，而是 ffmpeg 实际读取的音频输入在 3:30 左右就 EOF 了。
- 原代码 `StreamTranscriber.run()` 在 ffmpeg 输入结束后无条件 `on_progress(100.0)`，因此“输入提前结束”会被误显示为 Completed 100%。

修复：

- `frontend/src/composables/StreamTranscriptionAPI.ts`
  - `startTranscription()` 增加 `expectedDuration` 和 `audioFormatId` 参数。
- `frontend/src/views/StreamTranscriptionView.vue`
  - 开始转录时传入 `resolvedStream.duration` 和 `resolvedStream.audio.format_id`。
- `backend/video/views/stream_transcription.py`
  - `/api/stream_transcription/start` 接收 `expected_duration` 和 `audio_format_id`。
- `backend/video/stream_transcriber.py`
  - `StreamTranscriber` 保存期望时长。
  - 进度按期望时长计算，并在最终完成前最多上报 99%。
  - ffmpeg EOF 后检查实际读取样本数：如果读取时长比期望短超过 30s 且低于期望的 85%，抛出 `Audio stream ended early`，走 failed，而不是 complete。
  - YouTube 预下载使用前端已解析的 `audio_format_id`，不再重新使用 `bestaudio/best` 选择音轨。
  - YouTube 预下载输出路径改为 `tmp_base.%(ext)s`，并从 yt-dlp 的 `requested_downloads` / `prepare_filename` / glob fallback 获取真实文件路径。
  - YouTube 预下载后 probe 实际文件时长，明显短于期望时删除并 fallback 到直接 ffmpeg。

验证：

```bash
python -m py_compile backend/video/stream_transcriber.py backend/video/views/stream_transcription.py
npm run type-check
PYTHONPATH=backend DJANGO_SETTINGS_MODULE=vid_go.settings /home/jju/anaconda3/envs/autocut312/bin/python - <<'PY'
import django

django.setup()
from video.stream_transcriber import StreamTranscriber, SAMPLE_RATE
t = StreamTranscriber('', None, {}, lambda s: None, lambda p: None, lambda: None, lambda e: None, expected_duration=826)
t._sample_index = int(206 * SAMPLE_RATE)
try:
    t._raise_if_audio_ended_early()
except RuntimeError as exc:
    assert 'read 206.0s of expected 826.0s' in str(exc)
else:
    raise AssertionError('early EOF was not detected')
t._sample_index = int(820 * SAMPLE_RATE)
t._raise_if_audio_ended_early()
t._cleanup()
print('early EOF guard ok')
PY
```

结果：

```text
py_compile: pass
vue-tsc --build: pass
early EOF guard: pass
```

## 2026-06-23 实时流转录诊断日志

用户提供旧日志：

```text
[download]  19.4% of   10.31MiB at    5.40MiB/s ETA 00:01
[23/Jun/2026 06:39:32] "POST /api/stream_transcription/start HTTP/1.1" 200 68
...
[23/Jun/2026 06:40:02] "GET /api/stream_transcription/a96bd555-a8a7-43d3-bfb3-5920463c11ed/events HTTP/1.1" 200 1606865
```

旧日志只能证明：

- YouTube 分支开始下载了一个 `10.31MiB` 的音频文件。
- SSE 在开始后约 30s 正常返回。
- 没有记录下载完成后的音频路径/大小/时长、ffmpeg 实际读取时长、VAD 提交段数、ASR 过滤数，因此不能定位问题是在下载、ffmpeg、VAD 还是 ASR。

新增诊断日志：

- `start_transcription`
  - 打印 `audio` / `original` / `expected` / `audio_format_id` / `source_lang` / `target_lang` / headers / proxy。
- YouTube prefetch
  - 打印下载目标、format、expected、proxy。
  - 下载完成后打印真实文件路径、文件大小、`ffprobe` duration、expected、ext、format_id。
  - 如果预下载文件时长明显短于 expected，打印 warning 并 fallback 到直接 ffmpeg。
- ffmpeg/VAD/ASR
  - 开始时打印输入、expected、ffprobe probed duration、是否 temp_audio、proxy、headers。
  - 每读 60s 打印 read progress、submitted/emitted/skipped 计数。
  - 每个提交给 ASR 的段打印 start/end/duration/rms。
  - 短段/低能量段打印 skip 原因。
  - 空 ASR 结果和幻觉过滤结果打印 drop 原因。
  - ffmpeg EOF 时打印 read/expected/probed/returncode/submitted/emitted/skipped/empty/filtered/pending/stderr tail。
  - early EOF 时打印 read/expected/probed/stderr tail。

下一次复现时主要看这些行：

```text
[stream-asr:<task_id>] youtube prefetch done path=... size=... duration=... expected=...
[stream-asr:<task_id>] start input=... expected=... probed=... temp_audio=...
[stream-asr:<task_id>] read progress ... submitted=... emitted=...
[stream-asr:<task_id>] ffmpeg-eof read=... expected=... probed=... submitted=... emitted=...
[stream-asr:<task_id>] early EOF detected read=... expected=... probed=...
```

验证：

```bash
python -m py_compile backend/video/stream_transcriber.py backend/video/views/stream_transcription.py
npm run type-check
PYTHONPATH=backend DJANGO_SETTINGS_MODULE=vid_go.settings /home/jju/anaconda3/envs/autocut312/bin/python - <<'PY'
import django

django.setup()
from video.stream_transcriber import StreamTranscriber, SAMPLE_RATE

t = StreamTranscriber('', None, {}, lambda s: None, lambda p: None, lambda: None, lambda e: None, expected_duration=826, task_id='test')
t._sample_index = int(206 * SAMPLE_RATE)
try:
    t._raise_if_audio_ended_early()
except RuntimeError as exc:
    assert 'read 206.0s of expected 826.0s' in str(exc)
else:
    raise AssertionError('early EOF was not detected')
t._cleanup()
print('early EOF guard ok')
PY
```

结果：

```text
py_compile: pass
vue-tsc --build: pass
early EOF guard: pass
console logging confirmed: WARNING stream_translate [stream-asr:test] early EOF detected ...
```

## 2026-06-23 实时流转录 resolve 修复

现象：

```text
WARNING: [youtube] ... n challenge solving failed ...
WARNING: Only images are available for download. use --list-formats to see them
ERROR: [youtube] ... Requested format is not available
Bad Gateway: /api/stream_transcription/resolve

bvid: BV1MCEg6bEmD
Neither 1080p nor 720p ... using first available resolution.
Bad Gateway: /api/stream_transcription/resolve
```

YouTube 根因：

- `autocut312` 中 `yt-dlp==2026.06.09`、`yt-dlp-ejs==0.8.0`。
- 系统 `node` 是 `20.20.0`，但新版 `yt-dlp` 要求 Node `>=22.0.0` 才算 supported runtime。
- `YouTubeDownloader` 会自动加载 `backend/media/cookies/youtube-cookies.txt`。
- cookies 存在时 YouTube extractor 进入认证态，`android/ios` client 会被跳过，剩下 web client 需要 n challenge；由于 Node 20 unsupported，解析可能只剩 storyboard 图片格式。

修复：

- `backend/utils/stream_downloader/youtube_download.py`
  - `get_video_info()` 改为多 attempt。
  - 默认 attempt 保留 cookies。
  - 如果返回空 info 或没有可用 video/audio format，自动重试 `no-cookie-mobile-client`：

```python
extractor_args = {"youtube": {"player_client": ["default", "android", "ios"]}}
```

- 只影响 metadata/resolve，不改变普通下载逻辑。
- 新增日志：每次 attempt 打印 `formats/video/audio/cookies`。

Bilibili 修复：

- `backend/video/views/stream_transcription.py`
  - stream transcription resolve 不再通过 `parse_video_url()` 二次选择 URL。
  - 改为从 `_select_bilibili_dash_items()` 选中的 `video_item/audio_item` 直接取 `baseUrl/base_url`，没有则取 `backupUrl/backup_url`。
  - 失败时错误信息包含 `code/message/dash_video/dash_audio/selected_video/selected_audio`。
  - 成功时日志包含 bvid、cid、dash 数量、选中格式和 URL 是否存在。

验证命令：

```bash
/home/jju/anaconda3/envs/autocut312/bin/python -m py_compile \
  backend/utils/stream_downloader/youtube_download.py \
  backend/video/views/stream_transcription.py \
  backend/video/stream_transcriber.py

cd frontend && npm run type-check

PYTHONPATH=backend DJANGO_SETTINGS_MODULE=vid_go.settings \
/home/jju/anaconda3/envs/autocut312/bin/python - <<'PY'
import django, json
django.setup()
from django.test import Client

client = Client()
for url in [
    'https://www.youtube.com/watch?v=JVh6sUHRxjg',
    'https://www.bilibili.com/video/BV1MCEg6bEmD',
]:
    resp = client.post(
        '/api/stream_transcription/resolve',
        data=json.dumps({'url': url}),
        content_type='application/json',
    )
    data = resp.json()
    print(resp.status_code, data.get('success'), data.get('platform'), data.get('duration'))
    print('video', (data.get('video') or {}).get('format_id'), bool((data.get('video') or {}).get('url')))
    print('audio', (data.get('audio') or {}).get('format_id'), bool((data.get('audio') or {}).get('url')))
PY
```

结果：

```text
YouTube: 200 success=True platform=youtube duration=826 video=18 audio=140
Bilibili: 200 success=True platform=bilibili duration=375 video=32 audio=30280
py_compile: pass
vue-tsc --build: pass
```

Node 22 / nvm 处理：

- `~/.bashrc` 原本已有 nvm 初始化片段，但 `~/.nvm` 目录不存在。
- 使用 `127.0.0.1:36990` 代理安装 nvm `v0.40.3` 与 Node `v22.23.0`：

```bash
export HTTP_PROXY=http://127.0.0.1:36990 HTTPS_PROXY=http://127.0.0.1:36990
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | PROFILE="$HOME/.bashrc" bash
source "$HOME/.nvm/nvm.sh"
nvm install 22
nvm use --delete-prefix v22.23.0
nvm alias default 22
```

- 当前验证：

```text
node=/home/jju/.nvm/versions/node/v22.23.0/bin/node
node --version: v22.23.0
yt-dlp JS runtimes: node-22.23.0
```

- 用 Node 22 后，YouTube resolve 默认 attempt 返回：

```text
formats=28 video=21 audio=11 cookies=True
```

注意：

- 旧终端不会自动切换到 nvm Node 22；需要重新打开终端，或在启动后端前执行：

```bash
source ~/.nvm/nvm.sh
nvm use 22
```

- `backend/media/cookies/youtube-cookies.txt` 曾提示已失效；公共公开视频现在即使 cookies 失效也有无 cookies fallback，但需要登录权限的视频仍应重新导出 cookies。

## 2026-06-23 实时流转录 torch/VAD 修复

现象：

```text
[stream-asr:<task_id>] start_transcription ...
[stream-asr:<task_id>] failed: No module named 'torch'
[stream-asr:<task_id>] finished read=0.0s expected=unknown probed=unknown returncode=None submitted=0 emitted=0 ...
```

根因：

- 失败发生在 `_run_pipeline()` 一开始创建 VAD 阶段，还没进入 ffmpeg 读流。
- 当前配置为：

```ini
[Transcription Engine]
vad_backend = silero
```

- `backend/third_party/silero-vad` 即使调用 `load_silero_vad(onnx=True)`，其 `model.py` / `utils_vad.py` 顶层仍会 `import torch`。
- 所以这不是 FunASR-GGUF 或 GLM-ASR 依赖 torch，而是实时转录 VAD backend 选到了 Silero wrapper。

修复：

- 默认 VAD backend 从 `silero` 改为 `firered`：
  - `backend/video/views/set_setting.py`
  - `backend/config/config.ini.example`
  - 本地当前 `backend/config/config.ini`
- `backend/video/stream_transcriber.py`
  - `_get_vad_backend()` 默认返回 `firered`。
  - 如果旧配置仍写着 `silero`，但环境没有 torch，则自动 fallback 到 `FireRedVAD`。
  - 未知 VAD backend 也 fallback 到 `FireRedVAD`。

验证：

```text
torch spec None
vad_backend firered
vad class asr_utils.firered_vad FireRedVAD
silence result {}
```

完整 1 秒本地静音实时转录 smoke test：

```text
Completed None {'percent': 100.0} segments 0
```

强制旧配置 `silero` 的 fallback 测试：

```text
silero VAD requires torch; falling back to FireRed ONNX VAD
asr_utils.firered_vad FireRedVAD
```

## 2026-06-23 实时流转录 3:24 截断修复

现象：

- UI 上转录只到 `03:24` 左右。
- 日志显示 ffmpeg 实际读完了全音频：

```text
ffmpeg-eof read=374.7s expected=unknown probed=374.7s returncode=0
```

- 但 204s 之后没有有效 submit，只剩大量 64ms 左右的短段：

```text
skip short segment start=242.930s end=242.994s duration=0.064s ...
```

结论：

- 不是下载/ffmpeg/ASR 提前结束。
- 是 FireRed VAD streaming wrapper 的时间轴累计有 drift。
- 旧 FireRed wrapper 在每个 ONNX output frame 上执行 `_sample_offset += 160`，但它又保留了 240 samples overlap。长音频中 `_sample_offset` 会越来越落后真实样本位置。

验证 drift：

```text
# 修复前：输入 640s，VAD offset 落后 40s
real 10240000 vad_offset 9599680 diff -640320 sec_diff -40.02

# 修复后：只剩固定 overlap 240 samples，即 15ms
real 10240000 vad_offset 10239760 diff -240 sec_diff -0.015
```

进一步修复：

- 新增 `backend/asr_utils/silero_vad_onnx.py`。
- 直接用 vendored `silero_vad.onnx` + ONNX Runtime 实现 torchless Silero VAD。
- 默认 `vad_backend` 改为 `silero_onnx`。
- FireRed 保留为 fallback。

真实 B 站 VAD-only 验证：

```text
duration 375 segments 47
first5 [(0.162, 4.830, ...), ...]
last10 [..., (365.794, 371.870, ...), (372.130, 374.656, ...)]
last_end 374.656 read 374.656
```

真实 ASR smoke test：

```text
status Completed error None progress {'percent': 100.0}
segments 47
last {'index': 46, 'text': '等你感觉到疼的时候，已经是晚期了。', 'start': 372.13, 'end': 374.656}
```

涉及文件：

- `backend/asr_utils/silero_vad_onnx.py`
- `backend/asr_utils/firered_vad.py`
- `backend/video/stream_transcriber.py`
- `backend/video/views/set_setting.py`
- `backend/config/config.ini`
- `backend/config/config.ini.example`
