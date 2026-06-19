---
name: subtitle-generate
description: Generate, translate, retry, delete, and check subtitle tasks for VidGo videos. Use when a video needs subtitles before summary or ask workflows, when the user wants transcript generation, or when polling subtitle task progress.
license: MIT
---

# Subtitle Generate

Generate original subtitles, optionally translate subtitles, and poll VidGo subtitle task progress.

## Prerequisites

- VidGo backend must be running.
- Load agent-side VidGo API config before calling endpoints:
  ```bash
  VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
  vidgo_require_env
  ```
- Know each target video's `id` and `name`. Use the `query-videos` skill if needed.
- Bearer token authentication skips CSRF validation in this project.

## Instructions

### Step 1: Identify videos

Search by title if the user gives a keyword:

```bash
curl -s "$VIDGO_API_BASE/api/videos/search/?q=<KEYWORD>&mode=title" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Use each returned `id` in `video_id_list` and its title/name in the same position in `video_name_list`.

### Step 2: Start subtitle generation

Generate original subtitles only:

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

Generate original subtitles and a translated subtitle track:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/tasks/subtitle_generate/add" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id_list": [<VIDEO_ID>],
    "video_name_list": ["<VIDEO_NAME>"],
    "src_lang": "en",
    "trans_lang": "zh",
    "emphasize_dst": "<TERMS_OR_EMPTY_STRING>"
  }'
```

Successful response:

```json
{"success": true}
```

Important: this endpoint does not return a `task_id`. The task key is the `video_id`.

Supported language values:

- `src_lang`: `zh`, `en`, `jp`, `de`
- `trans_lang`: `None`, `zh`, `en`, `jp`, `de`

### Step 3: Poll subtitle task status

```bash
curl -s "$VIDGO_API_BASE/api/tasks/subtitle_generate/status" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

The response is a map keyed by video ID:

```json
{
  "123": {
    "filename": "Video title",
    "src_lang": "en",
    "trans_lang": "zh",
    "video_id": 123,
    "stages": {
      "transcribe": "Running",
      "optimize": "Queued",
      "translate": "Queued"
    },
    "stage_progress": {
      "transcribe": 45,
      "optimize": 0,
      "translate": 0
    },
    "total_progress": 18
  }
}
```

Poll every 5 seconds until all relevant stages are terminal.

Terminal success stages are `Completed` or `Skipped`. Failure is any stage with `Failed`.

```bash
VIDEO_ID=<VIDEO_ID>
while true; do
  STATUS_JSON=$(curl -s "$VIDGO_API_BASE/api/tasks/subtitle_generate/status" \
    -H "Authorization: Bearer $VIDGO_API_TOKEN")
  echo "$STATUS_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(json.dumps(data.get(str('"$VIDEO_ID"'), {}), ensure_ascii=False, indent=2))'
  STATE=$(echo "$STATUS_JSON" | python3 -c 'import json,sys; t=json.load(sys.stdin).get(str('"$VIDEO_ID"'), {}); stages=t.get("stages", {}); vals=list(stages.values()); print("Failed" if "Failed" in vals else "Completed" if vals and all(v in ("Completed","Skipped") for v in vals) else "Running")')
  [ "$STATE" = "Completed" ] && break
  [ "$STATE" = "Failed" ] && break
  sleep 5
done
```

### Step 4: Translate existing subtitles only

Use this when original subtitles already exist and the user only wants another language.

```bash
curl -s -X POST "$VIDGO_API_BASE/api/tasks/subtitle_translation/add" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id_list": [<VIDEO_ID>],
    "video_name_list": ["<VIDEO_NAME>"],
    "target_lang": "zh",
    "emphasize_dst": "<TERMS_OR_EMPTY_STRING>"
  }'
```

Successful response:

```json
{"success": true, "message": "Translation tasks queued for 1 videos"}
```

Poll the same `/api/tasks/subtitle_generate/status` endpoint by video ID.

### Step 5: Retry or delete subtitle tasks

Retry a task:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/tasks/subtitle_generate/<VIDEO_ID>/retry" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Delete a task:

```bash
curl -s -X DELETE "$VIDGO_API_BASE/api/tasks/subtitle_generate/<VIDEO_ID>/delete" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Some clients cannot send `DELETE`; this backend also accepts `POST` for delete:

```bash
curl -s -X POST "$VIDGO_API_BASE/api/tasks/subtitle_generate/<VIDEO_ID>/delete" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

### Step 6: Verify subtitle files through summary prerequisites

Before running `video-summary-ask`, verify the video now has subtitles:

```bash
FILENAME='<FILENAME>'
ENC_FILENAME=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$FILENAME")

curl -s "$VIDGO_API_BASE/api/video-summary/$ENC_FILENAME/prerequisites" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN"
```

Proceed to summary only when `status` is `ok`.

## Error Handling

- `400 Missing "video_id_list" field`: provide a non-empty `video_id_list`.
- `400 Missing "video_name_list"`: provide names with the same count and order as `video_id_list`.
- `400 Invalid target language`: use `zh`, `en`, `jp`, or `de`.
- `400 Original subtitle not found...`: generate original subtitles before translation-only mode.
- `404 Video with ID <id> not found`: search videos again and use a valid video ID.
- `Task not found` on retry/delete: check `/api/tasks/subtitle_generate/status`; the task may have never been queued or may have been deleted.

## Important Notes

- Subtitle generation has no independent task ID; use the numeric `video_id` as the polling key.
- The status endpoint has no top-level `status`; inspect `stages`.
- Stages are `transcribe`, `optimize`, and `translate`.
- Stage values can be `Queued`, `Running`, `Completed`, `Failed`, or `Skipped`.
- The backend updates `raw_lang` when `src_lang` is one of `zh`, `en`, `jp`, or `de`.
- For summary workflows, generate subtitles first, verify prerequisites, then use `video-summary-ask`.
