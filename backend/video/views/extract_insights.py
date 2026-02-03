"""
实时转录内容的智能分析 - 待办事项和关键要点提取

使用 LLM (DeepSeek) 从转录文本中提取：
- 待办事项 (Action Items)
- 关键要点 (Key Points/Mentions)
"""
import json
import logging
import openai
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from video.views.set_setting import load_all_settings

logger = logging.getLogger('vidgo')

# LLM 提示词模板
EXTRACT_INSIGHTS_PROMPT = """你是一个专业的会议记录助手。请分析以下文本内容，提取其中的关键信息。

分析内容：
{text}

请按照以下JSON格式返回结果（不要添加任何markdown代码块标记）：
{{
  "todos": [
    "待办事项1",
    "待办事项2"
  ],
  "mentions": [
    "关键要点1",
    "关键要点2"
  ]
}}

提取规则：
1. **待办事项 (todos)**：
   - 明确提到需要执行的任务、行动或计划
   - 包含"需要"、"应该"、"必须"、"记得"、"TODO"等关键词的句子
   - 具体的工作安排、决策事项
   - 限制在8条以内，优先提取最重要的

2. **关键要点 (mentions)**：
   - 重要的观点、结论或见解
   - 被提及的人物、组织、技术或概念
   - 值得记录的信息点
   - 讨论的核心话题
   - 限制在6条以内，优先提取最核心的

注意：
- 只返回纯JSON格式，不要添加```json或其他标记
- 如果某类内容不存在，返回空数组[]
- 保持原文语言（中文或英文）
- 提取内容要简洁、准确、有价值
"""


@csrf_exempt
@require_http_methods(["POST"])
def extract_insights(request):
    """
    从文本中提取待办事项和关键要点

    Request body (JSON):
    {
        "text": "要分析的文本内容",
        "language": "zh"  // 可选，zh或en
    }

    Response:
    {
        "success": true,
        "data": {
            "todos": ["待办事项1", "待办事项2"],
            "mentions": ["关键要点1", "关键要点2"]
        }
    }
    """
    try:
        # 解析请求
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        language = data.get('language', 'zh')

        if not text:
            return JsonResponse({
                'success': False,
                'error': '文本内容不能为空'
            }, status=400)

        # 加载配置
        settings = load_all_settings()

        # 从 DEFAULT 部分获取 LLM 配置
        default_cfg = settings.get('DEFAULT', {})
        api_key = default_cfg.get('deepseek_api_key', '')
        base_url = default_cfg.get('deepseek_base_url', 'https://api.deepseek.com')
        model = 'deepseek-chat'

        logger.debug(f"[Extract Insights] API Key loaded: {api_key[:20]}..." if api_key else "[Extract Insights] No API key found")

        if not api_key or api_key == 'sk-your-deepseek-api-key-here':
            return JsonResponse({
                'success': False,
                'error': 'DeepSeek API 密钥未配置，请在设置中配置'
            }, status=500)

        logger.info(f"[Extract Insights] Processing text length: {len(text)} chars, language: {language}")

        # 调用 LLM
        client = openai.OpenAI(api_key=api_key, base_url=base_url)

        prompt = EXTRACT_INSIGHTS_PROMPT.format(text=text)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个专业的内容分析助手，擅长从文本中提取关键信息。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # 较低的温度以获得更稳定的结果
            max_tokens=2048
        )

        result_text = response.choices[0].message.content
        logger.debug(f"[Extract Insights] Raw LLM response: {result_text[:200]}...")

        # 清理可能的 markdown 代码块标记
        result_cleaned = result_text.strip()
        if result_cleaned.startswith("```json"):
            result_cleaned = result_cleaned[7:]
        elif result_cleaned.startswith("```"):
            result_cleaned = result_cleaned[3:]
        if result_cleaned.endswith("```"):
            result_cleaned = result_cleaned[:-3]
        result_cleaned = result_cleaned.strip()

        # 解析 JSON
        try:
            insights = json.loads(result_cleaned)
            todos = insights.get('todos', [])
            mentions = insights.get('mentions', [])

            logger.info(f"[Extract Insights] Extracted {len(todos)} todos and {len(mentions)} mentions")

            return JsonResponse({
                'success': True,
                'data': {
                    'todos': todos,
                    'mentions': mentions
                }
            })

        except json.JSONDecodeError as e:
            logger.error(f"[Extract Insights] JSON parsing failed: {e}")
            logger.error(f"[Extract Insights] Cleaned response: {result_cleaned[:500]}")

            # 尝试从文本中提取基本信息（降级方案）
            return JsonResponse({
                'success': False,
                'error': f'LLM 返回格式解析失败: {str(e)}'
            }, status=500)

    except Exception as e:
        logger.error(f"[Extract Insights] Error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
