"""
Plain translation for local vLLM small models (e.g. Hunyuan-MT-7B).

Strategy for instruction-following-free translation models:
- Punctuation/pause-driven aggregation: collect fragments into complete sentences
- Minimal system prompt: language direction + tone instruction only
- Proportional character alignment: distribute translated text back by source char ratio
"""

import logging
import os
import re
import sys
import threading

import httpx
import openai

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from video.views.set_setting import load_all_settings
from utils.split_subtitle.ASRData import ASRData

logger = logging.getLogger("subtitle_translate")

LANG_NAMES = {
    "en": "English",
    "zh": "Chinese",
    "jp": "Japanese",
}

PAUSE_THRESHOLD_MS = 600  # gap >= 600ms between segments → sentence boundary
MAX_MERGE = 12  # hard cap: flush chunk regardless of punctuation

TERMINAL_PUNCT = re.compile(r"[.?!。？！]\s*$")


def _build_chunks(segments) -> list[list[int]]:
    """
    Group segment indices into semantic chunks by sentence boundaries.

    Boundary triggers (any one suffices):
    1. Terminal punctuation at end of current segment (. ? !)
    2. Time gap to next segment >= PAUSE_THRESHOLD_MS
    3. Buffer reaches MAX_MERGE segments (hard cap, prevents over-long API input)
    4. Final segment

    Returns list of index-lists, e.g. [[0,1,2], [3,4], [5,6,7,8]]
    """
    chunks = []
    buffer = []

    for i, seg in enumerate(segments):
        buffer.append(i)

        is_terminal = bool(TERMINAL_PUNCT.search(seg.text.strip()))
        is_max = len(buffer) >= MAX_MERGE
        is_last = i == len(segments) - 1

        is_pause = False
        if not is_last:
            gap = segments[i + 1].start_time - seg.end_time
            is_pause = gap >= PAUSE_THRESHOLD_MS

        if is_terminal or is_pause or is_max or is_last:
            chunks.append(buffer)
            buffer = []

    return chunks


def _align_translation(translated: str, segs) -> list[str]:
    """
    Distribute translated text to each segment proportionally by source char length.

    Safety: each non-last segment reserves at least 1 char per remaining segment,
    preventing cursor overflow caused by rounding accumulation.
    """
    translated = translated.strip()
    if not translated:
        return [seg.text for seg in segs]

    if len(segs) == 1:
        return [translated]

    total_src_len = sum(len(seg.text) for seg in segs)
    if total_src_len == 0:
        return [translated] + [""] * (len(segs) - 1)

    n = len(translated)
    result = []
    cursor = 0

    for i, seg in enumerate(segs):
        if i == len(segs) - 1:
            result.append(translated[cursor:])
        else:
            ratio = len(seg.text) / total_src_len
            count = max(1, round(n * ratio))
            # Leave at least 1 char per remaining segment to prevent rounding overflow
            count = min(count, n - cursor - (len(segs) - 1 - i))
            count = max(1, count)
            result.append(translated[cursor : cursor + count])
            cursor += count

    return result


def plain_translate(
    asr_data: ASRData,
    num_threads: int = 16,
    source_lang: str = "en",
    target_lang: str = "zh",
    progress_cb=None,
) -> ASRData:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = load_all_settings()
    selected_model_provider = settings.get("DEFAULT", {}).get(
        "translate_selected_model_provider", "deepseek"
    )
    api_key = settings.get("DEFAULT", {}).get(
        f"translate_{selected_model_provider}_api_key", ""
    )
    base_url = settings.get("DEFAULT", {}).get(
        f"translate_{selected_model_provider}_base_url", "https://api.deepseek.com"
    )
    model = settings.get("DEFAULT", {}).get(
        f"translate_{selected_model_provider}_model", ""
    )

    segments = asr_data.segments
    total = len(segments)
    logger.info(
        f"plain_translate: model={model}, threads={num_threads}, segments={total}"
    )

    use_proxy = (
        settings.get("DEFAULT", {}).get("translate_use_proxy", "false").lower()
        == "true"
    )
    effective_key = api_key if api_key else "dummy-key"
    from video.proxy import get_effective_proxy

    _proxy = get_effective_proxy(use_proxy)
    if _proxy:
        http_client = httpx.Client(proxy=_proxy, timeout=60)
        client = openai.OpenAI(
            api_key=effective_key, base_url=base_url, http_client=http_client
        )
    else:
        http_client = httpx.Client(proxy=None, timeout=60, trust_env=False)
        client = openai.OpenAI(
            api_key=effective_key, base_url=base_url, http_client=http_client
        )

    target_name = LANG_NAMES.get(target_lang, target_lang)
    system_prompt = (
        f"Translate into {target_name}. Take into account the raw sentence tone."
    )

    chunks = _build_chunks(segments)
    logger.info(f"plain_translate: {total} segs → {len(chunks)} chunks")

    def translate_chunk(indices: list[int]):
        chunk_segs = [segments[i] for i in indices]
        merged_text = " ".join(seg.text.strip() for seg in chunk_segs)

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": merged_text},
                ],
                temperature=0.1,
                top_p=0.85,
                max_tokens=512,
            )
            translated = resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"chunk翻译失败 [{merged_text[:30]}...]: {e}")
            translated = ""

        aligned = _align_translation(translated, chunk_segs)
        for i, idx in enumerate(indices):
            result = aligned[i].strip() if aligned[i].strip() else segments[idx].text
            segments[idx].direct = result
            segments[idx].free = result

    completed_chunks = 0
    progress_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(translate_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            future.result()
            if progress_cb:
                with progress_lock:
                    completed_chunks += 1
                    progress_cb(completed_chunks / max(len(chunks), 1))

    logger.info(f"plain_translate 完成, 共{total}句, {len(chunks)}个翻译块")
    return asr_data
