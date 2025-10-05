import os
import re

import difflib
from typing import List, Tuple
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.split_subtitle.ASRData import ASRData, from_srt, ASRDataSeg
from utils.split_subtitle.split_by_llm import split_by_llm
from utils.split_subtitle.merge_english_words import WordMerger

MAX_DISPLAY_COUNT = 60  # display长度的最大数量
MIN_DISPLAY_COUNT = 10   # display长度的最小数量
SEGMENT_THRESHOLD = 800  # 每个分段的最大字数
FIXED_NUM_THREADS = 4  # 固定的线程数量
SPLIT_RANGE = 50  # 在分割点前后寻找最大时间间隔的范围

import logging
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

def is_pure_punctuation(s: str) -> bool:
    """
    检查字符串是否仅由标点符号组成
    """
    return not re.search(r'\w', s, flags=re.UNICODE)


from utils.split_subtitle.cnt_tokens import count_words, cnt_display_words

def preprocess_text(s: str) -> str:
    """
    通过转换为小写并规范化空格来标准化文本
    """
    return ' '.join(s.lower().split())


def merge_segments_based_on_sentences(asr_data: ASRData, sentences: List[str]) -> ASRData:
    """
    基于LLM返回的句子列表，合并ASR分段。
    asr_data: ASRData，ASRDataSeg List，段落中所有的token
    sentences: List[str],LLM根据完整句子生成的分句列表
    这里已经粗筛过一次，asr_data和sentence都是这个800字左右的Section
    """
    asr_texts = [seg.text for seg in asr_data.segments]
    asr_len = len(asr_texts)
    asr_index = 0  # 当前分段索引位置
    threshold = 0.5  # 相似度阈值
    max_shift = 10   # 滑动窗口的最大偏移量

    new_segments = []  # 存储List[List[ASRDataSeg]]以保留token时间信息

    for sentence in sentences:
        logger.info(f"[+] 处理句子: {sentence}")
        sentence_proc = preprocess_text(sentence)
        word_count = count_words(sentence_proc)
        best_ratio = 0.0
        best_pos = None
        best_window_size = 0

        # 滑动窗口大小，优先考虑接近句子词数的窗口
        # 最多为目标词数的2倍
        # 但不能超过剩余的ASR数据长度
        min_window_size = max(1, word_count // 2)
        # 至少为1（保证窗口不为空）
        # 通常为目标词数的一半
        max_window_size = min(word_count * 2, asr_len - asr_index)

        window_sizes = sorted(range(min_window_size, max_window_size + 1), key=lambda x: abs(x - word_count))

        for window_size in window_sizes:
            max_start = min(asr_index + max_shift + 1, asr_len - window_size + 1)
            for start in range(asr_index, max_start):
                substr = ''.join(asr_texts[start:start + window_size])
                substr_proc = preprocess_text(substr)
                ratio = difflib.SequenceMatcher(None, sentence_proc, substr_proc).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_pos = start
                    best_window_size = window_size
                if ratio == 1.0:
                    break  # 完全匹配
            if best_ratio == 1.0:
                break  # 完全匹配

        if best_ratio >= threshold and best_pos is not None:
            start_seg_index = best_pos
            end_seg_index = best_pos + best_window_size - 1

            # 保留原始的ASRDataSeg列表，保持token级别的时间信息
            matched_segments = asr_data.segments[start_seg_index:end_seg_index + 1]
            merged_text = ''.join(seg.text for seg in matched_segments)

            print(f"[+] 合并分段: {merged_text}")
            print("=============")

            # 存储匹配的分段列表，保持token时间信息
            new_segments.append(matched_segments)

            asr_index = end_seg_index + 1  # 移动到下一个未处理的分段
        else:
            # 无法匹配句子，跳过当前分段
            print(f"[-] 无法匹配句子: {sentence},尝试匹配过的分段为{substr_proc},词数为{word_count}其Sequence匹配度为{ratio}")
            # 匹配失败时只前进1步，而不是跳过整个窗口
            asr_index += 1

    # 统一处理过长和过短的分段
    print("[+] 正在处理过长分段...")
    processed_segments = []
    for seg_list in new_segments:
        # 计算整个句子的display长度
        total_text = ''.join(seg.text for seg in seg_list)
        display_len = cnt_display_words(total_text)
        
        if display_len > MAX_DISPLAY_COUNT:
            # 需要分割的分段，传递List[ASRDataSeg]
            split_segs = split_segment_by_display_length(seg_list)
            processed_segments.extend(split_segs)
        else:
            # 创建单个合并的ASRDataSeg用于最终输出
            merged_seg = ASRDataSeg(
                total_text,
                seg_list[0].start_time,
                seg_list[-1].end_time
            )
            processed_segments.append(merged_seg)
    
    print("[+] 正在循环合并过短分段...")
    final_segments = merge_short_segments_iteratively(processed_segments)
    
    # 对最终的句子文本应用英文单词合并
    print("[+] 正在合并分割的英文单词...")
    word_merger = WordMerger()
    merged_final_segments = []
    
    for seg in final_segments:
        merged_text = word_merger.merge_text(seg.text)
        if merged_text != seg.text:
            print(f"[+] 合并单词: '{seg.text}' -> '{merged_text}'")
        
        # 创建新的segment，保持时间信息不变
        merged_seg = ASRDataSeg(
            merged_text,
            seg.start_time,
            seg.end_time,
            seg.direct,
            seg.free,
            seg.reflected
        )
        merged_final_segments.append(merged_seg)
    
    return ASRData(merged_final_segments)


def split_segment_by_display_length(seg_list: List[ASRDataSeg]) -> List[ASRDataSeg]:
    """
    基于display长度分割ASRDataSeg列表，保持token级别的时间信息
    """
    result = []
    
    if not seg_list:
        return result
    
    # 计算总的display长度
    total_text = ''.join(seg.text for seg in seg_list)
    total_display_len = cnt_display_words(total_text)
    
    if total_display_len <= MAX_DISPLAY_COUNT:
        # 不需要分割，合并为单个segment
        merged_seg = ASRDataSeg(
            total_text,
            seg_list[0].start_time,
            seg_list[-1].end_time
        )
        result.append(merged_seg)
        return result
    
    # 需要分割，使用时间间隔寻找最佳分割点
    n = len(seg_list)
    if n <= 1:
        # 只有一个segment，直接返回
        result.extend(seg_list)
        return result
    logger.info(f"[+] 开始分割ASRDataSeg列表，长度为 {n}")
    
    # 在1/6到5/6之间寻找最佳分割点
    start_idx = max(1, n // 6)
    end_idx = min(n - 1, (5 * n) // 6)
    
    max_time_diff = 0
    best_split_idx = -1
    
    for i in range(start_idx, end_idx + 1):
        # 计算与前一个token的时间间隔
        time_diff = seg_list[i].start_time - seg_list[i - 1].end_time
        if time_diff > max_time_diff:
            max_time_diff = time_diff
            best_split_idx = i
    
    # 如果没有找到合适的分割点或时间差太小，使用中点
    if best_split_idx == -1 or max_time_diff < 50:  # 50毫秒作为阈值
        best_split_idx = n // 2
    
    # 根据找到的分割点分割
    first_part = seg_list[:best_split_idx]
    second_part = seg_list[best_split_idx:]
    
    # 递归处理两个部分
    result.extend(split_segment_by_display_length(first_part))
    result.extend(split_segment_by_display_length(second_part))
    
    return result

def merge_short_segments_iteratively(segments: List[ASRDataSeg]) -> List[ASRDataSeg]:
    """
    循环合并过短的分段，基于display_words最小值
    """
    result = segments.copy()
    changed = True
    
    while changed:
        changed = False
        i = 0
        
        while i < len(result):
            seg = result[i]
            display_len = cnt_display_words(seg.text)
            
            if display_len < MIN_DISPLAY_COUNT:
                # 计算与前后分段的时间差
                prev_time_diff = float('inf')
                next_time_diff = float('inf')
                
                if i > 0:
                    prev_seg = result[i - 1]
                    prev_time_diff = seg.start_time - prev_seg.end_time
                
                if i < len(result) - 1:
                    next_seg = result[i + 1]
                    next_time_diff = next_seg.start_time - seg.end_time
                
                # 选择时间差较小的进行合并
                if prev_time_diff <= next_time_diff and i > 0:
                    # 与前一个分段合并
                    prev_seg = result[i - 1]
                    merged_text = prev_seg.text + seg.text
                    
                    merged_seg = ASRDataSeg(
                        merged_text,
                        prev_seg.start_time,
                        seg.end_time,
                        "",  # 直接翻译
                        "",  # 自由翻译
                        ""   # 反思翻译
                    )
                    result[i - 1:i + 1] = [merged_seg]
                    changed = True
                    # 不增加i，因为列表长度减少了
                elif next_time_diff < prev_time_diff and i < len(result) - 1:
                    # 与后一个分段合并
                    next_seg = result[i + 1]
                    merged_text = seg.text + next_seg.text
                    
                    merged_seg = ASRDataSeg(
                        merged_text,
                        seg.start_time,
                        next_seg.end_time,
                        "",  # 直接翻译
                        "",  # 自由翻译
                        ""   # 反思翻译
                    )
                    result[i:i + 2] = [merged_seg]
                    changed = True
                    # 不增加i，继续检查合并后的分段
                else:
                    # 无法合并（边界情况）
                    i += 1
            else:
                i += 1
    
    return result


def process_split_by_llm(asr_data_part: ASRData) -> List[str]:
    """
    调用 split_by_llm 处理单个 ASRData 分段，返回句子列表
    """
    txt = asr_data_part.to_txt().replace("\n", "")
    sentences = split_by_llm(txt, use_cache=True)
    return sentences


def split_asr_data(asr_data: ASRData, num_segments: int) -> List[ASRData]:
    """
    根据ASR分段中的时间间隔，将ASRData拆分成多个部分。
    处理步骤：
    1. 计算总字数与分段数，并确定每个分段的字数范围。
    2. 确定平均分割点。
    3. 在分割点前后一定范围内，寻找时间间隔最大的点作为实际的分割点。
    返回：List[ASRData]，即分段列表，每一个ASRData对象代表一个分段,包含其中所有的ASRDataSeg对象。
    """
    total_segs = len(asr_data.segments)
    total_word_count = count_words(asr_data.to_txt())
    words_per_segment = total_word_count // num_segments
    split_indices = []

    if num_segments <= 1 or total_segs <= num_segments:
        return [asr_data]

    # 计算每个分段的大致字数 根据每段字数计算分割点
    # 比如7047个字，分成8段，每段880个字。
    split_indices = [i * words_per_segment for i in range(1, num_segments)]
    # 调整分割点：在每个平均分割点附近寻找时间间隔最大的点
    adjusted_split_indices = []
    for split_point in split_indices:
        # 定义搜索范围
        start = max(0, split_point - SPLIT_RANGE)
        end = min(total_segs - 1, split_point + SPLIT_RANGE)
        # 在范围内找到时间间隔最大的点
        max_gap = -1
        best_index = split_point
        for j in range(start, end):
            gap = asr_data.segments[j + 1].start_time - asr_data.segments[j].end_time
            if gap > max_gap:
                max_gap = gap
                best_index = j
        adjusted_split_indices.append(best_index)

    # 移除重复的分割点
    adjusted_split_indices = sorted(list(set(adjusted_split_indices)))

    # 根据调整后的分割点拆分ASRData
    segments = []
    prev_index = 0
    for index in adjusted_split_indices:
        part = ASRData(asr_data.segments[prev_index:index + 1])
        segments.append(part)
        prev_index = index + 1
    # 添加最后一部分
    if prev_index < total_segs:
        part = ASRData(asr_data.segments[prev_index:])
        segments.append(part)

    return segments


def determine_num_segments(word_count: int, threshold: int = 500) -> int:
    """
    根据字数计算分段数，每1000个字为一个分段，至少为1
    """
    num_segments = word_count // threshold
    # 如果存在余数，增加一个分段
    if word_count % threshold > 0:
        num_segments += 1
    return max(1, num_segments)

from video.views.set_setting import load_all_settings

from typing import Callable, List
def optimise_srt(
    srt_path: str,
    save_path: str,
    num_threads: int = FIXED_NUM_THREADS,
    progress_cb: Callable[[float], None] | None = None,   # 0.0‒1.0 之间
) -> None:
    settings = load_all_settings()
    use_proxy = settings.get('DEFAULT', {}).get('use_proxy', 'true').lower() == 'true'
    if not use_proxy:
        # 禁用HTTP(S)代理请求
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
    from utils.llm_engines import ENGINES
    # 获取 API 配置
    selected_model_provider = settings.get('DEFAULT', {}).get('selected_model_provider', 'deepseek')
    api_key = settings.get('DEFAULT', {}).get(f'{selected_model_provider}_api_key', '')
    base_url = settings.get('DEFAULT', {}).get(f'{selected_model_provider}_base_url', 'https://api.deepseek.com')
    enable_thinking = settings.get('DEFAULT', {}).get('enable_thinking', 'true')
    model = ENGINES[selected_model_provider]["thinking" if enable_thinking == 'true' else "normal"]
    """
    · 将 用于优化字幕。
    · 增加 progress_cb 回调，用于上报阶段内进度（0‑1）
      ‑ 若未传递则默认什么都不做
    """
    if progress_cb is None:               # 回调默认空操作
        progress_cb = lambda ratio: None

    if progress_cb:
        progress_cb("Running")      # 读取srt文件为一整个asr_data
    with open(srt_path, encoding="utf-8") as f:
        asr_data = from_srt(f.read())

    # 预处理ASR数据，去除标点并转换为小写
    new_segments= []
    for seg in asr_data.segments:
        if not is_pure_punctuation(seg.text):
            if re.match(r"^[a-zA-Z\']+$", seg.text.strip()):
                seg.text = seg.text.lower() + " "
            new_segments.append(seg)
    asr_data.segments = new_segments

    # 将整个字幕合并为文本
    txt = asr_data.to_txt().replace("\n", "")
    total_word_count = count_words(txt)
    print(f"[+] 待分割段落文本长度: {total_word_count} 字")

    # 调试：打印合并后的文本前500字符
    logger.debug(f"[DEBUG] 待分割文本前500字符: {txt[:500]}")

    # 打印所有word-level时间戳字幕（用于调试）
    logger.debug("[DEBUG] ========== Word-level Timestamps ==========")
    logger.debug(f"[DEBUG] 总共 {len(asr_data.segments)} 个word segments")
    for i, seg in enumerate(asr_data.segments[:20]):  # 只打印前20个
        # start_time和end_time是毫秒，需要除以1000转换为秒
        logger.debug(f"[DEBUG] Segment {i}: [{seg.start_time/1000:.2f}s - {seg.end_time/1000:.2f}s] '{seg.text}'")
    if len(asr_data.segments) > 20:
        logger.debug(f"[DEBUG] ... (还有 {len(asr_data.segments) - 20} 个segments)")
    logger.debug("[DEBUG] ============================================")

    num_segments = determine_num_segments(
        total_word_count, threshold=SEGMENT_THRESHOLD
    )
    print(f"[+] 根据字数 {total_word_count}，确定分段数: {num_segments}")

    # 分割ASRData
    asr_data_segments = split_asr_data(asr_data, num_segments)

    # ── 10‑85 %： 多线程执行 split_by_llm 获取句子列表 ─────────────────
    # 🆕 进度追踪变量
    import threading
    completed_chunks = 0
    total_chunks = len(asr_data_segments)
    progress_lock = threading.Lock()

    def process_segment(asr_data_part):
        nonlocal completed_chunks
        part_txt = asr_data_part.to_txt().replace("\n", "")
        sentences = split_by_llm(part_txt, use_cache=True,api_key=api_key,model=model,base_url=base_url)
        print(f"[+] 分段的句子提取完成，共 {len(sentences)} 句")
        # 🆕 线程安全地更新进度 (10% ~ 85%)
        with progress_lock:
            completed_chunks += 1
            progress_percent = 10 + int((completed_chunks / total_chunks) * 75)
            if progress_cb:
                progress_cb(progress_percent)
        return sentences
    print("[+] 正在并行请求LLM将每个分段的文本拆分为句子...")
    all_sentences: List[str] = [] # 一个二维列表
    """
    • map ⇒ 顺序固定，适合“一次性拿齐”场景。
    • submit + as_completed ⇒ 完成顺序随机，如需保持原序必须自己根据索引排队。
    • 你看到的大量“无法匹配”并非线程池速度问题，而是结果顺序被打乱导致后续算法对不了号。
    • 既然 map 已经满足性能要求，又天然保证顺序，最简单的就是保留 map 写法。(所以这里只需要提供是否完成，不需要提供进度)
    """
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        all_sentences = list(executor.map(process_segment, asr_data_segments))
    logger.info("all_sentences before flatten: %s", all_sentences)
    all_sentences = [item for sublist in all_sentences for item in sublist] # 摊平元素，all_sentences 被假定为二维列表
    logger.info("all_sentences after flatten: %s", all_sentences)

    """
    示例：
    all_sentences = [
        ['I', 'am', 'AI'],
        ['你', '好'],
        ['hello', 'world']
    ]
    # 执行列表推导式后：
    all_sentences
    # -> ['I', 'am', 'AI', '你', '好', 'hello', 'world']
    """

    print(f"[+] 总共提取到 {len(all_sentences)} 句")

    # 基于LLM已经分段的句子，对ASR分段进行合并
    print("[+] 正在合并ASR分段基于句子列表...")
    # ── 85‑95 %：合并分段 ──────────────────────
    merged_asr = merge_segments_based_on_sentences(asr_data, all_sentences)
    merged_asr.segments.sort(key=lambda s: s.start_time)

    # ── 95‑100 %：写文件 ───────────────────────
    final_asr_data = ASRData(merged_asr.segments)
    final_asr_data.to_srt(save_path=save_path,use_translation=False)
    print("[+] 已完成 srt 文件合并")
    if progress_cb:
        progress_cb("Completed")        

    print("[+] 已完成 srt 文件合并")

def translate_srt(raw_srt_path, 
                  translate_srt_path,
                  raw_lang="en", 
                  target_lang="zh",
                  use_translation_cache: bool = True,  # Whether to use translation cache
                  num_threads: int = FIXED_NUM_THREADS,  # Number of threads for translation
                  batch_size: int = 15,  # Batch size for LLM processing (10-20 sentences per batch)
                  progress_cb: Callable[[float], None] | None = None,
                  terms_to_note: str = "",  # Terms to emphasize in translation
    ):
    """
    翻译 SRT 文件的主函数
    """
    import logging
    from utils.split_subtitle.translate import two_step_translate
    
    logger = logging.getLogger('subtitle_translate')
    logger.info("开始翻译字幕...")
    
    # 从raw_srt_path加载原始字幕
    with open(raw_srt_path, encoding="utf-8") as f:
        raw_asr_data = from_srt(f.read())
    logger.info("原文字幕加载完成")
    
    # 翻译字幕
    final_asr_data = two_step_translate(raw_asr_data, use_cache=use_translation_cache, num_threads=num_threads, batch_size=batch_size, source_lang=raw_lang, target_lang=target_lang, terms_to_note=terms_to_note)
    logger.info("字幕翻译完成")
    
    # 如果提供了翻译保存路径，则保存翻译字幕
    if translate_srt_path:
        final_asr_data.to_srt(save_path=translate_srt_path, use_translation=True)
        logger.info(f"保存翻译字幕: {translate_srt_path}")
    else:
        logger.warning("未提供翻译字幕保存路径，翻译字幕未保存")
    
    logger.info("翻译完成")
    if progress_cb:
        progress_cb("Completed")

# '线程数量'
num_threads=FIXED_NUM_THREADS
