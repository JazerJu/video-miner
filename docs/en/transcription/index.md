# Transcription Engine

Transcription Engine settings control the backend used to convert audio to text. The current settings panel provides local Fun-ASR-GGUF (broad general use), local GLM-ASR Stack (500+ RTFx, ultra-fast transcription), and ElevenLabs Speech-to-Text (API, expensive, about $0.05/min).

## Basic settings

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Transcription Engine | Select | Fun-ASR-Nano (ONNX + GGUF, Local GPU Acceleration) | Options are Fun-ASR-Nano, GLM-ASR Stack, and ElevenLabs Speech-to-Text. |
| Hotword List | Textarea | Empty | One hotword per line. Lines starting with `#` are comments. |
| VAD Backend | Select | Silero VAD | Options are Silero VAD or FireRed VAD. |

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

> Credits: The engine integration and hotword transcription in this project refer to work from the Fun-ASR team and HaujetZhao's Fun-ASR-GGUF.
> https://github.com/FunAudioLLM/Fun-ASR
> https://github.com/HaujetZhao/Fun-ASR-GGUF

## How to choose an engine

1. Prefer a local engine, Fun-ASR or GLM-ASR, for audio processing.
2. Choose ElevenLabs only when you strongly need a cloud service, then enter an API key.
3. If voice activity detection is not accurate enough, switch between Silero VAD and FireRed VAD.

---

[Back to English docs](../) | [Previous: Subtitle Settings](../subtitle/) | [Next: Media Credentials](../media/)
