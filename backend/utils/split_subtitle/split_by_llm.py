import hashlib
import json
import os,math
import re
import sys
from typing import List, Optional
import openai
import logging
from utils.split_subtitle.cnt_tokens import count_words
from utils.split_subtitle.prompt import VIDEO_SPLIT_PROMPT_TEMPLATE 

# 将项目根目录添加到路径以从video.views.set_setting导入
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger('subtitle_split')
if not logger.handlers:
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 创建文件处理器
    log_file = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'subtitle_split.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # 创建格式器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # 添加处理器到logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)



CACHE_DIR = "cache"



def get_cache_key(text: str, model: str) -> str:
    """
    生成缓存键值
    """
    return hashlib.md5(f"{text}_{model}".encode()).hexdigest()

def get_cache(text: str, model: str) -> Optional[List[str]]:
    """
    从缓存中获取断句结果
    """
    cache_key = get_cache_key(text, model)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            return None
    return None

def set_cache(text: str, model: str, result: List[str]) -> None:
    """
    将断句结果设置到缓存中
    """
    cache_key = get_cache_key(text, model)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
    except IOError:
        pass

def split_by_llm(text: str,
                 use_cache: bool = False,
                 max_length:int = 20,
                 language:str= "en",
                 api_key="sk-your_api_key",
                 base_url="https://api.deepseek.com",
                 model="deepseek-chat") -> List[str]:
    """
    使用LLM进行文本断句
    """
    # if use_cache:
    #     cached_result = get_cache(text, MODEL)
    #     if cached_result:
    #         print(f"[+] 从缓存中获取结果: {cached_result}")
    #         return cached_result
    word_limit=30 # 最大词数限制
    # 初始化OpenAI客户端
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    SYSTEM_PROMPT = f"使用<br>进行段落分割"
    total_word_count = count_words(text)
    logger.info(f"total_word_count: {total_word_count}")
    logger.info(f"Input text length: {len(text)} characters")
    prompt = VIDEO_SPLIT_PROMPT_TEMPLATE.format(
        sentence=text
    )
    print("using model:",model)
    result = None  # 初始化变量以便在异常处理中使用
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=8192  # Ensure sufficient tokens for long responses
        )
        result = response.choices[0].message.content # 获取LLM返回的内容（OpenAI格式）

        # 调试：打印原始响应
        logger.debug(f"[DEBUG] Raw LLM response content: {repr(result)}")

        # 检查响应是否为空
        if not result or result.strip() == "":
            logger.error(f"[!] LLM返回空响应")
            logger.debug(f"[DEBUG] Full response object: {response}")
            return []

        # 尝试清理可能的markdown代码块标记
        result_cleaned = result.strip()
        if result_cleaned.startswith("```json"):
            result_cleaned = result_cleaned[7:]  # 移除 ```json
        elif result_cleaned.startswith("```"):
            result_cleaned = result_cleaned[3:]  # 移除 ```
        if result_cleaned.endswith("```"):
            result_cleaned = result_cleaned[:-3]  # 移除结尾的 ```
        result_cleaned = result_cleaned.strip()

        logger.debug(f"[DEBUG] Cleaned response length: {len(result_cleaned)} chars")
        logger.debug(f"[DEBUG] Cleaned response preview: {result_cleaned[:200]}...")

        # Check if response appears truncated (doesn't end with proper JSON closing)
        if not result_cleaned.endswith('}'):
            logger.warning(f"[!] Response appears truncated - doesn't end with '}}'. Last 50 chars: {result_cleaned[-50:]}")
            logger.warning(f"[!] This may indicate the response exceeded max_tokens limit")
            # Try to fix common truncation issues
            if result_cleaned.endswith('"'):
                result_cleaned += '\n}'
            elif result_cleaned.endswith(','):
                result_cleaned = result_cleaned.rstrip(',') + '\n}'
            else:
                result_cleaned += '"\n}'
            logger.info(f"[DEBUG] Attempted to fix truncated JSON, new ending: {result_cleaned[-50:]}")

        json_data = json.loads(result_cleaned)
        logger.info(f"[+] LLM返回结果字段: {list(json_data.keys())}")
        split_text = json_data.get('split', '')

        if not split_text:
            logger.error(f"[!] JSON中没有'split'字段: {json_data}")
            return []

        split_result = [segment.strip() for segment in split_text.split("<br>") if segment.strip()] # 将单个段落拆分为句子（各语言通用），通过strip去除文本两端的空格
        logger.info(f"[+] 成功分割为 {len(split_result)} 个句子")

        set_cache(text, model, split_result)
        return split_result
    except json.JSONDecodeError as e:
        logger.error(f"[!] JSON解析失败: {e}")
        logger.error(f"[!] 原始内容长度: {len(result) if result else 0} chars")
        logger.error(f"[!] 原始内容预览 (前500字符): {result[:500] if result else 'None'}")
        logger.error(f"[!] 原始内容结尾 (后200字符): {result[-200:] if result else 'None'}")
        return []
    except Exception as e:
        logger.error(f"[!] 请求LLM失败: {e}")
        print(f"[!] 请求LLM失败: {e}")
        return []
