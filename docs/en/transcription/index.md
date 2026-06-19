# Transcription Engine

Transcription Engine settings choose the backend used to convert audio to text. The current settings panel provides local Fun-ASR-GGUF, local GLM-ASR Stack, and ElevenLabs Speech-to-Text.

## Basic settings

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Transcription Engine | Select | Fun-ASR-Nano (ONNX + GGUF, Local GPU Acceleration) | Options are Fun-ASR-Nano, GLM-ASR Stack, and ElevenLabs Speech-to-Text. |
| Hotword List | Textarea | Empty | One hotword per line. Lines starting with `#` are comments. |
| VAD Backend | Select | Silero VAD | Options are Silero VAD and FireRed VAD. |

## Engine details

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| FunASR-GGUF info | Conditional info block | Shown when Fun-ASR-Nano is selected | Local engine with CTC hard alignment and Qwen3 decoder. It is Chinese optimized, supports character-level CTC timestamps, uses about 1.5GB VRAM, and does not require an API key. |
| ElevenLabs API Key | Password input | Empty | Shown only when ElevenLabs Speech-to-Text is selected. |

## Hotword format

```text
# Names
Obama
CapsWriter
iPhone
```

## How to choose an engine

1. Choose a local engine first for private audio.
2. Choose ElevenLabs for cloud transcription and enter an API key.
3. If voice activity detection is not accurate enough, switch between Silero VAD and FireRed VAD.

> The current settings panel shows only these three transcription engines. Older references to Faster-Whisper, DashScope, or OpenAI are not current panel options.

---

[Back to English docs](../) | [Previous: Subtitle Settings](../subtitle/) | [Next: Media Credentials](../media/)
