---
name: video-summary-ask
description: Summarize VidGo videos and ask questions about video content. Use when the user wants to summarize a video, check a summary task, fetch an existing summary, ask a question about a video, or stream video Q&A through the VidGo backend API.
license: MIT
---

# Video Summary and Ask

Generate long-running video summaries and answer questions about video content through VidGo.

## Prerequisites

- VidGo backend must be running.
- Load agent-side VidGo API config before calling endpoints:
  ```bash
  VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
  vidgo_require_env
  ```
- Know both the `video_id` and the stored video `filename` (`url` from `/api/videos/` or `/api/videos/search/`).
- The video must have subtitles before summary generation. Use the `subtitle-generate` skill first if subtitles are missing.

## Instructions

### Step 1: Identify the video

If the user gives only a title or keyword, search for the video and capture its `id`, `name`, and `url`.

```bash
curl -s "$VIDGO_API_BASE/api/videos/search/?q=<KEYWORD>&mode=title" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Use the returned `id` as `<VIDEO_ID>` and `url` as `<FILENAME>`.

For filenames with spaces or non-ASCII characters, URL-encode before using path endpoints:

```bash
FILENAME='<FILENAME>'
ENC_FILENAME=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$FILENAME")
```

### Step 2: Check summary prerequisites

```bash
curl -s "$VIDGO_API_BASE/api/video-summary/$ENC_FILENAME/prerequisites" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Expected successful response:

```json
{
  "status": "ok",
  "video_id": 123,
  "filename": "example.mp4",
  "has_subtitles": true,
  "raw_lang": "en",
  "available_langs": ["en", "zh"]
}
```

Handle prerequisite statuses:

- `ok`: continue.
- `no_subtitles`: generate subtitles first with the `subtitle-generate` skill.
- `raw_lang_not_set`: set the raw language, then check again.
- `video_not_found`: search videos again and use the exact stored filename.

Set raw language if needed:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/videos/<VIDEO_ID>/language" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"raw_lang": "en"}'
```

Allowed raw language values are `zh`, `en`, `jp`, and `de`.

### Step 3: Submit a summary task

Video summary is asynchronous: submit once, save the returned `task_id`, then poll by that task ID.

```bash
RESP=$(curl -s -X POST "$VIDGO_API_BASE/api/summary/add" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"video_id": <VIDEO_ID>, "language": "中文", "min_coverage": 0.6}')

echo "$RESP"
TASK_ID=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("task_id", ""))')
```

Successful response:

```json
{"task_id": "summary_123_1710000000", "status": "Queued"}
```

Tell the user the task ID immediately. Summary generation can take several minutes for long videos.

### Step 4: Poll summary status

```bash
curl -s "$VIDGO_API_BASE/api/summary/$TASK_ID/status" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Poll every 5 seconds until top-level `status` is `Completed` or `Failed`.

```bash
while true; do
  STATUS_JSON=$(curl -s "$VIDGO_API_BASE/api/summary/$TASK_ID/status" \
    -H "Authorization: Bearer $VIDGO_API_TOKEN")
  echo "$STATUS_JSON"
  STATE=$(echo "$STATUS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))')
  [ "$STATE" = "Completed" ] && break
  [ "$STATE" = "Failed" ] && break
  sleep 5
done
```

Status object fields:

- `status`: `Queued`, `Running`, `Completed`, or `Failed`.
- `stages`: `build`, `extract`, `summarize`.
- `stage_progress`: percentage for each stage.
- `total_progress`: weighted overall percentage.
- `error_message`: failure detail when present.

### Step 5: Fetch summary result

Only fetch the result after the summary task is `Completed`.

```bash
curl -s "$VIDGO_API_BASE/api/video-summary/$ENC_FILENAME" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Successful response:

```json
{"summary": "# Markdown summary...", "file": "example_123_summary.md"}
```

The `summary` field contains markdown. Image links inside the markdown may point to `/media/vidunder/output/...`. Leave those links unchanged by default. If the user explicitly asks to make image links directly clickable, resolve root-relative media links against the user-specified VidGo web/API base URL, not against the MCP endpoint URL. For example, if the user wants `http://127.0.0.1:8080`, then `/media/vidunder/output/.../slide_000.png` becomes `http://127.0.0.1:8080/media/vidunder/output/.../slide_000.png`. If OpenCode connects to MCP through `http://127.0.0.1:8787/sse`, that URL only identifies the MCP transport and must not be used as the media base. For SSH tunnel tests, either forward both `8787` and `8080`, or use the remote VidGo web/API URL the user provides.

### Step 6: Ask a question about the video

Video ask is not a submit-and-poll task. It is synchronous or SSE streaming, and it requires a vidUnder DB generated by a previous summary run.

Synchronous question:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/video-ask/$ENC_FILENAME" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "<QUESTION>"}'
```

Successful response:

```json
{"answer": "..."}
```

Streaming question:

```bash
curl -s -N -X POST "$VIDGO_API_BASE/api/video-ask-stream/$ENC_FILENAME" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "<QUESTION>"}'
```

The stream is Server-Sent Events:

```text
data: {"type":"tool_call","name":"..."}

data: {"type":"answer","content":"..."}

```

Stream completion is indicated by the connection closing. If the stream emits `{"type":"error","content":"..."}`, report that error.

### Manage summary tasks

List all summary tasks:

```bash
curl -s "$VIDGO_API_BASE/api/summary/status" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Retry a failed or completed task:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/summary/<TASK_ID>/retry" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Delete a non-running task:

```bash
curl -s -X DELETE "$VIDGO_API_BASE/api/summary/<TASK_ID>/delete" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

## Error Handling

- `400 Invalid JSON`: fix JSON syntax and retry.
- `400 Missing video_id`: submit summary with a numeric `video_id`.
- `400 Video has no subtitle. Generate subtitles first.`: use `subtitle-generate`, then retry summary.
- `404 Video not found`: search videos and use the exact `id`.
- `404 Summary not found for <filename>`: submit and complete a summary task first.
- `404 No vidunder DB found. Run summary first.`: complete summary generation before video ask.
- `404 SRT file not found`: subtitles are recorded in the database but missing on disk; regenerate or re-upload subtitles.

## Important Notes

- Summary uses task IDs like `summary_<video_id>_<unix_seconds>`.
- Video ask does not return a task ID and should not be polled.
- Do not claim a summary is complete until `/api/summary/<task_id>/status` returns `Completed`.
- If the user only wants to start the job, return the `task_id` and current status without waiting.
- If polling takes too long, report the task ID and the latest `total_progress` so the user can resume status checks later.
