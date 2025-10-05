"""
Translation Agent 的核心在于其独特的“反思工作流”，该工作流模拟了人类翻译专家的思考过程，将翻译任务分解为三个主要步骤：

    初始翻译： Translation Agent 首先利用 LLM 对输入文本进行初步翻译，得到一个初步的译文。

    反思与改进： 与传统机器翻译系统直接输出译文不同，Translation Agent 会引导 LLM 对自身的翻译结果进行反思，并提出改进建议。例如，LLM 可能会指出译文中存在的不准确、不流畅或不符合目标语言习惯表达的地方，就像一个经验丰富的校对员一样，帮助 LLM 找出翻译中的不足之处。

    优化输出： 最后，Translation Agent 根据 LLM 提出的改进建议，对初始译文进行优化，最终生成一个更加精准、流畅且符合目标语言习惯的译文。
"""

def get_faithful_prompt(source_lang: str, target_lang: str, previous_context: str = "", next_context: str = "", terms_to_note: str = "") -> str:
    """生成直译阶段的提示模板"""
    
    # 语言名称映射
    lang_names = {
        'en': 'English',
        'zh': '简体中文',
        'jp': '日本語'
    }
    
    source_name = lang_names.get(source_lang, source_lang)
    target_name = lang_names.get(target_lang, target_lang)
    
    return f"""  Role

  You are a professional Netflix subtitle translator, fluent in both {source_name} and {target_name}, as well as their respective cultures.
  Your expertise lies in accurately understanding the semantics and structure of the original {source_name} text and faithfully translating it into {target_name} while preserving the original meaning.

  Task

  We have a segment of original {source_name} subtitles that need to be directly translated into {target_name}. These subtitles come from a specific context and may contain specific themes and terminology.

  1. Translate the original {source_name} subtitles into {target_name} line by line
  2. Ensure the translation is faithful to the original, accurately conveying the original meaning
  3. Consider the context and professional terminology

  Previous Context Information

  {previous_context if previous_context else "无前文上下文"}
  
  Next Context Information

  {next_context if next_context else "无后文上下文"}


  Points to Note

  {terms_to_note if terms_to_note else "[Specific things to note for this chunk]"}

  Output in only JSON format and no other text,For Example:

  {{
    "1": {{
      "original": "An example sentence in the source language.",
      "direct": "The corresponding faithful translation in the target language."
    }},
    "2": {{
      "original": "Another example subtitle line.",
      "direct": "Its faithful translation."
    }}
  }}

"""
#   Note: Start you answer with ```json and end with ```, do not add any other text.

def get_free_prompt(source_lang: str, target_lang: str, previous_context: str = "", next_context: str = "") -> str:
    """生成意译阶段的提示模板"""
    
    # 语言名称映射
    lang_names = {
        'en': 'English',
        'zh': '简体中文', 
        'jp': '日本語'
    }
    
    source_name = lang_names.get(source_lang, source_lang)
    target_name = lang_names.get(target_lang, target_lang)
    
    return f"""### Step 2: Expressive Translation

  Role

  You are a professional Netflix subtitle translator and language consultant.
  Your expertise lies not only in accurately understanding the original {source_name} but also in optimizing the {target_name} translation to better suit the target language's expression habits and cultural
  background.

  Task

  We already have a direct translation version of the original {source_name} subtitles.
  Your task is to reflect on and improve these direct translations to create more natural and fluent {target_name} subtitles.

  1. Analyze the direct translation results line by line, pointing out existing issues
  2. Provide detailed modification suggestions
  3. Perform free translation based on your analysis
  4. Do not add comments or explanations in the translation, as the subtitles are for the audience to read
  5. Do not leave empty lines in the free translation, as the subtitles are for the audience to read

  Previous Context:
  {previous_context if previous_context else "无前文上下文"}
  
  Next Context:
  {next_context if next_context else "无后文上下文"}

  1. Direct Translation Reflection:
    - Evaluate language fluency
    - Check if the language style is consistent with the original text
    - Check the conciseness of the subtitles, point out where the translation is too wordy
  2. {target_name} Free Translation:
    - Aim for contextual smoothness and naturalness, conforming to {target_name} expression habits
    - Ensure it's easy for {target_name} audience to understand and accept
    - Adapt the language style to match the theme (e.g., use casual language for tutorials, professional terminology for technical content, formal language for documentaries)
    - Do not abridge the translation; instead, expand when necessary. Conciseness should be treated as a secondary criterion, while the primary standard is to fully cover the context and preserve all expressions of the original text without reduction.
  </Translation Analysis Steps>

  OUTPUT

  {{
    "1": {{
      "original": "All of you know Andrew Ng as a famous computer science professor at Stanford.",
      "direct": "你们都知道吴恩达是斯坦福大学著名的计算机科学教授。",
      "reflect": "直译较为准确，但可以更简洁自然",
      "free": "大家都知道吴恩达，斯坦福著名的计算机科学教授"
    }},
    "2": {{
      "original": "He was really early on in the development of neural networks with GPUs.",
      "direct": "他在使用GPU开发神经网络方面起步很早。",
      "reflect": "表达略显生硬，可以更符合中文表达习惯",
      "free": "他很早就开始用GPU来开发神经网络了"
    }}
  }}
"""

