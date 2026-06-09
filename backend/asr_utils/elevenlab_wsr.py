import requests
import json
import re
import requests
from typing import Iterable, List, Dict, Any, Optional

def sec_to_srt_time(sec: float) -> str:
    """
    将秒(float)转为 SRT 时间格式: HH:MM:SS,mmm
    """
    if sec is None:
        sec = 0.0
    if sec < 0:
        sec = 0.0
    total_ms = int(round(sec * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


# 字级时间戳SRT文件建立==========
def build_word_level_srt(entries: Iterable[Dict[str, Any]]) -> str:
    """
    entries: 形如 [{"text": "...", "start": 1.23, "end": 1.56}, ...] 的可迭代对象
    返回字级（逐词）SRT字符串
    """
    lines: List[str] = []
    idx = 1
    for e in entries:
        text = (e.get("text") or "").strip()
        if not text:
            continue
        start = e.get("start")
        end = e.get("end")
        if start is None or end is None:
            continue
        # 修正非增时长
        if end <= start:
            end = start + 0.001  # 1ms 兜底

        lines.append(str(idx))
        lines.append(f"{sec_to_srt_time(start)} --> {sec_to_srt_time(end)}")
        lines.append(text)
        lines.append("")  # 空行
        idx += 1
    return "\n".join(lines)


# ========== ElevenLabs 响应适配器 ==========
def elevenlabs_words_to_entries(
    resp_json: Dict[str, Any],
    include_punctuation: bool = False,
    only_type_word: bool = True,
) -> List[Dict[str, Any]]:
    """
    将 ElevenLabs /v1/speech-to-text 返回里的 words 列表，转为 entries
    - include_punctuation=False: 默认跳过纯标点或空白 token
    - only_type_word=True: 仅保留 type == "word" 的 token（跳过 "spacing", "audio_event"）
    """
    words: List[Dict[str, Any]] = resp_json.get("words", []) or []
    entries: List[Dict[str, Any]] = []

    # 简单判定“纯标点/空白”
    # 单引号版本（注意在字符类里把单引号写成 \'）
    punct_re = re.compile(
        r'^\s*$|^[\u3000-\u303F\u2000-\u206F!"#$%&\'()*+,\-./:;<=>?@\[\]^_`{|}~，。！？；：“”‘’（）《》、…—]+$'
    )

    for w in words:
        t = (w.get("text") or "")
        wtype = w.get("type")
        if only_type_word and wtype != "word":
            # 跳过 spacing / audio_event 等
            continue

        # 是否跳过标点/空白
        if not include_punctuation and punct_re.match(t):
            continue

        start = w.get("start")
        end = w.get("end")
        # ElevenLabs 的 start/end 为秒(float)
        if start is None or end is None:
            continue

        entries.append({
            "text": t,
            "start": float(start),
            "end": float(end),
        })
    return entries


# ========== 字级时间戳json转srt ==========
def sentence_json_to_entries(
    sentence_list: List[Dict[str, Any]],
    include_punctuation: bool = False
) -> List[Dict[str, Any]]:
    """
    适配你此前提供的结构：
    [
      {
        "sentence_id": 1,
        "begin_time": 1980,  # ms
        "end_time": 4260,    # ms
        "words": [
          {"begin_time": 1980, "end_time": 2305, "text": "好", "punctuation": "，"},
          ...
        ]
      },
      ...
    ]
    转为 entries（秒）
    - include_punctuation=False: 默认把 punctuation 拼到当前词尾或直接忽略（更贴近“字级”）
    """
    entries: List[Dict[str, Any]] = []
    for sent in sentence_list:
        for w in sent.get("words", []):
            text = (w.get("text") or "")
            punct = (w.get("punctuation") or "")
            token = text if not include_punctuation else (text + punct)

            if not token.strip():
                continue

            # 原数据是毫秒
            bs = w.get("begin_time")
            es = w.get("end_time")
            if bs is None or es is None:
                continue

            start = float(bs) / 1000.0
            end = float(es) / 1000.0
            if end <= start:
                end = start + 0.001

            entries.append({
                "text": token.strip(),
                "start": start,
                "end": end
            })
    return entries


# ========== 拉取 + 转 SRT 的主流程（ElevenLabs） ==========
def elevenlabs_stt_to_word_srt(
    audio_path: str,
    api_key: str,
    model_id: str = "scribe_v1",
    include_punctuation: bool = False
) -> str:
    """
    调用 ElevenLabs STT，并把返回转为字级 SRT 字符串
    """
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": api_key}
    data = {"model_id": model_id}

    with open(audio_path, "rb") as f:
        files = {"file": f}
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=120,proxies={"http": None, "https": None})

    # 如果不是 JSON，可以 resp.text 打印看看
    resp.raise_for_status()
    resp_json = resp.json()

    # 适配为 entries
    entries = elevenlabs_words_to_entries(
        resp_json,
        include_punctuation=include_punctuation,
        only_type_word=True,  # 跳过 spacing/audio_event
    )

    # 构建 SRT
    return build_word_level_srt(entries)
