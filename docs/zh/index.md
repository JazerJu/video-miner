# VideoMiner 设置文档

本页汇总 VideoMiner 设置面板中的各项配置。内容按设置页签拆分，适合管理员按需查阅，也适合部署后作为 GitHub Pages 文档发布。

## 设置章节

| 章节 | 内容 |
| --- | --- |
| [模型设置](model/) | 断句 LLM (Split LLM) 与翻译 LLM (Translate LLM) 的供应商、密钥、模型名、并发和代理设置。 |
| [界面设置](interface/) | 界面语言与默认译文字幕语言。 |
| [字幕设置](subtitle/) | 原文字幕和译文字幕的字体、颜色、背景、阴影、描边和预览。 |
| [转录引擎](transcription/) | 音频转录引擎、热词表、VAD 后端和 ElevenLabs 密钥。 |
| [媒体凭据](media/) | B站 SESSDATA、YouTube cookies.txt、网络代理和 yt-dlp 管理。 |
| [API 令牌](api-token/) | Agent 和 CLI 访问 VidGo API 的令牌创建、查看和吊销。 |
| [视频理解](video-understanding/) | 本地模型下载、推理参数、角点检测、摘要编排和知识补充 LLM。 |
| [标签管理](tags/) | 标签创建、颜色、编辑、删除和批量删除。 |

> 设置保存后会写入后端配置。涉及 API Key、SESSDATA、cookies.txt 和令牌的值都应按密码保管。

[返回总首页](../) | [下一节：模型设置](model/)
