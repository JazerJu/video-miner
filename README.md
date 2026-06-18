![Latest stable](https://img.shields.io/github/v/release/JazerJu/video-miner?display_name=tag) [![CI](https://github.com/JazerJu/video-miner/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/JazerJu/video-miner/actions/workflows/ci.yml) [![Codecov](https://codecov.io/gh/JazerJu/video-miner/graph/badge.svg?branch=main)](https://codecov.io/gh/JazerJu/video-miner)

# VideoMiner

VidGo是一个专为NAS用户和小型团队设计的本地视频管理平台，提供完整的视频内容管理解决方案。

项目提供[示例网站](https://example.vidgo.cemp.top/)供用户测试使用。

部署和使用中的问题可参考[项目文档](https://doc.vidgo.cemp.top/)。

# 核心功能

**📥1.流媒体视频下载**
- 支持Bilibili、YouTube、Apple Podcasts等主流平台的音视频下载  
- 🔗提供外链解析和批量下载功能 

**🎬2.智能字幕系统**

- 🎙️多引擎转录支持：Faster-Whisper本地处理、ElevenLabs、阿里巴巴DashScope、OpenAI Whisper提供的APi服务
- ✂️ 基于 LLM 的智能分割与断句，字幕阅读更自然流畅
- ⚡支持批量运行任务，提升效率
- ✏️高级字幕编辑器，支持实时预览，自定义字幕样式
    - 🌊 支持音频波形展示&同步
    - 🌐支持双语字幕/字幕嵌入视频导出

**📚3.视频管理与组织**
- 📁分类和合集管理系统 
- ⚙️批量操作支持（移动、删除、字幕生成、视频合并）
- 🖼️ 缩略图管理

**👥4.用户认证和权限管理**
- 👤主用户/普通用户分离
- 🔐可单独为普通用户设置权限与分类展示。

**▶️5.视频播放体验**
- ▶️在线播放视频
- 📺集成字幕显示面板
- 🎯章节导航和时间轴跳转
- 🔄双语字幕切换和自动滚动 

# 界面预览
![概览](https://doc.vidgo.cemp.top/assets/images/overview-6abee6dae72e659c5837d798dd0090a2.png)


> 项目架构为前后端分离的Vue3 + django api



# 快速开始
项目提供示例网站，地址为https://example.vidgo.cemp.top ，需要输入用户名&密码。

用户名:**user**,

密码:**User123**.

示例网站暂不支持基于本地的字幕识别，但支持基于云端的字幕识别，此外可以体验视频观看，字幕编辑等功能。
部署和使用中的问题可以参考[项目文档](https://doc.vidgo.cemp.top/).

# 部署
项目支持以下两种方式部署：
1. node + python
2. Docker部署

## Node + python部署
```
git clone https://github.com/your-org/vidgo.git
cd vidgo

#  修改 .ini 文件
cp ./backend/config/config.ini.example ./backend/config/config.ini.

# 安装前端依赖
cd frontend
npm install
npm run start # 可以调整前端运行端口，默认为4173。
# frontend/.env记录前后端交互时后端api所用端口，默认为8000,若后端因端口冲突，可以修改该文件以匹配后端。

# 另开终端运行后端
cd ../backend
conda create -n vidgo-env python=3.10
conda activate vidgo-env  # 或你自定义的虚拟环境
pip install -r requirements.txt. # 安装其他依赖
pip install faster_whisper # 安装faster_whisper
bash run_all.sh # 运行后端服务
```


## Docker快速部署
```
sudo docker pull jaceju68/vidgo:latest

sudo docker run -d --name vidgo \
  --restart unless-stopped \
  --gpus '"device=0"' \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e WHISPER_DEVICE=cuda \
  -p 8030:8000 \
  -v "$(pwd)/data/videos.db:/app/database/videos.db" \
  -v "$(pwd)/data/media:/app/media" \
  -v "$(pwd)/data/config:/app/config" \
  -v "$(pwd)/data/models:/app/models" \
  jaceju68/vidgo:latest
```

项目同时支持采用docker-compose.yml部署，默认使用GPU，

[示例文件](https://github.com/JaceJu-frog/vidgo/blob/main/docker-compose.yml)


# 未来规划
- [ ] 增加模糊搜索，匹配与用户搜索内容相近的项目
- [ ] 优化字幕编辑页面的"音频展示"，使UI更现代化。
- [ ] 增加Ai生成视频笔记，视频思维导图，视频章节的功能。
- [ ] 支持更多的WSR模型，包括剪映提供的高准确度模型。
- [ ] 支持更多的LLM模型
