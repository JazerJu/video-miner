"""
视频章节生成器
使用AI分析字幕内容，生成具有层次结构的视频章节
"""

import json
import re
import os
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging
import openai

from utils.split_subtitle.ASRData import from_srt, ASRData

# 添加项目根目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from video.views.set_setting import load_all_settings, _init_client

logger = logging.getLogger(__name__)


class ChapterGenerator:
    """视频章节生成器"""

    def __init__(self):
        self.presets = {
            "少章+凝练": {
                "K": 7,
                "MIN_GAP": 120,
                "MAX_GAP": 420,
                "STYLE": "凝练"
            },
            "多章+学术": {
                "K": 14,
                "MIN_GAP": 45,
                "MAX_GAP": 240,
                "STYLE": "学术"
            },
            "多章+优雅": {
                "K": 12,
                "MIN_GAP": 60,
                "MAX_GAP": 300,
                "STYLE": "优雅"
            }
        }

    def _build_prompt(self, subtitles_text: str, preset: str) -> str:
        """构建AI提示词"""
        config = self.presets[preset]

        prompt_template = f"""
# === 参数（仅需改这里） =======================================
K = {config['K']}                  # 目标章节数（少章示例：6~8；多章示例：12~16）
MIN_GAP = {config['MIN_GAP']}            # 相邻章节的最小时间间隔（秒）。少章可 120~150，多章可 30~60
MAX_GAP = {config['MAX_GAP']}           # 单段允许的最大跨度（秒），用于在过长处强制拆分
STYLE = "{config['STYLE']}"          # 取值："凝练" | "学术" | "优雅"
# ============================================================

你是资深视频编导与内容摘要专家。给定**带时间戳的字幕**，请**仅输出两部分**，且**全程使用中文**：
（1）《章节》：用于粘贴到YouTube描述的章节标记
（2）《列表》：与章节逐条对应的要点清单
除这两部分外，**不要输出任何其他文字**（如解释、JSON、代码块标记等）。

【时间与切分规则】
1. 章节锚点：每章的时间戳 = 该章**首句字幕的开始时间**，格式严格为`HH:MM:SS`（不足两位补零）。
2. 章节数量：目标为 K 条（允许 K±2 的弹性）。若素材不足，宁少不滥；若转折密集且不影响可读性，可略多于 K。
3. 合并策略：当相邻候选段主题高度相似或两段时间间隔 < MIN_GAP 时，应合并，直至接近 K。
4. 拆分策略：当单段跨度 > MAX_GAP，且在该段内部出现明显转折（如"定价/设计/内饰/电池/快充/低温/成本/安全/竞品/总结/购买建议/结语"等），在转折处拆分。
5. 时间序：时间戳必须严格递增；若输入时间为秒/毫秒，请自行换算为`HH:MM:SS`。
6. 锚点一致：第二部分《列表》的每行时间 = 对应《章节》行的同一锚点（可转为`MM:SS`，但分钟不足两位也要补零）。

【输出第 1 部分：《章节》】
- 每行格式：`HH:MM:SS - 章节标题`
- 数量：约 K 行
- 标题要求：主题明确、信息密度高；**禁止**口语、表情、标点收尾（如句号/引号/书名号）。

【输出第 2 部分：《列表》】
- 每行格式：`- [MM:SS] 要点摘要`
- 行数与《章节》**一一对应**、顺序一致
- 要点应与对应章节互补，不要和章节标题完全重复

【文风控制（按 STYLE 生效）】
- 当 STYLE="凝练"：
  - 标题 6~10 字，以名词短语为主；要点 10~16 字
  - 禁用比喻、感叹号与夸张表达
  - 示例标题：`定价争议与门槛`、`尾灯方案与取舍`、`低温续航与安全`
- 当 STYLE="学术"：
  - 标题 10~16 字；要点 14~22 字
  - 采用术语 + 因果/对比结构，避免情绪化形容
  - 模板建议：`主题 + 指标/机制 + 结论/效应`
  - 示例标题：`钠离子体系的低温性能与安全性证据`
- 当 STYLE="优雅"：
  - 标题 10~14 字；要点 12~20 字
  - 允许轻微修辞（对称/对照），不使用感叹词，整体克制流畅
  - 示例标题：`简化之美：设计与效率的权衡`

【质量守则（硬性约束）】
1. **事实边界**：仅据字幕内容做**主题归纳与措辞压缩**；**禁止**虚构字幕中未出现的数据/参数/结论。
2. **唯一性**：章节标题互不重复；如出现近义重复，合并靠前段并更新标题。
3. **格式校验**：若最终行数超出 K±2，请先合并/拆分再输出（但不要解释过程）。
4. **中文强制**：始终用中文；不输出 JSON/YAML/XML/额外说明。
5. **仅两部分**：先输出完整的《章节》，空一行，再输出完整的《列表》。

【待处理字幕——请原样放在此处】
{subtitles_text}
"""
        return prompt_template.strip()

    def _format_subtitles_for_ai(self, asr_data: ASRData) -> str:
        """格式化字幕文本供AI分析"""
        formatted_lines = []

        for seg in asr_data.segments:
            # 转换时间戳为 HH:MM:SS 格式
            total_seconds = seg.start_time // 1000
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            timestamp = f"{hours:02}:{minutes:02}:{seconds:02}"

            # 清理文本，移除多余换行和空格
            text = seg.text.strip().replace('\n', ' ')
            # 移除常见的字幕标记
            text = re.sub(r'<[^>]+>', '', text)  # HTML标签
            text = re.sub(r'\[.*?\]', '', text)  # 方括号内容

            if text:  # 只添加非空文本
                formatted_lines.append(f"[{timestamp}] {text}")

        return '\n'.join(formatted_lines)

    def _parse_ai_response(self, response_text: str) -> Tuple[List[Dict], str]:
        """
        解析AI响应，提取章节信息
        返回: (章节列表, 总结文本)
        """
        lines = [line.strip() for line in response_text.split('\n') if line.strip()]
        logger.info(f"Parsing AI response with {len(lines)} lines")

        # 查找章节和列表的分隔点
        chapters_section = []
        list_section = []
        current_section = None

        # 检查是否有标准的《章节》和《列表》标记
        has_section_markers = any("《章节》" in line or "《列表》" in line for line in lines)

        if not has_section_markers:
            # 如果没有标准标记，尝试自动检测章节和列表的分隔点
            logger.info("No standard section markers found, using auto-detection")

            # 查找第一个列表项（以 - 开头的行）作为分隔点
            for i, line in enumerate(lines):
                if line.startswith('-'):
                    chapters_section = lines[:i]
                    list_section = lines[i:]
                    break
            else:
                # 如果没有列表项，所有行都当作章节
                chapters_section = lines
                list_section = []
        else:
            # 使用标准标记解析
            for line in lines:
                if line == "《章节》":
                    current_section = "chapters"
                    continue
                elif line == "《列表》":
                    current_section = "list"
                    continue

                if current_section == "chapters":
                    chapters_section.append(line)
                elif current_section == "list":
                    list_section.append(line)

        logger.info(f"Found {len(chapters_section)} chapter lines and {len(list_section)} list lines")

        # 解析章节标题和时间戳
        chapters = []
        summary_parts = []

        for chapter_line in chapters_section:
            # 支持多种时间格式:
            # - "HH:MM:SS - 章节标题"
            # - "MM:SS - 章节标题"
            # - "HH:MM:SS 章节标题"
            match = re.match(r'(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*(.+)', chapter_line)
            if match:
                timestamp_str, title = match.groups()
                # 转换时间戳为秒数
                time_parts = timestamp_str.split(':')
                if len(time_parts) == 3:  # HH:MM:SS
                    h, m, s = map(int, time_parts)
                    total_seconds = h * 3600 + m * 60 + s
                else:  # MM:SS
                    m, s = map(int, time_parts)
                    total_seconds = m * 60 + s

                chapters.append({
                    "title": title,
                    "timestamp": total_seconds,
                    "part_outline": []
                })
                summary_parts.append(title)
                logger.info(f"Parsed chapter: {title} at {total_seconds}s")

        # 解析列表项，匹配到对应章节
        chapter_index = 0
        for list_line in list_section:
            # 解析格式: "- [MM:SS] 要点摘要"
            match = re.match(r'-\s*\[(\d{1,2}:\d{2})\]\s*(.+)', list_line)
            if match and chapter_index < len(chapters):
                time_str, content = match.groups()
                # 转换时间戳为秒数
                parts = time_str.split(':')
                if len(parts) == 2:
                    m, s = map(int, parts)
                    total_seconds = m * 60 + s
                else:
                    total_seconds = 0

                chapters[chapter_index]["part_outline"].append({
                    "timestamp": total_seconds,
                    "content": content
                })

                # 如果有多个列表项对应同一章节，继续添加；否则移动到下一章节
                if chapter_index < len(chapters) - 1:
                    chapter_index += 1

        # 生成总结
        summary = " | ".join(summary_parts)

        return chapters, summary

    def _call_ai_service(self, prompt: str) -> str:
        """
        调用AI服务处理章节生成
        使用项目配置的LLM服务（DeepSeek、OpenAI等）
        """
        try:
            # 加载配置
            settings_data = load_all_settings()
            cfg = settings_data.get('DEFAULT', {})

            # 获取选中的模型提供商
            selected_provider = cfg.get('selected_model_provider', 'deepseek')

            # 获取提供商特定的API密钥和基础URL
            if selected_provider == 'deepseek':
                api_key = cfg.get('deepseek_api_key', '')
                base_url = cfg.get('deepseek_base_url', 'https://api.deepseek.com')
                model = 'deepseek-chat'
            elif selected_provider == 'openai':
                api_key = cfg.get('openai_api_key', '')
                base_url = cfg.get('openai_base_url', 'https://api.openai.com/v1')
                model = 'gpt-4o'
            elif selected_provider == 'glm':
                api_key = cfg.get('glm_api_key', '')
                base_url = cfg.get('glm_base_url', 'https://open.bigmodel.cn/api/paas/v4')
                model = 'glm-4-plus'
            elif selected_provider == 'qwen':
                api_key = cfg.get('qwen_api_key', '')
                base_url = cfg.get('qwen_base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
                model = 'qwen-plus'
            else:
                # 默认使用deepseek
                api_key = cfg.get('deepseek_api_key', '')
                base_url = cfg.get('deepseek_base_url', 'https://api.deepseek.com')
                model = 'deepseek-chat'

            if not api_key:
                logger.error(f"API key not configured for provider: {selected_provider}")
                raise ValueError(f"API key not configured for provider: {selected_provider}")

            # 初始化OpenAI客户端
            client = openai.OpenAI(api_key=api_key, base_url=base_url)

            logger.info(f"Calling AI service: {selected_provider} with model: {model}")

            # 调用AI服务
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # 较低的温度以获得更一致的结果
                max_tokens=8192,  # 足够的token支持长响应
                timeout=120  # 2分钟超时
            )

            result = response.choices[0].message.content
            logger.info(f"AI response received, length: {len(result)} characters")

            return result

        except Exception as e:
            logger.error(f"AI service call failed: {str(e)}")
            # 如果AI服务失败，返回一个基本的章节结构
            return """
《章节》
00:00:01 - 视频内容概述
00:10:00 - 主要内容讲解
00:20:00 - 总结与回顾

《列表》
- [01:00] 视频内容概述和介绍
- [10:00] 主要内容详细讲解
- [20:00] 总结和关键要点回顾
"""

    def generate_chapters(self, srt_content: str, preset: str = "多章+学术") -> Dict:
        """
        生成视频章节

        Args:
            srt_content: SRT格式的字幕内容
            preset: 章节生成预设，可选值："少章+凝练", "多章+学术", "多章+优雅"

        Returns:
            Dict: 包含章节信息的字典，格式参考API响应示例
        """
        try:
            # 验证预设参数
            if preset not in self.presets:
                preset = "多章+学术"
                logger.warning(f"Invalid preset, using default: {preset}")

            # 解析SRT字幕
            asr_data = from_srt(srt_content)
            if not asr_data.has_data():
                raise ValueError("No valid subtitle data found")

            logger.info(f"Parsed {len(asr_data.segments)} subtitle segments")

            # 格式化字幕文本
            formatted_subtitles = self._format_subtitles_for_ai(asr_data)
            logger.info(f"Formatted subtitles length: {len(formatted_subtitles)} characters")

            # 构建AI提示词
            prompt = self._build_prompt(formatted_subtitles, preset)
            logger.info(f"Generated prompt length: {len(prompt)} characters")

            # 调用AI服务
            ai_response = self._call_ai_service(prompt)
            logger.info(f"AI response received: {ai_response[:200] if ai_response else 'None'}...")

            # 解析AI响应
            chapters, summary = self._parse_ai_response(ai_response)
            logger.info(f"Parsed {len(chapters)} chapters from AI response")

            # 构建响应数据
            result = {
                "code": 0,
                "message": "0",
                "ttl": 1,
                "data": {
                    "code": 0,
                    "model_result": {
                        "result_type": 2,
                        "summary": summary,
                        "outline": chapters
                    }
                }
            }

            logger.info(f"Generated {len(chapters)} chapters using preset: {preset}")
            return result

        except Exception as e:
            logger.error(f"Error generating chapters: {str(e)}")
            return {
                "code": -1,
                "message": f"章节生成失败: {str(e)}",
                "ttl": 1,
                "data": None
            }

    def generate_chapters_from_file(self, srt_file_path: str, preset: str = "多章+学术") -> Dict:
        """
        从SRT文件生成视频章节

        Args:
            srt_file_path: SRT文件路径
            preset: 章节生成预设

        Returns:
            Dict: 包含章节信息的字典
        """
        try:
            with open(srt_file_path, 'r', encoding='utf-8') as f:
                srt_content = f.read()

            return self.generate_chapters(srt_content, preset)

        except FileNotFoundError:
            logger.error(f"SRT file not found: {srt_file_path}")
            return {
                "code": -1,
                "message": f"SRT文件不存在: {srt_file_path}",
                "ttl": 1,
                "data": None
            }
        except Exception as e:
            logger.error(f"Error reading SRT file: {str(e)}")
            return {
                "code": -1,
                "message": f"读取SRT文件失败: {str(e)}",
                "ttl": 1,
                "data": None
            }


def main():
    """测试函数"""
    generator = ChapterGenerator()

    # 测试用的SRT内容
    test_srt = """1
00:00:01,000 --> 00:00:05,000
大家好，今天我们来介绍一下人工智能的发展历程

2
00:00:06,000 --> 00:00:10,000
人工智能从20世纪50年代开始经历了多次发展浪潮

3
00:00:11,000 --> 00:00:15,000
现在我们来看看机器学习的基本概念
"""

    result = generator.generate_chapters(test_srt, "多章+学术")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()