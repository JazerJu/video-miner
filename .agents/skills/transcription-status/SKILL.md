---
name: transcription-status
description: Check and manage VidGo transcription and video-understanding model readiness. Use when the user asks which transcription engine is active, whether Fun-ASR or GLM-ASR is configured, which engines are available, how much model files have been downloaded, or asks to download/cancel Fun-ASR, GLM-ASR, MiniCPM-V, GLM-OCR, or related local model groups.
license: MIT
---

# Transcription Status

Inspect the active transcription engine and manage local model downloads without exposing API keys.

## Prerequisites

- VidGo backend must be running.
- Load agent-side VidGo API config before calling endpoints:
  ```bash
  VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
  vidgo_require_env
  ```
- If the user asks to change host/IP/domain/port, or if these calls cannot reach the backend, use `vidgo-endpoint` first.

## Check Current Transcription Engine

Use `/api/config/`, but never print API keys or full provider settings. Extract only the transcription fields.

```bash
curl -s "$VIDGO_API_BASE/api/config/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" |
python3 -c '
import json, sys
d = json.load(sys.stdin)
te = d.get("data", {}).get("Transcription Engine", {})
keys = [
    "primary_engine",
    "fallback_engine",
    "transcription_mode",
    "vad_backend",
    "enable_split",
    "split_num_threads",
    "enable_translate",
    "translate_num_threads",
]
for k in keys:
    if k in te:
        print(f"{k}: {te.get(k)}")
'
```

Interpret common engine values:

- `funasr_gguf`: FunASR-GGUF / Fun-ASR-Nano local stack.
- `glm_asr`: GLM-ASR Stack / GLM-ASR-Nano + Qwen3 ForceAligner.
- `elevenlabs`: ElevenLabs API transcription.

## Check Engine Availability

```bash
curl -s "$VIDGO_API_BASE/api/transcription-engines/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" |
python3 -c '
import json, sys
d = json.load(sys.stdin).get("data", {})
print("available_engines:", ", ".join(d.get("available_engines", [])) or "none")
for name, info in d.get("engines", {}).items():
    print("{}: available={}, label={}".format(name, info.get("available"), info.get("name")))
'
```

Use this to answer whether Fun-ASR or GLM-ASR is currently usable.

## Check Model Download Status

Use `/api/vidunder-models/` for the local model groups, including `fun-asr` and `glm-asr`.

```bash
curl -s "$VIDGO_API_BASE/api/vidunder-models/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" |
python3 -c '
import json, sys
d = json.load(sys.stdin)
for m in d.get("data", {}).get("models", []):
    total = m.get("total_size") or 0
    done = m.get("downloaded_size") or 0
    pct = 100 if total and done == total else round(done * 100 / total, 1) if total else 0
    print("{}: {} ({}%, {}/{} bytes) - {}".format(
        m.get("name"), m.get("status"), pct, done, total, m.get("label")
    ))
'
```

Important model groups:

- `fun-asr`: required for `funasr_gguf`.
- `glm-asr`: required for `glm_asr`.
- `minicpm-v4.5`: MiniCPM-V vision model used by video understanding / summary.
- `glm-ocr`: OCR model used by video understanding / summary.
- `embedding`: embedding model used by video understanding support features.

Check active downloads:

```bash
curl -s "$VIDGO_API_BASE/api/vidunder-models/progress/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

If `progress` is `{}`, there is no active model download.

## Start Model Downloads

Use `/api/vidunder-models/download/` to start downloads. Model downloads are asynchronous: submit once, then poll `/api/vidunder-models/progress/` and `/api/vidunder-models/`.

Model name aliases:

- User says `fun-asr`, `funasr`, or `fun-asr-nano` -> `fun-asr`
- User says `glm-asr`, `glm asr`, or `glm-asr stack` -> `glm-asr`
- User says `minicpm-v`, `minicpm`, or `minicpm-v4.5` -> `minicpm-v4.5`
- User says `glm-ocr` or `ocr model` -> `glm-ocr`

Before starting a download, check status first. If `status` is `downloaded`, tell the user it is already downloaded and do not submit another download.

Start a download from Hugging Face:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/vidunder-models/download/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "<MODEL_NAME>", "source": "hf"}'
```

Start a download from ModelScope:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/vidunder-models/download/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "<MODEL_NAME>", "source": "modelscope"}'
```

Allowed `source` values are `hf`, `ms`, and `modelscope`. Prefer `modelscope` when Hugging Face is slow or unavailable.

For model groups without an explicit upstream `repo`, downloads intentionally reference the project-owned mirrors:

- Hugging Face: `JazerJu/VideoMiner`
- ModelScope: `modelmo/VideoMiner`

That includes `minicpm-v4.5`, `glm-ocr`, `fun-asr`, and `embedding`. The `glm-asr` group is different: some files declare upstream repos such as `zai-org/GLM-ASR-Nano-2512` and `Qwen/Qwen3-ForcedAligner-0.6B`.

Successful start response:

```json
{"success": true, "message": "Download started"}
```

Already downloaded response:

```json
{"success": true, "message": "Model already downloaded"}
```

## Poll Model Download Progress

```bash
curl -s "$VIDGO_API_BASE/api/vidunder-models/progress/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" |
python3 -c '
import json, sys
d = json.load(sys.stdin)
progress = d.get("progress", {})
if not progress:
    print("No active model downloads")
for name, p in progress.items():
    print("{}: {} {}% current_file={} error={}".format(
        name, p.get("status"), p.get("percent"), p.get("current_file"), p.get("error")
    ))
'
```

When a model reaches `downloaded`, re-check `/api/vidunder-models/` to confirm the final status.

## Cancel Model Download

Cancel only if the user asks to stop a currently downloading model.

```bash
curl -s -X DELETE "$VIDGO_API_BASE/api/vidunder-models/download/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "<MODEL_NAME>"}'
```

Successful response:

```json
{"success": true, "message": "Cancellation requested"}
```

## Response Guidance

When answering "我的转录引擎配置是什么":

1. State `primary_engine` first.
2. State whether the active engine is available according to `/api/transcription-engines/`.
3. State the relevant model group status:
   - `primary_engine=funasr_gguf` -> report `fun-asr`.
   - `primary_engine=glm_asr` -> report `glm-asr`.
4. Mention active download progress only if `/api/vidunder-models/progress/` is non-empty.
5. Do not include API keys, provider secrets, hotword contents, or the full config JSON.

When answering "下载 fun-asr/glm-asr/minicpm-v/glm-ocr 模型":

1. Normalize the model name.
2. Check `/api/vidunder-models/`.
3. If not downloaded, submit `/api/vidunder-models/download/`.
4. Return the model name and tell the user progress is checked through `/api/vidunder-models/progress/`.
