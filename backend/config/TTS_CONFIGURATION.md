# TTS (Text-to-Speech) Configuration Guide

## Audio Clone Feature (New)

VidGo now supports audio cloning, allowing you to create custom voice models by uploading reference audio files. This feature uses Alibaba Cloud's DashScope Voice Enrollment Service to generate personalized TTS voiceovers.

## Overview

VidGo's TTS feature uses Alibaba Cloud's **CosyVoice-v2** model to generate natural-sounding voiceovers from subtitle files and merge them with your videos.

## Prerequisites

1. **Alibaba Cloud Account**: Sign up at https://www.aliyun.com
2. **DashScope API Key**: Get your key from https://dashscope.console.aliyun.com/apiKey
3. **Subtitle File**: Generate subtitles for your video first using VidGo's subtitle generation feature
4. **Aliyun OSS Configuration** (for Audio Clone): Configure OSS credentials for audio file storage

## Configuration Steps

### 1. Get Your API Key

1. Visit https://dashscope.console.aliyun.com/apiKey
2. Click "Create API Key" or copy an existing one
3. Save the key securely (format: `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

### 2. Configure VidGo

#### Option A: Via Web Interface (Recommended)

1. Open VidGo in your browser
2. Go to **Settings** → **TTS Settings**
3. Paste your DashScope API key
4. Select your preferred voice (default: `longxiaochun_v2`)
5. For Audio Clone feature, also configure OSS settings in **Settings** → **OSS Service**
6. Click "Save"

#### Option B: Via Configuration File

1. Edit `backend/config/config.ini`
2. Add or update the `[TTS settings]` section:

```ini
[TTS settings]
dashscope_api_key = sk-your-actual-api-key-here
default_voice = longxiaochun_v2
default_model = cosyvoice-v2
```

3. For Audio Clone feature, also add the `[OSS Service]` section:

```ini
[OSS Service]
oss_access_key_id = your_aliyun_access_key_id
oss_access_key_secret = your_aliyun_access_key_secret
oss_endpoint = oss-cn-beijing.aliyuncs.com
oss_bucket = vidgo-test
oss_region = cn-beijing
```

4. Save and restart the server

### 3. Available Voice Models

CosyVoice-v2 offers multiple voices:

| Voice ID | Description | Language | Gender |
|----------|-------------|----------|--------|
| `longxiaochun_v2` | Long Xiaochun | Chinese | Female |
| `longyueyue_v2` | Long Yueyue | Chinese | Female |
| `longaoxue_v2` | Long Aoxue | Chinese | Female |
| `longjingyu_v2` | Long Jingyu | Chinese | Male |
| `longzetao_v2` | Long Zetao | Chinese | Male |

For the full list, visit: https://help.aliyun.com/zh/model-studio/cosyvoice-v2-api

## Usage

### Generate TTS Voiceover

1. **Ensure subtitle exists**:
   - Your video must have subtitles in the target language
   - Example: For Chinese TTS, you need `{video_id}_zh.srt`

2. **Start TTS task**:
   - API: `POST /api/tts/generate/<video_id>`
   - Request body:
   ```json
   {
     "language": "zh",
     "voice": "longxiaochun_v2"
   }

3. **Monitor progress**:
   - Check the **Tasks** page in VidGo
   - Progress shows: Queued → Running → Completed/Failed
   - Real-time segment count displayed (e.g., "5/10 segments")

4. **Output**:
   - Generated video: `work_dir/tts_output/{md5}_{language}.mp4`
   - Original video audio is replaced with synthesized speech
   - Video quality preserved (copy mode, no re-encoding)

### Generate TTS with Audio Clone

1. **Prepare reference audio**:
   - Format: WAV, MP3, or M4A
   - Duration: 10-20 seconds recommended (minimum 5 seconds of continuous speech)
   - Size: Maximum 10MB

2. **Upload audio and generate TTS**:
   - In the TTS dialog, enable "使用自定义音色"
   - Click "选择音频文件" to upload your reference audio
   - Optionally enter reference text for better voice cloning
   - Select language and click "生成"

3. **Monitor progress**:
   - The system will first create a voice model from your audio
   - Then generate TTS using the cloned voice
   - Progress shows both voice cloning and TTS generation steps

## Pricing & Limits

### Alibaba Cloud DashScope

- **Free Tier**: 1 million characters/month (check current limits)
- **Paid Tier**: ~¥0.03/1000 characters
- **Rate Limit**: 500ms between requests (handled automatically)

Visit https://dashscope.console.aliyun.com for current pricing

## Troubleshooting

### Error: "DashScope API key not configured"

**Solution**: Configure `dashscope_api_key` in settings (see Configuration Steps)

### Error: "no subtitle for this video"

**Solution**: Generate subtitles first:
1. Go to video details
2. Click "Generate Subtitles"
3. Select source language
4. Wait for completion
5. Then try TTS again

### Error: "Audio preprocessing failed"

**Solution**:
- Check if FFmpeg is installed: `ffmpeg -version`
- Ensure video file exists and is accessible
- Check file permissions

### TTS task stuck at "Running"

**Solution**:
- Check backend logs: `tail -f backend/logs/vidgo.log`
- Verify API key is valid
- Check network connectivity to Alibaba Cloud
- Retry the task from Tasks page

### Audio Clone Specific Errors

#### Error: "OSS credentials not configured"

**Solution**: Configure OSS credentials in settings (see Configuration Steps)

#### Error: "Invalid file type" when uploading audio

**Solution**: Use WAV, MP3, or M4A format only

#### Error: "File size exceeds 10MB limit"

**Solution**: Compress or trim your audio file to under 10MB

#### Error: "Failed to create voice model"

**Solution**:
- Check audio quality (clear speech, minimal background noise)
- Ensure audio contains at least 5 seconds of continuous speech
- Verify DashScope API key is valid
- Check backend logs for detailed error information

## Technical Details

### Pipeline

1. **Load Subtitles**: Read SRT file (`media/saved_srt/{video_id}_{language}.srt`)
2. **Segment Merging**: Combine short segments (max 15s, 50 words) to optimize API calls
3. **TTS Synthesis**: Call CosyVoice-v2 API for each segment
4. **Audio Assembly**: Merge segments with crossfade and silence insertion
5. **Video Merging**: Replace video audio track using FFmpeg

### Cache System

- **Location**: `work_dir/tts_cache/`
- **Format**: WAV files named by MD5 hash
- **Key**: `MD5(text + voice + model)`
- **Benefit**: Reuse audio for identical text segments

### Performance

- **Speed**: ~1-2x real-time (depends on network and segment count)
- **Memory**: ~500MB peak during processing
- **Disk**: Temp files cleaned automatically

## Support

For issues or questions:
- GitHub Issues: https://github.com/jaceju68/vidgo/issues
- Documentation: https://github.com/jaceju68/vidgo/wiki
