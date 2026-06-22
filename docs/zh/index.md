# VideoMiner 文档

## 部署

| 文档 | 内容 |
| --- | --- |
| [Docker 部署](deployment.md) | 使用预编译镜像部署，包含 docker-compose、端口配置、数据持久化、GPU 参数和代理设置。 |
| [从零编译镜像](build-from-scratch.md) | 多阶段构建说明、自定义镜像源、docker-compose 本地编译、镜像瘦身。 |

## 设置章节

| 章节 | 内容 |
| --- | --- |
| [模型设置](model/) | 断句 LLM (Split LLM) 与翻译 LLM (Translate LLM) 的供应商、密钥、模型名、并发和代理设置。 |
| [界面设置](interface/) | 界面语言与默认译文字幕语言。 |
| [字幕设置](subtitle/) | 原文字幕和译文字幕的字体、颜色、背景、阴影、描边和预览。 |
| [转录引擎](transcription/) | 音频转录引擎、热词表、VAD 后端和 ElevenLabs 密钥。 |
| [媒体凭据](media/) | B站 SESSDATA、YouTube cookies.txt、网络代理和 yt-dlp 管理。 |
| [API 令牌](api-token/) | Agent 和 CLI 访问 Video-Miner API 的令牌创建、查看和吊销。 |
| [视频理解](video-understanding/) | 本地模型下载、推理参数、角点检测、摘要编排和知识补充 LLM。 |
| [标签管理](tags/) | 标签创建、颜色、编辑、删除和批量删除。 |

> 设置保存后会写入后端配置。涉及 API Key、SESSDATA、cookies.txt 和令牌的值都应按密码保管。