MERGE_ENGLISH_GRAPHEME_PROMPT="""
你是一个擅长处理中英文混排字幕的Youtube高级字幕识别专家，这是一份中英文混杂的字幕，你的任务是将其中被分散为词素的英文单词合并， 
注意不要修改每一行的编号，时间及字幕顺序，仅修改其中中英文夹杂时不符合语言习惯的内容，并返回srt格式的字幕。 
示例：ver 可以让两个we b ui 同时使用 输出：ver 可以让两个web ui 同时使用 
示例：然后一个是这个f inet une 输出：然后一个是这个finetune 
示例：一个是拉拉玛trans l ator 输出：一个是拉拉玛translator
"""

TERM_EMBEDDING_PROMPT="""
阶段1：摘要和术语提取

输入：用户的 custom_terms.xlsx + 视频内容
处理：GPT 提取新术语，同时避免与现有自定义术语重复
输出：包含用户定义和AI提取术语的组合术语文件

阶段2：术语感知翻译
对于每个翻译块：

术语检测：扫描当前句子中的任何已知术语（不区分大小写）
上下文注入：将相关术语作为"注意要点"添加到翻译提示词中
翻译：GPT 在完全了解特定术语的情况下进行翻译

4. 手动术语调整功能
暂停机制 (config.yaml + st.py)
yamlpause_before_translate: false  # 设置为true以启用手动术语编辑
启用时：
pythonif load_key("pause_before_translate"):
    input("⚠️ 请前往 `output/log/terminology.json` 编辑术语。然后按回车键...")
用户可以在翻译开始前手动编辑组合术语文件。
"""

import hashlib
import json
import os
import sys
import logging
from typing import Optional
import openai

# 将项目根目录添加到路径以从video.views.set_setting导入
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from video.views.set_setting import load_all_settings
from utils.split_subtitle.ASRData import ASRData

# 配置日志
logger = logging.getLogger('subtitle_translate')
if not logger.handlers:
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 创建文件处理器
    log_file = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'translate.log')
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

from utils.llm_engines import ENGINES

CACHE_DIR = "cache"

def get_cache_key(prompt: str, model: str) -> str:
    """
    生成缓存键值
    """
    return hashlib.md5(f"{prompt}_{model}".encode()).hexdigest()

def get_cache(prompt: str, model: str) -> Optional[str]:
    """
    从缓存中获取翻译结果
    """
    cache_key = get_cache_key(prompt, model)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                return cached_data.get('result', None)
        except (IOError, json.JSONDecodeError):
            return None
    return None

def set_cache(prompt: str, model: str, result: str) -> None:
    """
    将翻译结果设置到缓存中
    """
    cache_key = get_cache_key(prompt, model)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({'result': result}, f, ensure_ascii=False)
    except IOError:
        pass

def clean_json_response(response: str) -> str:
    """
    清理LLM响应，去除markdown代码块格式
    """
    if not response or not response.strip():
        return "{}"
    
    response = response.strip()
    
    # 去除开头的```json或```
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    elif response.startswith("json"):
        response = response[4:]
    
    # 去除结尾的```
    if response.endswith("```"):
        response = response[:-3]
    
    response = response.strip()
    
    # 如果响应为空或只包含换行符，返回空对象
    if not response or response.isspace():
        return "{}"
    
    # 尝试找到JSON对象的开始和结束
    start_idx = response.find('{')
    end_idx = response.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        return response[start_idx:end_idx + 1]
    
    return response

