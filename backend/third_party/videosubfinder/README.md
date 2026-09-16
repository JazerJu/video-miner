# VideoSubFinder（Linux 命令行版）

硬字幕提取 v12 用它找「字幕出现、换句、消失」的时间区间，不做文字识别。

- 来源：video-subtitle-extractor 2.2.0 自带的预编译二进制 `backend/subfinder/linux/`，原样拷贝
- 上游源码：https://sourceforge.net/p/videosubfinder/src/ （作者 Simeon Kosnitsky）。源码文件头声明为公有领域（不得出售源码），SourceForge 项目页标注 GPLv2
- 静态链接，不依赖系统库；启动脚本会 `cd` 到本目录并写 `report.log`，目录需可写
- 调用封装：`backend/utils/hardsub/vsf.py`
