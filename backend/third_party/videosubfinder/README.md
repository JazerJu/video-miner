# VideoSubFinder（Linux 命令行版）

硬字幕提取用它找「字幕出现、换句、消失」的时间区间，不做文字识别。调用封装在
`backend/utils/hardsub/vsf.py`。

## 二进制不在仓库里

`VideoSubFinderCli` 有 45 MB，静态链接，不依赖系统库。它放在两个地方，内容是同一个文件：

| 位置 | 给谁用 |
| --- | --- |
| 模型仓库 `JazerJu/VideoMiner`、`modelmo/VideoMiner` 的 `videosubfinder/` | 源码安装：在设置页下载模型组「videosubfinder」，文件会落到本目录 `linux/` 下 |
| 载体镜像 `jaceju68/videosubfinder:vse-2.2.0` | Docker 镜像构建时 `COPY --from` 取用，构建步骤见 `docker/videosubfinder/` |

- **sha256：**`2d9e4bc170408eee05326094b4fc89f0c79b017d7a3ba2e767801c8adb2e85fa`（47,121,988 字节）。
  下载和镜像构建都会核对这个值。
- **来源：**video-subtitle-extractor 2.2.0 的 `backend/subfinder/linux/`，原样拷贝。
- **上游：**https://sourceforge.net/projects/videosubfinder/ （作者 Simeon Kosnitsky），项目页标注 GPLv2。
  许可证原文和上游源码快照（`c3d19ab`，2023-04-25）与二进制放在同一个模型仓库目录下。

## 目录里的其他文件

- `linux/VideoSubFinderCli.run`：启动脚本，会 `cd` 到本目录并给二进制加执行位。`vsf.py` 用 `sh` 调它。
- `linux/settings/general.cfg`：程序读的参数，其中 `sub_frame_length = 6` 决定一句字幕至少要持续几帧。
- 程序运行时会在本目录写 `report.log`，所以这个目录要可写。该文件已被 git 忽略。