def call_llm(prompt: str, use_cache: bool = True, api_key=None, base_url=None, model=None) -> str:
    """
    调用LLM API
    """
    if api_key is None or base_url is None or model is None:
        raise ValueError("api_key, base_url and model parameters are required")
    
    # 在函数内部创建客户端
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    # 暂时禁用缓存以避免格式问题
    # if use_cache:
    #     cached_result = get_cache(prompt, MODEL)
    #     if cached_result:
    #         logger.debug("从缓存中获取翻译结果")
    #         return cached_result

    try:
        logger.debug(f"发送LLM请求，模型: {model}, 提示词长度: {len(prompt)} 字符")
        logger.debug(f"提示词前200字符: {prompt[:200]}...")
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=8192  # Ensure sufficient tokens for long responses
        )
        result = response.choices[0].message.content
        
        # 详细记录LLM响应
        logger.debug(f"LLM响应长度: {len(result)} 字符")
        logger.debug(f"LLM响应前500字符: {result[:500]}...")
        
        # 检查响应是否包含明显的错误标识
        if result and (result.strip().startswith('"') or 'error' in result.lower() or 'invalid' in result.lower()):
            logger.warning(f"LLM响应可能包含错误: {result[:200]}...")
        
        # 暂时禁用缓存
        # if use_cache:
        #     set_cache(prompt, MODEL, result)
        
        return result
    except Exception as e:
        logger.error(f"请求LLM失败: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"提示词: {prompt[:100]}...")
        return ""
    
def step1_direct_translate_batch(batch_segments: ASRData, batch_start_idx: int, batch_size: int, all_segments: ASRData = None, use_cache: bool = True, source_lang: str = 'en', target_lang: str = 'zh', terms_to_note: str = "", api_key=None, base_url=None, model=None) -> ASRData:
    """
    批量直译处理函数 - 处理一批sentences (10-20个)
    输入给LLM的序号始终是1到len(batch_segments)
    all_segments: 完整的字幕数据，用于生成上下文
    """
    # 生成上下文信息
    context_size = 3  # 前后各3个句子作为上下文
    previous_context = ""
    next_context = ""
    # print(next_context)

    if all_segments and len(all_segments.segments) > 0:
        # 获取前文上下文
        prev_start_idx = max(0, batch_start_idx - context_size)
        prev_end_idx = batch_start_idx
        if prev_start_idx < prev_end_idx:
            prev_segments = all_segments.segments[prev_start_idx:prev_end_idx]
            # print("start direct translate")
            # print([f"{seg.text}" for i, seg in enumerate(prev_segments)])
            previous_context = "\n".join([f"{prev_start_idx+i+1}. {seg.text}" for i, seg in enumerate(prev_segments)])
        
        # 获取后文上下文  
        next_start_idx = batch_start_idx + len(batch_segments)
        next_end_idx = min(len(all_segments.segments), next_start_idx + context_size)
        if next_start_idx < next_end_idx:
            next_segments = all_segments.segments[next_start_idx:next_end_idx]
            next_context = "\n".join([f"{next_start_idx+i+1}. {seg.text}" for i, seg in enumerate(next_segments)])
    # print(all_segments)
    # 准备输入JSON，序号: 1开始到batch_size
    input_json = {}
    for i, segment in enumerate(batch_segments, 1):  # i 从1开始，到len(batch_segments)
        input_json[str(i)] = {
            "original": segment.text
        }
    print("input_json:",input_json)
    # 构建完整的prompt，一次性填充所有占位符
    prompt_with_context = get_faithful_prompt(
        source_lang, 
        target_lang, 
        previous_context if previous_context else "无前文上下文",
        next_context if next_context else "无后文上下文",
        terms_to_note
    )
    # print(prompt_with_context)
    full_prompt = prompt_with_context + "\n\nINPUT:\n" + json.dumps(input_json, ensure_ascii=False, indent=2)
    print("full_prompt:",full_prompt)

    # 调用LLM
    response = call_llm(full_prompt, use_cache, api_key, base_url, model)
    
    # 解析LLM返回的JSON
    try:
        logger.debug(f"批次{batch_start_idx//batch_size+1} 开始解析LLM响应")
        cleaned_response = clean_json_response(response)
        logger.debug(f"批次{batch_start_idx//batch_size+1} 清理后的响应: {cleaned_response[:200]}...")
        
        response_json = json.loads(cleaned_response)
        logger.debug(f"批次{batch_start_idx//batch_size+1} JSON解析成功，包含{len(response_json)}个条目")
        
        # 将LLM返回的结果（序号1-batch_size）映射回原始segments
        for batch_idx, segment in enumerate(batch_segments):  # batch_idx: 0 to len(batch_segments)-1
            llm_key = str(batch_idx + 1)  # LLM返回的序号：1 to len(batch_segments)
            original_idx = batch_start_idx + batch_idx  # 原始序号
            
            if llm_key in response_json and "direct" in response_json[llm_key]:
                # original = response_json[llm_key].get("origin", segment.text)  # 不再使用
                direct = response_json[llm_key]["direct"]
                segment.direct = direct
                logger.debug(f"批次{batch_start_idx//batch_size+1} 原始第{original_idx+1}句(批内第{batch_idx+1}句)直译完成: {segment.text[:30],segment.direct[:30]}...")
            else:
                logger.warning(f"批次{batch_start_idx//batch_size+1} 缺少key '{llm_key}' 或 'direct' 字段")
                logger.debug(f"响应中的keys: {list(response_json.keys())}")
                if llm_key in response_json:
                    logger.debug(f"key '{llm_key}' 的内容: {response_json[llm_key]}")
    
    except json.JSONDecodeError as e:
        logger.error(f"批次{batch_start_idx//batch_size+1} LLM返回的JSON格式无效: {e}")
        logger.error(f"JSON错误位置: 行{e.lineno}, 列{e.colno}")
        logger.error(f"错误消息: {e.msg}")
        logger.error(f"原始LLM响应长度: {len(response)} 字符")
        logger.error(f"原始LLM响应: {repr(response)}")  # 使用repr显示转义字符
        logger.error(f"清理后的响应长度: {len(cleaned_response)} 字符")
        logger.error(f"清理后的响应: {repr(cleaned_response)}")  # 使用repr显示转义字符
        
        # 为所有段落设置默认值，避免翻译失败
        for batch_idx, segment in enumerate(batch_segments):
            if not hasattr(segment, 'direct') or not segment.direct:
                segment.direct = segment.text  # 使用原文作为默认直译
    except Exception as e:
        logger.error(f"批次{batch_start_idx//batch_size+1} 处理响应时发生未知错误: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"原始响应: {repr(response)}")
        logger.error(f"清理后响应: {repr(cleaned_response) if 'cleaned_response' in locals() else 'N/A'}")
        
        # 为所有段落设置默认值，避免翻译失败
        for batch_idx, segment in enumerate(batch_segments):
            if not hasattr(segment, 'direct') or not segment.direct:
                segment.direct = segment.text  # 使用原文作为默认直译
    
    return batch_segments

def step1_direct_translate(asr_data: ASRData, use_cache: bool = True, batch_size: int = 15, num_threads: int = 4, source_lang: str = 'en', target_lang: str = 'zh', terms_to_note: str = "", api_key=None, base_url=None, model=None) -> ASRData:
    """
    第一步：直译 - 使用FAITHFUL_PROMPT，支持批处理和多线程
    """
    from concurrent.futures import ThreadPoolExecutor
    
    # 将segments按批次分组
    batches = []
    for i in range(0, len(asr_data.segments), batch_size):
        batch = asr_data.segments[i:i + batch_size]
        batches.append((batch, i))
    
    logger.info(f"直译阶段：将{len(asr_data.segments)}个句子分为{len(batches)}个批次，每批最多{batch_size}句")
    
    # 多线程处理批次
    def process_batch(batch_data):
        batch_segments, batch_start_idx = batch_data
        return step1_direct_translate_batch(batch_segments, batch_start_idx, batch_size, asr_data, use_cache, source_lang, target_lang, terms_to_note, api_key, base_url, model)
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        batch_results = list(executor.map(process_batch, batches))
    
    # 合并结果，保持原始顺序
    all_segments = []
    for batch_result in batch_results:
        all_segments.extend(batch_result)
    
    return ASRData(all_segments)

def step2_free_translate_batch(batch_segments: ASRData, batch_start_idx: int, batch_size: int, all_segments: ASRData = None, use_cache: bool = True, source_lang: str = 'en', target_lang: str = 'zh', terms_to_note: str = "", api_key=None, base_url=None, model=None) -> ASRData:
    """
    批量意译和反思处理函数 - 处理一批sentences (10-20个)
    输入给LLM的序号始终是1到len(batch_segments)
    all_segments: 完整的字幕数据，用于生成上下文
    """
    # 生成上下文信息（与step1相同逻辑）
    context_size = 3  # 前后各3个句子作为上下文
    previous_context = ""
    next_context = ""
    
    if all_segments and len(all_segments.segments) > 0:
        # 获取前文上下文
        prev_start_idx = max(0, batch_start_idx - context_size)
        prev_end_idx = batch_start_idx
        if prev_start_idx < prev_end_idx:
            prev_segments = all_segments.segments[prev_start_idx:prev_end_idx]
            print("start free translate")
            print([f"{i+1}. {seg.text}" for i, seg in enumerate(prev_segments)])
            previous_context = "\n".join([f"{i+1}. {seg.text}" for i, seg in enumerate(prev_segments)])
        
        # 获取后文上下文
        next_start_idx = batch_start_idx + len(batch_segments)
        next_end_idx = min(len(all_segments.segments), next_start_idx + context_size)
        if next_start_idx < next_end_idx:
            next_segments = all_segments.segments[next_start_idx:next_end_idx]
            next_context = "\n".join([f"{i+1}. {seg.text}" for i, seg in enumerate(next_segments)])
    
    # 准备输入JSON，序号从1开始到batch_size
    input_json = {}
    for i, segment in enumerate(batch_segments, 1):  # i 从1开始，到len(batch_segments)
        input_json[str(i)] = {
            "original": segment.text,
            "direct": segment.direct
        }
    
    # 构建完整的prompt，一次性填充所有占位符  
    prompt_with_context = get_free_prompt(
        source_lang,
        target_lang,
        previous_context if previous_context else "无前文上下文",
        next_context if next_context else "无后文上下文"
    )
    full_prompt = prompt_with_context + "\n\nINPUT:\n" + json.dumps(input_json, ensure_ascii=False, indent=2)
    
    # 调用LLM
    response = call_llm(full_prompt, use_cache, api_key, base_url, model)
    
    # 解析LLM返回的JSON
    try:
        logger.debug(f"批次{batch_start_idx//batch_size+1} 开始解析LLM响应")
        cleaned_response = clean_json_response(response)
        logger.debug(f"批次{batch_start_idx//batch_size+1} 清理后的响应: {cleaned_response[:200]}...")
        
        response_json = json.loads(cleaned_response)
        logger.debug(f"批次{batch_start_idx//batch_size+1} JSON解析成功，包含{len(response_json)}个条目")
        
        # 将LLM返回的结果（序号1-batch_size）映射回原始segments
        for batch_idx, segment in enumerate(batch_segments):  # batch_idx: 0 to len(batch_segments)-1
            llm_key = str(batch_idx + 1)  # LLM返回的序号：1 to len(batch_segments)
            original_idx = batch_start_idx + batch_idx  # 原始序号
            
            if llm_key in response_json:
                if "reflect" in response_json[llm_key]:
                    segment.reflected = response_json[llm_key]["reflect"]
                if "free" in response_json[llm_key]:
                    segment.free = response_json[llm_key]["free"]
                    logger.debug(f"批次{batch_start_idx//batch_size+1} 原始第{original_idx+1}句(批内第{batch_idx+1}句)翻译意见为：{segment.reflected[:30]}，意译完成: {segment.free[:30]}...")
            else:
                logger.warning(f"批次{batch_start_idx//batch_size+1} 缺少key '{llm_key}'")
                logger.debug(f"响应中的keys: {list(response_json.keys())}")
    
    except json.JSONDecodeError as e:
        logger.error(f"批次{batch_start_idx//batch_size+1} (意译阶段) LLM返回的JSON格式无效: {e}")
        logger.error(f"JSON错误位置: 行{e.lineno}, 列{e.colno}")
        logger.error(f"错误消息: {e.msg}")
        logger.error(f"原始LLM响应长度: {len(response)} 字符")
        logger.error(f"原始LLM响应: {repr(response)}")  # 使用repr显示转义字符
        logger.error(f"清理后的响应长度: {len(cleaned_response)} 字符")
        logger.error(f"清理后的响应: {repr(cleaned_response)}")  # 使用repr显示转义字符
        
        # 为所有段落设置默认值，避免翻译失败
        for batch_idx, segment in enumerate(batch_segments):
            if not hasattr(segment, 'free') or not segment.free:
                segment.free = getattr(segment, 'direct', segment.text)  # 使用直译或原文作为默认意译
            if not hasattr(segment, 'reflected') or not segment.reflected:
                segment.reflected = "翻译完成"
    except Exception as e:
        logger.error(f"批次{batch_start_idx//batch_size+1} (意译阶段) 处理响应时发生未知错误: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"原始响应: {repr(response)}")
        logger.error(f"清理后响应: {repr(cleaned_response) if 'cleaned_response' in locals() else 'N/A'}")
        
        # 为所有段落设置默认值，避免翻译失败
        for batch_idx, segment in enumerate(batch_segments):
            if not hasattr(segment, 'free') or not segment.free:
                segment.free = getattr(segment, 'direct', segment.text)  # 使用直译或原文作为默认意译
            if not hasattr(segment, 'reflected') or not segment.reflected:
                segment.reflected = "翻译完成"
    
    return batch_segments

def step2_free_translate(asr_data: ASRData, use_cache: bool = True, batch_size: int = 15, num_threads: int = 4, source_lang: str = 'en', target_lang: str = 'zh', terms_to_note: str = "", api_key=None, base_url=None, model=None) -> ASRData:
    """
    第二步：意译和反思 - 使用FREE_PROMPT，支持批处理和多线程
    """
    from concurrent.futures import ThreadPoolExecutor
    
    # 将segments按批次分组
    batches = []
    for i in range(0, len(asr_data.segments), batch_size):
        batch = asr_data.segments[i:i + batch_size]
        batches.append((batch, i))
    
    logger.info(f"意译阶段：将{len(asr_data.segments)}个句子分为{len(batches)}个批次，每批最多{batch_size}句")
    
    # 多线程处理批次
    def process_batch(batch_data):
        batch_segments, batch_start_idx = batch_data
        return step2_free_translate_batch(batch_segments, batch_start_idx, batch_size, asr_data, use_cache, source_lang, target_lang, terms_to_note, api_key, base_url, model)
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        batch_results = list(executor.map(process_batch, batches))
    
    # 合并结果，保持原始顺序
    all_segments = []
    for batch_result in batch_results:
        all_segments.extend(batch_result)
    
    return ASRData(all_segments)

def two_step_translate(asr_data: ASRData, use_cache: bool = True, num_threads: int = 4, batch_size: int = 15, source_lang: str = 'en', target_lang: str = 'zh', terms_to_note: str = "") -> ASRData:
    """
    两步翻译流程：先直译，再意译和反思，支持批处理和多线程
    """
    # 在这里加载设置，每次调用时都获取最新配置
    settings = load_all_settings()
    selected_model_provider = settings.get('DEFAULT', {}).get('selected_model_provider', 'deepseek')
    api_key = settings.get('DEFAULT', {}).get(f'{selected_model_provider}_api_key', '')
    base_url = settings.get('DEFAULT', {}).get(f'{selected_model_provider}_base_url', 'https://api.deepseek.com')
    enable_thinking = settings.get('DEFAULT', {}).get('enable_thinking', 'true')
    model = ENGINES[selected_model_provider]["thinking" if enable_thinking == 'true' else "normal"]
    
    logger.info(f"使用模型: {model}, API地址: {base_url}")
    
    logger.info("开始第一步：批量多线程直译...")
    asr_data = step1_direct_translate(asr_data, use_cache, batch_size, num_threads, source_lang, target_lang, terms_to_note, api_key, base_url, model)
    logger.info(f"直译完成，处理了 {len(asr_data.segments)} 个句子")
    
    logger.info("开始第二步：批量多线程意译和反思...")
    asr_data = step2_free_translate(asr_data, use_cache, batch_size, num_threads, source_lang, target_lang, terms_to_note, api_key, base_url, model)
    logger.info(f"意译和反思完成，处理了 {len(asr_data.segments)} 个句子")
    
    logger.info("两步翻译完成")
    return asr_data