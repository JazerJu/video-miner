---
name: video-workflows
description: Orchestrate VidGo skills for end-to-end user requests. Use when the user gives a video URL and asks to download/transcribe/subtitle it, asks to summarize a video and get a task ID, asks to check task progress, mentions a VidGo backend host/IP/domain, asks to configure Bilibili SESSDATA, or asks a natural-language VidGo workflow that requires combining vidgo-endpoint, vidgo-config, search, download-video, subtitle-generate, video-summary-ask, or transcription-status.
license: MIT
---

# Video Workflows

Coordinate existing VidGo skills into complete user-facing workflows.

## Prerequisites

- VidGo backend must be running.
- Load agent-side VidGo API config before running a workflow:
  ```bash
  VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
  vidgo_require_env
  ```
- Use these skills as building blocks:
  - `vidgo-endpoint` for reading, switching, persisting, or testing the backend API base URL.
  - `vidgo-config` for server-side settings such as Bilibili `SESSDATA`.
  - `download-video` for URLs.
  - `query-videos` for finding videos by title and retrieving `id`, `name`, and `url`.
  - `subtitle-generate` for subtitle generation and subtitle task status.
  - `video-summary-ask` for summary submission, summary status, summary result, and video Q&A.
  - `transcription-status` for transcription engine and model readiness.

## Workflow Selection

- URL + subtitles/transcription: run "URL to subtitles".
- Existing title + subtitles/transcription: run "Existing video to subtitles".
- Summary request: run "Start summary task".
- Progress request: run "Check progress".
- Transcription engine/config/model request: use `transcription-status`.
- Backend address/IP/domain/port request: use `vidgo-endpoint` first, then continue the requested workflow.
- Bilibili SESSDATA/login/restricted video request: use `vidgo-config` first, then continue the requested workflow.

Do not use deprecated/web-only workflows such as `watch-live`, `external-transcription`, `realtime-subtitle`, or `media-tools`.

If the user supplies a backend address inline, such as `192.168.1.20:8080` or `https://video.example.com`, normalize and test it with `vidgo-endpoint` before calling other VidGo APIs.

## URL to Subtitles

Use this when the user provides a Bilibili, YouTube, or Apple Podcasts URL and asks for subtitles.

### Step 1: Download the media

Use `download-video`:

1. `POST /api/stream_media/query` with the user URL.
2. Show the resolved title and parts.
3. `POST /api/stream_media/download/add`.
4. Poll `/api/stream_media/download_status` until the matching task is complete or failed.

If the user only wants the job started, return the download task ID if the endpoint provides one. For Bilibili multi-part downloads, the add endpoint may only return `{"success": true}`; use `/api/stream_media/download_status` to find the generated tasks by title.

### Step 2: Find the downloaded video record

After download completes, search by the resolved title:

```bash
curl -s "$VIDGO_API_BASE/api/videos/search/?q=<RESOLVED_TITLE>&mode=title" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Capture:

- `id` as `<VIDEO_ID>`
- `title` or `name` as `<VIDEO_NAME>`
- `url` as `<FILENAME>`

If multiple results match, choose the newest or ask the user to disambiguate.

### Step 3: Submit subtitle generation

Map user intent to language fields:

- "原文就是英文，给它上英文字幕": `src_lang="en"`, `trans_lang="None"`.
- "原文英文，给中文字幕": `src_lang="en"`, `trans_lang="zh"`.
- "原文中文，给英文字幕": `src_lang="zh"`, `trans_lang="en"`.
- If original language is unclear, ask once before submitting.

Use `subtitle-generate`:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/tasks/subtitle_generate/add" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id_list": [<VIDEO_ID>],
    "video_name_list": ["<VIDEO_NAME>"],
    "src_lang": "en",
    "trans_lang": "None",
    "emphasize_dst": ""
  }'
```

Tell the user that subtitle status is checked by `video_id`, not by a separate task ID.

## Existing Video to Subtitles

1. Use `query-videos` to search by title.
2. Capture `id`, `title/name`, and `url`.
3. Submit `/api/tasks/subtitle_generate/add` through `subtitle-generate`.
4. Return the numeric `video_id` as the polling key.

## Start Summary Task

Use this when the user says "summary this video", "总结这个视频", or similar.

1. Use `query-videos` if the user gave a title, or use the known `video_id` and `filename`.
2. Use `video-summary-ask` to call:
   ```bash
   curl -s "$VIDGO_API_BASE/api/video-summary/<ENC_FILENAME>/prerequisites" \
     -H "Authorization: Bearer $VIDGO_API_TOKEN"
   ```
3. If `status` is `no_subtitles`, do not submit summary. Tell the user to generate subtitles first, or ask whether to start subtitles.
4. If `status` is `raw_lang_not_set`, set raw language if known; otherwise ask once.
5. If `status` is `ok`, submit summary:
   ```bash
   curl -s -X POST "$VIDGO_API_BASE/api/summary/add" \
     -H "Authorization: Bearer $VIDGO_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"video_id": <VIDEO_ID>, "language": "中文", "min_coverage": 0.6}'
   ```
6. Return the `task_id` immediately with the current status and tell the user how to query progress.

Do not wait for a summary task to finish unless the user explicitly asks to monitor it.

## Check Progress

Classify the identifier:

- Starts with `summary_`: call `/api/summary/<task_id>/status`.
- Numeric ID: check subtitle status in `/api/tasks/subtitle_generate/status`.
- Download task ID or no ID: call `/api/stream_media/download_status` and match by title/task ID.

Summary progress:

```bash
curl -s "$VIDGO_API_BASE/api/summary/<TASK_ID>/status" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Subtitle progress:

```bash
curl -s "$VIDGO_API_BASE/api/tasks/subtitle_generate/status" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Download progress:

```bash
curl -s "$VIDGO_API_BASE/api/stream_media/download_status" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Report the current stage, `total_progress`, and any error message. Do not claim completion until terminal status is visible.

## Search Workflow

When the user says "search", "找一下", "有没有这个视频", or asks by natural title:

```bash
curl -s "$VIDGO_API_BASE/api/videos/search/?q=<KEYWORD>&mode=title" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Return human-readable `title`/`name`, `id`, and subtitle status when relevant. Use `url` only as the internal filename required by follow-up API calls.

## User-Facing Responses

- For long-running download/subtitle/summary tasks, return the task key immediately.
- For subtitles, say: "字幕任务用 video_id 查询进度: `<VIDEO_ID>`."
- For summary, say: "summary 任务 ID 是 `<TASK_ID>`."
- For URL workflows, explain whether the agent is still downloading, generating subtitles, or waiting for the user to ask for progress.
- For model download workflows, use `transcription-status`; do not mix model downloads with video task IDs.
