# coding=utf-8
import os
import glob as _glob
import numpy as np
from pathlib import Path
from PIL import Image as PILImage
import json as _json
from external_api import (
    call_gemini, extract_text, embed_texts, cosine_similarity,
    call_deepseek, call_step, call_step_with_images, call_deepseek_tools,
    call_glm_ocr, _pil_to_base64,
)
from srt_utils import search_transcript, transcript_for_timerange
from config import DEEPSEEK_API_KEY, STEP_API_KEY, N_PREDICT, GGUF_PATH, EXPORT_DIR, N_CTX, N_GPU_LAYERS, N_BATCH, KV_CACHE_TYPE, ONNX_PROVIDER, SUMMARY_SLIDES_PER_CHAPTER, SUMMARY_LANG, MEDIA_VIDUNDER


# ── DeepSeek tool definitions ─────────────────────────────────
_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "search_transcript",
            "description": "在视频字幕中搜索关键词，返回匹配的字幕条目（含时间戳和文本）。适用于定位视频中的特定操作、命令或对话。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，可以是中文或英文",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回前 N 条结果，默认 10",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_transcript_range",
            "description": "读取指定时间范围的原始字幕（最可靠的信息源）。返回该时间段内所有字幕条目。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_seconds": {
                        "type": "number",
                        "description": "起始时间（秒），例如 420 表示 07:00",
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "结束时间（秒），例如 480 表示 08:00",
                    },
                },
                "required": ["start_seconds", "end_seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "visual_inspect",
            "description": "对指定时间段的视频帧进行视觉分析（VQA）。支持多片段：传入较长时间范围时，自动拼接范围内所有 clip 的视觉 token 进行分析。适合确认画面中的命令文本、界面内容、操作流程等。每次调用约需 3-10 秒（取决于范围大小）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "关于视频画面的具体问题",
                    },
                    "start_seconds": {
                        "type": "number",
                        "description": "起始时间（秒）",
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "结束时间（秒）",
                    },
                },
                "required": ["question", "start_seconds", "end_seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_similar_clips",
            "description": "通过语义相似度搜索视频片段描述（caption），返回与查询最相关的片段及其时间戳。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "描述你想找的画面内容",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回前 N 个结果，默认 5",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_scrolling",
            "description": "对视频中滚动代码/文本的区域做高密度采样：密集提取 N 帧，垂直拼接成一张长图，用 GLM-OCR 一次性识别所有可见文本。比逐帧 OCR 更准确（避免逐帧重复），能捕获滚动内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_seconds": {
                        "type": "number",
                        "description": "起始时间（秒）",
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "结束时间（秒）",
                    },
                    "question": {
                        "type": "string",
                        "description": "你想从滚动代码中了解什么？",
                    },
                },
                "required": ["start_seconds", "end_seconds", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_chapters",
            "description": "检测视频的章节结构。通过分析字幕内容的话题变化，返回章节列表（每章含起止时间、标题、概要）。用于生成结构化摘要或理解视频整体结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_chapter_secs": {
                        "type": "integer",
                        "description": "最短章节时长（秒），默认 120",
                        "default": 120,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_extracted_content",
            "description": "获取指定时间段的已提取内容（幻灯片 OCR 文本、代码快照、字幕转录）。需要先运行 extract 命令生成结构化数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_seconds": {
                        "type": "number",
                        "description": "起始时间（秒）",
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "结束时间（秒）",
                    },
                },
                "required": ["start_seconds", "end_seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_chapter",
            "description": "对指定时间段生成结构化章节摘要。综合字幕、幻灯片内容和代码快照，输出该章节的知识点、代码引用和时间锚点。用于 summarize 管线的分章节处理。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_seconds": {
                        "type": "number",
                        "description": "章节起始时间（秒）",
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "章节结束时间（秒）",
                    },
                    "chapter_title": {
                        "type": "string",
                        "description": "章节标题",
                    },
                },
                "required": ["start_seconds", "end_seconds", "chapter_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_summary",
            "description": "读取已生成的 summary markdown 文件。未指定章节时返回目录（二级标题列表）；指定章节标题或序号时返回对应章节正文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {
                        "type": "string",
                        "description": "可选。章节标题或章节序号，支持标题部分匹配；省略则只返回 summary 的二级标题目录。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_summary",
            "description": "修改已生成 summary markdown 中的指定章节内容。用于 ask/refine 流程中重写或修正某一小段摘要文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {
                        "type": "string",
                        "description": "要修改的章节标题或序号，支持标题部分匹配",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "待替换的原文短摘录，用于定位和校验",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "替换后的新文本",
                    },
                },
                "required": ["chapter", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_slide",
            "description": "使用 GLM-OCR 读取或分析指定幻灯片图片。适合查看 extract 输出中的 slide_XXX.png，确认幻灯片文字、公式、表格或页面内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_path": {
                        "type": "string",
                        "description": "幻灯片图片路径，例如 /tmp/xxx/slides/slide_011.png",
                    },
                    "question": {
                        "type": "string",
                        "description": "关于这张幻灯片要识别或分析的问题",
                    },
                },
                "required": ["slide_path", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "identify_image",
            "description": "抽取指定时间段的视频帧并发送给云端 VLM 分析。适合识别本地 8B 模型难以判断的物体、人物、Logo、图标、场景细节等。默认抽 1 帧中间帧；设置 frames>1 时均匀采样多帧一起发送，适合需要观察变化过程或对比多个时间点的场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要向云端视觉模型询问的问题",
                    },
                    "start_seconds": {
                        "type": "number",
                        "description": "起始时间（秒）",
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "结束时间（秒）",
                    },
                    "frames": {
                        "type": "integer",
                        "description": "采样帧数，默认 1（中间帧）。设为 2-8 可均匀采样多帧，一次发给云端 VLM 分析。",
                        "default": 1,
                    },
                },
                "required": ["question", "start_seconds", "end_seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_world_knowledge",
            "description": "查询外部世界知识（通过云端大模型）。当视频内容涉及你不确定的概念、术语、技术细节、历史背景等超出视频本身的信息时使用。返回外部模型的回答。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "需要查询外部知识的问题",
                    },
                },
                "required": ["question"],
            },
        },
    },
]

_SUMMARIZE_TOOL_NAMES = {
    "detect_chapters", "summarize_chapter", "get_extracted_content",
    "search_transcript", "read_transcript_range", "search_similar_clips",
    "inspect_scrolling",
}
_SUMMARIZE_TOOL_DEFS = [
    t for t in _TOOL_DEFS
    if t["function"]["name"] in _SUMMARIZE_TOOL_NAMES
]

class VideoAgent:
    def __init__(self, db, srt_entries, model=None, ctx=None, sampler=None,
                 siglip_sess=None, resampler_sess=None, video_path=None, lang=None):
        self.db = db
        self.srt = srt_entries
        self._model = model
        self._ctx = ctx
        self._sampler = sampler
        self._siglip = siglip_sess
        self._resampler = resampler_sess
        self._video_path = video_path or db.get("video_path")
        self._clip_embeds = None
        self._srt_embeds = None
        self._summary_text = None
        self._lang = lang or SUMMARY_LANG
        if self._lang != "中文":
            self._SYSTEM_PROMPT = self._SYSTEM_PROMPT.replace("用中文回答", f"用{self._lang}回答")
            self._SYSTEM_PROMPT_NO_SRT = self._SYSTEM_PROMPT_NO_SRT.replace("用中文回答", f"用{self._lang}回答")
            self._SUMMARIZE_SYSTEM_PROMPT = self._SUMMARIZE_SYSTEM_PROMPT.replace("用中文输出（原始字幕/代码保持原文）", f"用{self._lang}输出（原始字幕/代码保持原文）")
        self._clip_count = len(db.get("clips", []))

    def _fmt(self, sec):
        m, s = divmod(int(sec), 60)
        return f"{m:02d}:{s:02d}"

    def _ensure_models(self):
        if self._model is not None:
            return
        import io, contextlib
        with contextlib.redirect_stderr(io.StringIO()):
            from main import _load_models
            self._model, self._ctx, self._sampler, self._siglip, self._resampler = _load_models()
        print("  [lazy] models loaded")

    def unload_models(self):
        if self._model is None and self._ctx is None and self._siglip is None and self._resampler is None:
            return
        if self._sampler is not None and hasattr(self._sampler, "free"):
            self._sampler.free()
        self._ctx = None
        self._sampler = None
        self._siglip = None
        self._resampler = None
        self._model = None
        import gc
        gc.collect()
        print("  [unload] models released")

    def _ensure_clip_embeds(self):
        if self._clip_embeds is not None:
            return bool(self._clip_embeds)
        caps = [c.get("caption", "") for c in self.db.get("clips", [])]
        if not caps:
            self._clip_embeds = []
            return False
        print(f"  计算 {len(caps)} 条 caption 的 embedding...")
        self._clip_embeds = embed_texts(caps)
        print("  embedding 完成.")
        return bool(self._clip_embeds)

    def _parse_tool_arguments(self, tool_call):
        raw = (tool_call.get("function") or {}).get("arguments") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception as exc:
            return None, {
                "_source": "tool_argument_parser",
                "error": f"Invalid tool arguments JSON: {exc}",
                "raw_arguments": str(raw)[:1000],
            }
        if not isinstance(parsed, dict):
            return None, {
                "_source": "tool_argument_parser",
                "error": "Tool arguments must decode to a JSON object",
                "raw_arguments": str(raw)[:1000],
            }
        return parsed, None

    def _extract_json_path(self):
        import glob as _glob
        from pathlib import Path as _Path
        base = _Path(self.db.get("video_path", "")).stem
        output_root = _Path(MEDIA_VIDUNDER) / "output"
        explicit_output = self.db.get("extract_output")
        explicit_structure = self.db.get("structure_path")
        explicit_patterns = []
        if explicit_structure:
            explicit_patterns.append(str(explicit_structure))
        if explicit_output:
            explicit_patterns.append(str(_Path(explicit_output) / "*_structure.json"))
        for pattern in [
            *explicit_patterns,
            str(output_root / base / "*_structure.json"),
            str(output_root / f"{base}_extract" / "*_structure.json"),
            str(output_root / f"*{base}*" / "*_structure.json"),
            f"/tmp/{base}/*_structure.json",
            f"/tmp/{base}_test/*_structure.json",
            f"/tmp/*/{base}*_structure.json",
            f"/tmp/*{base.split('-')[0]}*/*_structure.json",
        ]:
            hits = _glob.glob(pattern)
            if hits:
                return sorted(hits)[-1]
        return None

    def _find_summary_path(self):
        for pattern in ["/tmp/*summary*.md", "/tmp/*_summary*.md"]:
            hits = sorted(_glob.glob(pattern))
            if hits:
                return hits[0]
        return None

    def _load_summary_text(self):
        if self._summary_text is not None:
            return self._summary_text
        summary_path = self._find_summary_path()
        if not summary_path:
            return ""
        self._summary_text = Path(summary_path).read_text(encoding="utf-8")
        return self._summary_text

    def _summary_sections(self, text: str):
        import re
        matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
        sections = []
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append({
                "title": match.group(1).strip(),
                "start": match.start(),
                "end": end,
                "content": text[match.start():end],
            })
        return sections

    def _find_summary_section(self, text: str, chapter: str):
        sections = self._summary_sections(text)
        query = str(chapter).strip()
        if not query:
            return None
        if query.isdigit():
            chapter_sections = [
                s for s in sections
                if s["title"].strip().lower() not in {"目录", "toc", "table of contents"}
            ]
            idx = int(query) - 1
            if 0 <= idx < len(chapter_sections):
                return chapter_sections[idx]
        q = query.lower()
        for section in sections:
            title = section["title"].lower()
            if q in title or title in q:
                return section
        return None

    def _load_dense_tokens(self, clip_idx):
        """Load pre-stored visual tokens for a clip."""
        if clip_idx < 0 or clip_idx >= len(self.db["clips"]):
            return None
        clip = self.db["clips"][clip_idx]
        path = clip.get("dense_tokens")
        if path and Path(path).exists():
            arr = np.load(path)
            return arr if arr.shape[0] > 0 else None
        return None

    def _find_clip_idx(self, sec):
        """Find the clip index for a given time in seconds."""
        for i, c in enumerate(self.db["clips"]):
            if c["start"] <= sec < c["end"]:
                return i
        return None

    def _local_ask(self, prompt, max_tokens=512):
        self._ensure_models()
        text = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        tokens = self._model.tokenize(text, add_special=True, parse_special=True)
        import minicpmv_llama
        self._ctx.clear_kv()
        chunk_size = 4096
        for off in range(0, len(tokens), chunk_size):
            chunk = tokens[off:off + chunk_size]
            batch = minicpmv_llama.LlamaBatch(len(chunk), embd_dim=0)
            batch.set_tokens(chunk, pos_offset=off)
            self._ctx.decode(batch)
        result, pos = bytearray(), len(tokens)
        for _ in range(max_tokens):
            tok = self._sampler.sample(self._ctx)
            self._sampler.accept(tok)
            if tok == self._model.eos_token:
                break
            result.extend(self._model.detokenize(tok))
            self._ctx.decode_token(tok, pos=pos)
            pos += 1
        return result.decode("utf-8", errors="replace")

    def _external_ask(self, prompt):
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = call_gemini(payload, timeout=180)
        return extract_text(r) or ""

    def _remote_ask(self, prompt, max_tokens=1024):
        """DeepSeek > Step > Gemini fallback chain."""
        if DEEPSEEK_API_KEY:
            r = call_deepseek(prompt, max_tokens=max_tokens)
            if r and len(r) > 20:
                return r
        if STEP_API_KEY:
            r = call_step(prompt, max_tokens=max_tokens)
            if r and len(r) > 20:
                return r
        return self._external_ask(prompt[:12000])

    _BUDGET_PROMPTS = {
        "low": (
            "简要描述这段10秒视频画面发生了什么，不超过80字。\n"
            "重点：操作类型（命令行/网页/设置）、是否在滚动/切换/输入。"
        ),
        "medium": (
            "直接描述这段10秒视频画面中的具体操作、界面内容和文字信息。\n"
            "要求：\n"
            "1. 如果画面中有命令行/终端，必须抄写出可见的完整命令文本\n"
            "2. 如果画面在滚动代码或切换页面，说明正在浏览什么内容\n"
            "3. 如果画面中有菜单/选项列表，列出可见的选项名称\n"
            "4. 所有屏幕上可见的重要文字信息都要体现"
        ),
        "high": (
            "【严格规则】只描述你从画面像素中能直接看到的内容，禁止任何推测或编造。"
            "无法清晰辨认的文字请写'画面模糊无法辨认'，不要猜测。\n\n"
            "详细描述这段10秒视频画面：\n"
            "1. 画面类型（终端/网页/IDE/设置界面/其他）\n"
            "2. 顶部标题或标签\n"
            "3. 主要内容：\n"
            "   - 命令行/终端：逐字抄写显示的命令和输出（不要推断未显示的命令）\n"
            "   - 网页：列出可见的标题、按钮、输入框、提示语\n"
            "   - IDE/代码：列出可见的关键代码行（函数名、变量、import）\n"
            "4. 字幕内容（如有）\n\n"
            "若画面变化快（滚动/切换），按时间顺序记录关键时刻。"
        ),
    }

    _BUDGET_N_PREDICT = {"low": 96, "medium": 256, "high": 768}

    def _caption_clip_with_budget(self, clip_idx: int, budget: str) -> str:
        from config import THINKING_BUDGET_FRAMES, FRAMES_PER_CLIP
        if budget not in THINKING_BUDGET_FRAMES:
            return self.db["clips"][clip_idx]["caption"]

        clip = self.db["clips"][clip_idx]
        n_frames = THINKING_BUDGET_FRAMES[budget]

        self._ensure_models()

        if n_frames == clip.get("frames_extracted", FRAMES_PER_CLIP):
            vis = self._load_dense_tokens(clip_idx)
            if vis is None:
                return clip["caption"]
        else:
            vis = self._run_vision_pipeline(clip_idx, n_frames)
            if vis is None:
                return clip["caption"]

        transcript = transcript_for_timerange(self.srt, clip["start"], clip["end"])
        transcript_hint = f"\n该时间段字幕:\n{transcript}" if transcript else ""

        question = self._BUDGET_PROMPTS[budget] + transcript_hint
        n_predict = self._BUDGET_N_PREDICT[budget]
        return self._visual_ask(question, vis, n_predict).strip()

    def _run_vision_pipeline(self, clip_idx: int, n_frames: int):
        from video_db import (_extract_clip_frames, _preprocess_frames,
                              _compute_onnx_inputs_v45, _get_video_fps)
        from config import NPPS, EMBED_DIM, MAX_SLICE_NUMS, VIDEO_FPS as VF
        from preprocess import (get_2d_sincos_pos_embed_numpy, encode_video_temporal_ids,
                                compute_temporal_embeddings_for_group)

        clip = self.db["clips"][clip_idx]
        vid_fps = _get_video_fps(self._video_path)
        frames = _extract_clip_frames(self._video_path, float(clip["start"]), float(clip["end"]),
                                       video_fps=VF, frames_per_clip=n_frames)
        if not frames:
            return None

        tiles, _ = _preprocess_frames(frames, max_slice_nums=MAX_SLICE_NUMS)

        siglip_features, patch_counts = [], []
        for tile in tiles:
            h, w = tile["h"], tile["w"]
            inputs = _compute_onnx_inputs_v45(h, w, NPPS)
            pv = tile["pixel_values"].astype(np.float32)
            feat = self._siglip.run(["siglip_features"],
                                     {"pixel_values": pv, "pos_ids": inputs["pos_ids"]})[0]
            siglip_features.append(feat)
            patch_counts.append(h * w)

        gf = np.concatenate(siglip_features, axis=0)
        sp = np.concatenate([
            get_2d_sincos_pos_embed_numpy(EMBED_DIM, (tiles[i]["h"], tiles[i]["w"]))
                .reshape(tiles[i]["h"] * tiles[i]["w"], -1)
            for i in range(len(tiles))
        ], axis=0)
        tids = encode_video_temporal_ids(
            np.linspace(0, len(frames) - 1, len(frames), dtype=int), vid_fps)
        te = compute_temporal_embeddings_for_group(patch_counts, tids, EMBED_DIM)

        inp_names = [i.name for i in self._resampler.get_inputs()]
        inputs = {inp_names[0]: gf.astype(np.float16),
                  inp_names[1]: sp.astype(np.float16),
                  inp_names[2]: te.astype(np.float16)}
        vt = self._resampler.run(None, inputs)[0]
        return vt.astype(np.float32)

    def summarize(self, thinking_budget: str = "low", top_n: int = 20, min_coverage: float = 0.60,
                  progress_cb=None):
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("summarize 需要 DEEPSEEK_API_KEY。本地 8B 模型摘要质量不足，不支持 legacy 模式。")

        try:
            result = self._summarize_inner(thinking_budget, top_n, min_coverage, progress_cb)
        finally:
            self._cleanup_dense_tokens()
        return result

    def _cleanup_dense_tokens(self):
        removed, freed = 0, 0
        for clip in self.db.get("clips", []):
            path = clip.get("dense_tokens")
            if path:
                p = Path(path)
                if p.exists():
                    freed += p.stat().st_size
                    p.unlink()
                    removed += 1
                clip["dense_tokens"] = None
        if removed:
            print(f"  [cleanup] removed {removed} .npy files ({freed / 1024**2:.0f} MB)")

    def _summarize_inner(self, thinking_budget, top_n, min_coverage, progress_cb=None):

        messages = [
            {"role": "system", "content": self._SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"请为这个视频生成完整的结构化总结。\n"
                f"视频时长：{self._fmt(self.db['clips'][-1]['end'] if self.db['clips'] else 0)}\n"
                f"共 {len(self.db['clips'])} 个片段，{len(self.srt)} 条字幕。\n"
                f"请先调用 detect_chapters 获取章节划分，然后对每个章节调用 summarize_chapter。"
            )},
        ]

        chapter_summaries = []
        total_chapters = 0
        max_rounds = 25
        recent_tool_calls = []

        for round_i in range(max_rounds):
            resp = call_deepseek_tools(messages, _SUMMARIZE_TOOL_DEFS, max_tokens=4096)
            if not resp or "choices" not in resp:
                break

            choice = resp["choices"][0]
            assistant_msg = dict(choice["message"])
            finish_reason = choice.get("finish_reason", "")

            if assistant_msg.get("tool_calls") and assistant_msg.get("content") is None:
                assistant_msg["content"] = ""
            if isinstance(assistant_msg.get("content"), list):
                assistant_msg["content"] = ""

            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls", [])
            content = (assistant_msg.get("content") or "").strip()

            if not tool_calls and content and len(content) > 200:
                if chapter_summaries:
                    return self._assemble_summary(chapter_summaries, min_coverage)
                return self._inject_slides(content)

            if not tool_calls:
                if content:
                    print(f"  [summarize] transitional content, length={len(content)}")
                break

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                tc_id = tc["id"]
                fn_args, parse_error = self._parse_tool_arguments(tc)
                if parse_error:
                    result_str = _json.dumps(parse_error, ensure_ascii=False)
                    print(f"  [warn] malformed summarize tool args for {fn_name}: {result_str[:300]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_str,
                    })
                    continue

                call_sig = f"{fn_name}:{sorted(fn_args.items())}"
                recent_tool_calls.append(call_sig)
                if len(recent_tool_calls) > 3 and sum(
                    1 for s in recent_tool_calls[-3:] if s == call_sig
                ) >= 3:
                    print(f"  [warn] tool loop detected: {fn_name}, forcing final answer")
                    messages.append({"role": "user", "content": "停止调用工具，根据已有信息直接给出最终总结。"})
                    break

                print(f"  [summarize tool] {fn_name}({fn_args})")
                result = self._execute_tool(fn_name, fn_args)
                result_str = _json.dumps(result, ensure_ascii=False)[:30000]
                print(f"  [result] {result_str[:150]}...")

                if fn_name == "detect_chapters" and isinstance(result, dict):
                    chapters = result.get("chapters", [])
                    if chapters:
                        total_chapters = len(chapters)

                if fn_name == "summarize_chapter" and "summary" in result:
                    chapter_summaries.append(result["summary"])
                    if progress_cb and total_chapters > 0:
                        progress_cb(len(chapter_summaries), total_chapters)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                })
            else:
                continue
            break

        if chapter_summaries:
            return self._assemble_summary(chapter_summaries, min_coverage)

        messages.append({
            "role": "user",
            "content": "请根据以上所有工具调用的结果，直接生成完整的结构化总结。不要再调用任何工具。使用 Markdown 格式，包含章节标题和时间戳。",
        })
        final_resp = call_deepseek_tools(messages, [], max_tokens=8192)
        if final_resp and "choices" in final_resp:
            return self._inject_slides(final_resp["choices"][0]["message"].get("content", "信息不足，无法生成总结。"))
        return "信息不足，无法生成总结。"

    def _assemble_summary(self, chapter_summaries: list, min_coverage: float = 0.60) -> str:
        extract_path = self._extract_json_path()
        slides_data = []
        slides_base = None
        if extract_path:
            import json as _json_mod
            try:
                with open(extract_path) as f:
                    structure = _json_mod.load(f)
                slides_data = structure.get("slides", [])
                slides_base = str(Path(extract_path).parent)
            except Exception:
                pass

        clip_captions = {}
        for c in self.db.get("clips", []):
            clip_captions[int(c["start"] / 10)] = c.get("caption", "")

        header = f"# 视频结构化总结\n\n> 共 {len(chapter_summaries)} 个章节\n\n"
        toc = "## 目录\n\n"
        body = ""
        for i, summary in enumerate(chapter_summaries, 1):
            title_match = ""
            for line in summary.split("\n"):
                if line.startswith("##") or line.startswith("#"):
                    title_match = line.strip("# ").strip()
                    break

            import re as _re
            start_sec, end_sec = 0, 0
            time_match = _re.search(r'\[(\d{2}:\d{2})-(\d{2}:\d{2})\]', summary[:200])
            if time_match:
                for ts, attr in [(time_match.group(1), 'start'), (time_match.group(2), 'end')]:
                    m, s = ts.split(':')
                    val = int(m) * 60 + int(s)
                    if attr == 'start':
                        start_sec = val
                    else:
                        end_sec = val

            chapter_slides = []
            if slides_data and start_sec < end_sec:
                max_slides = SUMMARY_SLIDES_PER_CHAPTER
                candidates = [s for s in slides_data
                              if start_sec <= s.get("time", -1) <= end_sec
                              and s.get("image_path") and Path(s["image_path"]).exists()]
                if len(candidates) > max_slides:
                    step = len(candidates) // max_slides
                    candidates = candidates[::step][:max_slides]
                for s in candidates:
                    t = s.get("time", 0)
                    mm, sc = divmod(int(t), 60)
                    img_path = self._crop_slide_for_summary(s, min_coverage)
                    display_path = img_path or s["image_path"]
                    if slides_base:
                        display_path = os.path.relpath(display_path, slides_base)
                    chapter_slides.append(f'![{mm:02d}:{sc:02d}]({display_path})')

            toc += f"{i}. {title_match or f'第{i}章'}\n"
            slide_block = "\n".join(chapter_slides) + "\n\n" if chapter_slides else ""
            body += f"\n---\n\n{summary}\n\n{slide_block}"

        total_images = body.count("![")

        return header + toc + "\n---\n" + body

    def _crop_slide_for_summary(self, slide: dict, min_coverage: float = 0.60) -> str | None:
        """Use Gemini to get precise bbox for a single slide, crop and save.

        Returns path to cropped image, or None to use original.
        """
        img_path = slide.get("image_path", "")
        if not img_path or not Path(img_path).exists():
            return None

        cropped_path = str(Path(img_path).with_suffix(".cropped.png"))
        if Path(cropped_path).exists():
            return cropped_path

        try:
            from layout_detector import get_vision_bbox
            img = PILImage.open(img_path)
            bbox = get_vision_bbox(img)
            if bbox is None:
                return None
            x, y, w, h = bbox
            ow, oh = img.size
            coverage = (w * h) / (ow * oh)
            if coverage < min_coverage or coverage > 0.98:
                return None
            cropped = img.crop((x, y, x + w, y + h))
            cropped.save(cropped_path)
            return cropped_path
        except Exception:
            return None

    def _inject_slides(self, text: str) -> str:
        import re as _re, json as _json_mod
        extract_path = self._extract_json_path()
        if not extract_path:
            return text
        try:
            with open(extract_path) as f:
                structure = _json_mod.load(f)
        except Exception:
            return text
        slides_base = str(Path(extract_path).parent)
        slides = [s for s in structure.get("slides", [])
                  if s.get("image_path") and Path(s["image_path"]).exists()]
        if not slides:
            return text

        # Find chapter headers and inject slides after each
        def _insert_after_header(match):
            header_line = match.group(0)
            time_match = _re.search(r'\[(\d{2}:\d{2})-(\d{2}:\d{2})\]', header_line)
            if not time_match:
                return header_line
            start = int(time_match.group(1).split(':')[0]) * 60 + int(time_match.group(1).split(':')[1])
            end = int(time_match.group(2).split(':')[0]) * 60 + int(time_match.group(2).split(':')[1])
            chapter_slides = [s for s in slides if start <= s.get("time", -1) <= end]
            if len(chapter_slides) > 3:
                step = len(chapter_slides) // 3
                chapter_slides = chapter_slides[::step][:3]
            if not chapter_slides:
                return header_line
            img_lines = []
            for s in chapter_slides:
                t = s.get("time", 0)
                m, sc = divmod(int(t), 60)
                img_lines.append(f'\n![{m:02d}:{sc:02d}]({os.path.relpath(s["image_path"], slides_base)})')
            return header_line + "".join(img_lines)

        result = _re.sub(r'^## .+\[\d{2}:\d{2}-\d{2}:\d{2}\].*$', _insert_after_header, text, flags=_re.MULTILINE)
        return result

    def _detect_chapters(self, min_chapter_secs: int = 120) -> dict:
        if not self.srt or len(self.srt) < 5:
            return {"_source": "detect_chapters", "error": "字幕不足，无法检测章节"}

        window_size = 20
        step = 10
        texts = []
        times = []
        for i in range(0, len(self.srt) - window_size, step):
            chunk = " ".join(e["text"] for e in self.srt[i:i + window_size])
            texts.append(chunk)
            times.append(self.srt[i]["start"])

        if not texts:
            return {"_source": "detect_chapters", "error": "字幕太少"}

        embeddings = embed_texts(texts)

        sims = [cosine_similarity(embeddings[i], embeddings[i - 1]) for i in range(1, len(embeddings))]
        if not sims:
            return {"_source": "detect_chapters", "error": "无法计算相似度"}

        import numpy as _np
        sim_arr = _np.array(sims)
        mean_sim = float(sim_arr.mean())
        std_sim = float(sim_arr.std())

        # Adaptive threshold: detect points significantly below mean
        threshold = mean_sim - 1.5 * std_sim
        boundaries = [0]
        for i in range(len(sims)):
            if sims[i] < threshold:
                boundaries.append(i)
            elif i > 0 and (sims[i - 1] - sims[i]) > 3 * std_sim and sims[i] < mean_sim:
                boundaries.append(i)

        # Merge boundaries that are too close
        merged = [boundaries[0]]
        for b in boundaries[1:]:
            if b - merged[-1] >= 3:
                merged.append(b)
        boundaries = merged

        # Ensure minimum chapter duration
        chapters = []
        prev_time = 0
        for j, b_idx in enumerate(boundaries):
            start_time = prev_time
            if j + 1 < len(boundaries):
                next_b = boundaries[j + 1]
                end_time = times[next_b] if next_b < len(times) else self.srt[-1]["end"]
            else:
                end_time = self.srt[-1]["end"]

            if end_time - start_time < min_chapter_secs:
                continue

            chapters.append({
                "chapter": len(chapters) + 1,
                "title": f"章节 {len(chapters) + 1}",
                "start_seconds": round(start_time, 1),
                "end_seconds": round(end_time, 1),
                "start_time": self._fmt(start_time),
                "end_time": self._fmt(end_time),
                "duration": round(end_time - start_time),
                "preview": " ".join(
                    e["text"] for e in self.srt
                    if start_time <= e["start"] <= end_time
                )[:300],
            })
            prev_time = end_time

        # Batch-generate chapter titles in one call
        if chapters:
            from external_api import call_doubao
            outlines = "\n".join(
                f"{ch['chapter']}. ({ch['start_time']}-{ch['end_time']}) {ch.get('preview', '')[:200]}"
                for ch in chapters
            )
            title_resp = call_doubao(
                f"为以下视频章节各生成一个简短标题（5-15字，不要序号和标点）。\n每行输出格式：序号. 标题\n\n{outlines}",
                max_tokens=500,
            )
            import re
            for line in title_resp.split("\n"):
                m = re.match(r'(\d+)[\.\)、]\s*(.+)', line.strip())
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(chapters):
                        chapters[idx]["title"] = m.group(2).strip()

        # Fix first chapter start
        if chapters:
            chapters[0]["start_seconds"] = 0
            chapters[0]["start_time"] = "00:00"

        # Fallback: energy minima when embedding fails (≤2 chapters for >10min video)
        duration = self.srt[-1]["end"] if self.srt else 0
        if len(chapters) <= 2 and duration > 600:
            import numpy as _np2
            target = max(3, int(duration / 240) + 1)  # ~4min per chapter
            # Take N-1 lowest-similarity points as boundaries, sorted by time
            ranked = sorted(enumerate(sims), key=lambda x: x[1])
            fallback = [0]
            for idx, _ in ranked[:target - 1]:
                if idx > 0:
                    fallback.append(idx)
            fallback.sort()
            # Merge by min distance
            merged_fb = [fallback[0]]
            for idx in fallback[1:]:
                last_t = times[merged_fb[-1]] if merged_fb[-1] < len(times) else 0
                cur_t = times[idx] if idx < len(times) else 0
                if cur_t - last_t >= min_chapter_secs:
                    merged_fb.append(idx)
            # Build chapters from fallback boundaries
            chapters_fb = []
            prev_time = 0
            for j, b_idx in enumerate(merged_fb):
                start_time = prev_time
                next_idx = merged_fb[j + 1] if j + 1 < len(merged_fb) else len(times) - 1
                end_time = times[next_idx] if next_idx < len(times) else self.srt[-1]["end"]
                if end_time - start_time < min_chapter_secs:
                    continue
                chapters_fb.append({
                    "chapter": len(chapters_fb) + 1,
                    "title": f"分组 {len(chapters_fb) + 1}",
                    "start_seconds": round(start_time, 1),
                    "end_seconds": round(end_time, 1),
                    "start_time": self._fmt(start_time),
                    "end_time": self._fmt(end_time),
                    "duration": round(end_time - start_time),
                    "preview": " ".join(
                        e["text"] for e in self.srt if start_time <= e["start"] <= end_time
                    )[:300],
                })
                prev_time = end_time
            if chapters_fb:
                from external_api import call_doubao
                outlines = "\n".join(
                    f"{ch['chapter']}. ({ch['start_time']}-{ch['end_time']}) {ch.get('preview', '')[:200]}"
                    for ch in chapters_fb
                )
                title_resp = call_doubao(
                    f"为以下视频分组各生成一个简短标题（5-15字，不要序号和标点）。\n每行输出格式：序号. 标题\n\n{outlines}",
                    max_tokens=500,
                )
                for line in title_resp.split("\n"):
                    m2 = re.match(r'(\d+)[\.\)、]\s*(.+)', line.strip())
                    if m2:
                        idx2 = int(m2.group(1)) - 1
                        if 0 <= idx2 < len(chapters_fb):
                            chapters_fb[idx2]["title"] = m2.group(2).strip()
                chapters_fb[0]["start_seconds"] = 0
                chapters_fb[0]["start_time"] = "00:00"
                chapters = chapters_fb
                threshold = float(_np2.mean([s[1] for s in ranked[:target-1]]))

        return {
            "_source": f"detect_chapters (adaptive threshold={threshold:.3f}, mean_sim={mean_sim:.3f})",
            "total_chapters": len(chapters),
            "chapters": chapters,
        }

    def _get_extracted_content(self, start_sec: float, end_sec: float) -> dict:
        transcript = self._transcript_in_range(start_sec, end_sec)

        clips_info = []
        for c in self.db["clips"]:
            if c["start"] < end_sec and c["end"] > start_sec:
                clips_info.append({
                    "time": f"{self._fmt(c['start'])}-{self._fmt(c['end'])}",
                    "caption": c["caption"],
                })

        return {
            "_source": "get_extracted_content",
            "_time_range": f"[{self._fmt(start_sec)}-{self._fmt(end_sec)}]",
            "transcript": transcript,
            "clip_captions": clips_info,
        }

    @staticmethod
    def _strip_preamble(text: str) -> str:
        import re
        text = re.sub(
            r'^[\s\S]*?(?=##\s)',
            '',
            text,
            count=1,
        )
        patterns = [
            r'^好的[，,].*?(?=\n##\s|\n###\s)',
            r'^作为您的?.*?(?=\n##\s|\n###\s)',
            r'^以下是.*?(?=\n##\s|\n###\s)',
            r'^---+\s*\n---+\s*\n',
        ]
        for pat in patterns:
            text = re.sub(pat, '', text, count=1, flags=re.DOTALL)
        return text.strip()

    def _summarize_chapter(self, start_sec: float, end_sec: float, chapter_title: str) -> dict:
        transcript = self._transcript_in_range(start_sec, end_sec)

        captions = []
        for c in self.db["clips"]:
            if c["start"] < end_sec and c["end"] > start_sec:
                captions.append(f"[{self._fmt(c['start'])}] {c['caption']}")

        caption_text = "\n".join(captions)

        # Inject extract data (code, terminal, slides) in one read
        ocr_code_section = ""
        terminal_section = ""
        slides_section = ""
        extract_path = self._extract_json_path()
        if extract_path:
            import json as _json_mod, re as _re
            try:
                with open(extract_path) as f:
                    structure = _json_mod.load(f)

                code_candidates = [
                    (snap["time"], snap["code"].strip())
                    for snap in structure.get("code_snapshots", [])
                    if start_sec <= snap.get("time", -1) <= end_sec and snap.get("code", "").strip()
                ]
                term_candidates = [
                    (term["time"], term["text"].strip())
                    for term in structure.get("terminal_outputs", [])
                    if start_sec <= term.get("time", -1) <= end_sec and term.get("text", "").strip()
                ]
                slide_candidates = [
                    (slide["time"], slide["ocr_text"].strip())
                    for slide in structure.get("slides", [])
                    if start_sec <= slide.get("time", -1) <= end_sec and slide.get("ocr_text", "").strip()
                ]

                # Dedup consecutive entries with high word overlap
                def _dedup(candidates, min_unique_ratio=0.2):
                    kept = []
                    for t, text in candidates:
                        if not kept:
                            kept.append((t, text))
                            continue
                        _, prev_text = kept[-1]
                        prev_words = set(prev_text.split())
                        curr_words = set(text.split())
                        if not prev_words or not curr_words:
                            kept.append((t, text))
                            continue
                        overlap = len(prev_words & curr_words) / max(len(prev_words), 1)
                        if overlap < (1 - min_unique_ratio):
                            kept.append((t, text))
                    return kept

                term_deduped = _dedup(term_candidates)
                code_deduped = _dedup(code_candidates)

                # Soft cap: only trim if a category is excessively large
                # terminal: always keep all after dedup (max ~25 entries, ~20K chars)
                # code: cap at 30K chars (lecture5 can have 48+ code snippets per chapter)
                # slides: cap at 15K chars
                def _cap_by_chars(candidates, max_chars):
                    total = sum(len(t) for _, t in candidates)
                    if total <= max_chars:
                        return candidates
                    # keep evenly spaced subset
                    n = max(5, len(candidates) * max_chars // total)
                    step = max(1, len(candidates) // n)
                    return candidates[::step][:n]

                term_selected = term_deduped
                code_selected = _cap_by_chars(code_deduped, 30000)
                slide_selected = _cap_by_chars(slide_candidates, 15000)

                if code_selected:
                    ocr_code_section = "\n\n画面中识别到的代码（OCR 提取）：\n" + "\n".join(
                        f"[{self._fmt(t)}] {text}" for t, text in code_selected)
                if term_selected:
                    terminal_section = "\n\n终端/命令行输出（OCR 提取，包含实际命令和执行结果）：\n" + "\n".join(
                        f"[{self._fmt(t)}] {text}" for t, text in term_selected)
                if slide_selected:
                    slides_section = "\n\nPPT/截图中的文字（OCR 提取）：\n" + "\n".join(
                        f"[{self._fmt(t)}] {text}" for t, text in slide_selected)
            except Exception:
                pass

        prompt = (
            f"请为视频章节「{chapter_title}」（{self._fmt(start_sec)}-{self._fmt(end_sec)}）生成详细的结构化摘要。\n\n"
            f"该章节字幕：\n{transcript}\n\n"
            f"{terminal_section}{ocr_code_section}{slides_section}\n\n"
            f"该章节画面描述（AI caption，仅供参考；优先采用上方 OCR 逐字抄录的终端/代码/幻灯片文字）：\n{caption_text}"
            f"要求：\n"
            f"- 严格按照时间顺序，逐段展开叙述，不要遗漏任何重要内容\n"
            f"- 每个知识点/操作步骤必须展开描述：先说明背景/目的，再写出具体内容（代码要完整写出，命令要写出完整命令行，配置要写出具体参数值）\n"
            f"- 不要使用模糊描述（如\"输入命令\"\"修改代码\"），必须写出具体内容\n"
            f"- 章节时长 {int((end_sec-start_sec)/60)} 分钟，输出长度应与此匹配（每分钟视频约10-15行摘要）\n\n"
            f"输出格式：\n\n"
            f"## {chapter_title} [{self._fmt(start_sec)}-{self._fmt(end_sec)}]\n\n"
            f"### 时间线叙事\n\n"
            f"**[MM:SS-MM:SS] | 小标题**\n"
            f"- 详细展开描述该时间段的内容\n"
            f"- 如有代码/命令/配置，用代码块展示\n\n"
            f"### 要点总结\n\n"
            f"3-5 句话概括本章核心内容和学习目标。\n\n"
            f"直接输出摘要内容，不要加任何开头语、寒暄或解释。"
        )

        from external_api import call_deepseek, call_knowledge_llm
        chapter_secs = end_sec - start_sec
        max_tok = min(16384, max(4000, int(chapter_secs / 60 * 400)))
        summary = call_deepseek(prompt, max_tokens=max_tok)
        if not summary or len(summary) < 50:
            summary = call_knowledge_llm(prompt, max_tokens=max_tok)

        summary = self._strip_preamble(summary or "")

        return {
            "_source": "summarize_chapter",
            "chapter_title": chapter_title,
            "time_range": f"{self._fmt(start_sec)}-{self._fmt(end_sec)}",
            "summary": summary or "信息不足，无法生成该章节摘要。",
        }

    _TEMPORAL_BEFORE = ["之前", "以前", "上一个", "前一个", "前面的", "之前的"]
    _TEMPORAL_AFTER = ["之后", "然后", "接下来", "下一步", "接着", "后的", "以后", "完后", "过后", "随后", "紧接着"]
    _TEMPORAL_EITHER = ["第一个", "第一个命令", "第一个操作"]

    def _has_temporal_intent(self, question):
        all_kw = self._TEMPORAL_BEFORE + self._TEMPORAL_AFTER + self._TEMPORAL_EITHER
        return any(kw in question for kw in all_kw)

    def _temporal_direction(self, question):
        """Returns (expand_forward, expand_backward)."""
        fwd = any(kw in question for kw in self._TEMPORAL_AFTER)
        bwd = any(kw in question for kw in self._TEMPORAL_BEFORE)
        if not fwd and not bwd:
            fwd = True
        return fwd, bwd

    _SYSTEM_PROMPT = (
        "你是视频分析助手。你可以使用以下工具来分析视频内容：\n"
        "1. search_transcript - 搜索字幕关键词，定位时间点\n"
        "2. read_transcript_range - 读取指定时间段的原始字幕（最可靠的信息源）\n"
        "3. visual_inspect - 对指定时间段做视觉分析（VQA），确认画面内容\n"
        "4. search_similar_clips - 通过语义相似度搜索相关的视频片段描述\n"
        "5. inspect_scrolling - 密集抽帧拼接长图，GLM-OCR 一次性识别滚动文本\n"
        "6. detect_chapters - 检测视频章节结构，返回话题分段\n"
        "7. get_extracted_content - 获取指定时间段的已提取内容（slides/code/transcript）\n"
        "8. summarize_chapter - 对单个章节生成结构化摘要\n"
        "9. read_summary - 读取已生成 summary 的目录或指定章节内容\n"
        "10. update_summary - 修改已生成 summary 中的指定章节文本\n"
        "11. inspect_slide - 使用 GLM-OCR 分析指定幻灯片图片\n"
        "12. identify_image - 使用云端 VLM 分析指定时间段的视频帧（支持多帧采样）\n\n"
        "字幕中的别名：x-ui = 三叉UI = 叉杠UI = 3X-UI\n\n"
        "分析策略：\n"
        "- 先用 search_transcript 或 search_similar_clips 定位大致时间\n"
        "- 用 read_transcript_range 读取该时间段原始字幕确认细节\n"
        "- 只在字幕信息不足以确认具体操作（如命令文本、界面内容）时，才用 visual_inspect\n"
        "- 需要精确识别命令/代码/URL 时，优先用 inspect_scrolling（GLM-OCR），不要依赖 visual_inspect\n\n"
        "- 需要读取或修正已生成摘要时，先用 read_summary 定位章节，再用 update_summary 精确替换文本\n"
        "- 需要确认单张幻灯片内容时用 inspect_slide；需要识别画面中的物体/人物/Logo 时用 identify_image\n\n"
        "重要：\n"
        "- 当你已经有足够信息时，**立即停止调用工具并直接给出最终答案**\n"
        "- 最终答案必须包含：具体事实 + 时间戳 + 来源（字幕/视觉）\n"
        "- 用中文回答"
    )

    _SYSTEM_PROMPT_NO_SRT = (
        "你是视频分析助手。当前视频没有字幕，所有信息必须从画面中提取。\n\n"
        "可用工具：\n"
        "1. search_similar_clips - 通过 caption embedding 语义搜索定位相关片段（首要定位手段）\n"
        "2. inspect_scrolling - 密集抽帧拼接长图，GLM-OCR 精确识别画面中所有可见文本【核心工具】\n"
        "3. visual_inspect - MiniCPM-V 8B 视觉描述（仅用于理解画面大意，不可信精确文本）\n"
        "4. get_extracted_content - 获取已提取的 slides/code/terminal OCR 内容\n"
        "5. identify_image - 云端 VLM 分析画面（识别物体/人物/Logo 等非文字内容）\n"
        "6. inspect_slide - GLM-OCR 读取指定幻灯片图片\n"
        "7. read_summary / update_summary - 读取/修改已生成的摘要\n\n"
        "无字幕分析策略（严格按此顺序）：\n"
        "1. 用 search_similar_clips 根据问题语义定位相关 clip 的时间范围\n"
        "2. 对定位到的时间范围调用 inspect_scrolling 做精确 OCR（这是获取具体文本/数字/代码/命令的唯一可靠来源）\n"
        "3. 只有在需要理解画面整体结构（如界面布局、操作流程）时才用 visual_inspect\n"
        "4. 绝不要仅凭 caption 或 visual_inspect 的结果回答涉及具体文本/数字/命令的问题\n\n"
        "工具可靠性排序（高→低）：\n"
        "  inspect_scrolling (GLM-OCR 精确文本) > get_extracted_content (已提取OCR) "
        "> identify_image (云端VLM) > visual_inspect (8B本地VLM, 可能幻觉) "
        "> search_similar_clips (caption, 仅供参考定位)\n\n"
        "caption 和 visual_inspect 可能产生幻觉（编造不存在的命令、数字、文件名），"
        "涉及具体事实时必须用 inspect_scrolling 交叉验证。\n\n"
        "重要：\n"
        "- 当你已经有足够信息时，**立即停止调用工具并直接给出最终答案**\n"
        "- 最终答案必须包含：具体事实 + 时间戳 + 来源（OCR/视觉）\n"
        "- 用中文回答"
    )

    _SUMMARIZE_SYSTEM_PROMPT = (
        "你是视频结构化总结助手。你的任务是为视频生成一份带章节结构的完整讲义。\n\n"
        "工作流程：\n"
        "1. 先调用 detect_chapters 获取视频的章节划分\n"
        "2. 对每个章节调用 summarize_chapter 生成结构化摘要\n"
        "3. 最后将所有章节摘要组合成完整的结构化文档输出\n\n"
        "输出格式要求：\n"
        "- 使用 Markdown 格式\n"
        "- 一级标题 # 为视频总标题\n"
        "- 二级标题 ## 为章节（含时间范围）\n"
        "- 每个章节用时间线叙事：按时间顺序描述发生了什么（操作→变化→结果）\n"
        "- 视频中出现的代码和界面操作必须体现（这是区别于纯字幕总结的关键优势）\n"
        "- 最后附上完整的目录（Table of Contents）\n"
        "- 用中文输出（原始字幕/代码保持原文）\n\n"
        "注意：不要跳过任何章节，确保覆盖完整视频内容。"
    )

    def reset_conversation(self):
        if not self.srt or len(self.srt) < 5:
            prompt = self._SYSTEM_PROMPT_NO_SRT
        else:
            prompt = self._SYSTEM_PROMPT
        self._messages = [{"role": "system", "content": prompt}]

    def ask(self, question, max_rounds=6, on_event=None):
        if not DEEPSEEK_API_KEY:
            return self._ask_legacy(question)

        if not hasattr(self, "_messages") or not self._messages:
            self.reset_conversation()

        self._messages.append({"role": "user", "content": question})

        for round_i in range(max_rounds):
            resp = call_deepseek_tools(self._messages, _TOOL_DEFS, max_tokens=4096)
            if not resp or "choices" not in resp:
                break

            choice = resp["choices"][0]
            assistant_msg = dict(choice["message"])
            finish_reason = choice.get("finish_reason", "")

            if assistant_msg.get("tool_calls") and assistant_msg.get("content") is None:
                assistant_msg["content"] = ""
            if isinstance(assistant_msg.get("content"), list):
                assistant_msg["content"] = ""

            self._messages.append(assistant_msg)

            if finish_reason == "length":
                print(f"  [warn] DeepSeek hit max_tokens=4096 on tool-call round {round_i+1}, continuing")

            tool_calls = assistant_msg.get("tool_calls", [])
            content = (assistant_msg.get("content") or "").strip()

            if not tool_calls and content and len(content) > 30 and finish_reason != "length":
                if on_event:
                    on_event({"type": "answer", "content": content})
                return content

            if not tool_calls:
                if content:
                    print(f"  [warn] transitional content, length={len(content)}: {content[:80]!r}")
                break

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                tc_id = tc["id"]
                fn_args, parse_error = self._parse_tool_arguments(tc)
                if parse_error:
                    result_str = _json.dumps(parse_error, ensure_ascii=False)
                    print(f"  [warn] malformed tool args for {fn_name}: {result_str[:300]}")
                    if on_event:
                        on_event({"type": "tool_result", "name": fn_name, "summary": parse_error["error"]})
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_str,
                    })
                    continue

                if on_event:
                    on_event({"type": "tool_call", "name": fn_name, "args": fn_args})

                print(f"  [tool] {fn_name}({fn_args})")
                result = self._execute_tool(fn_name, fn_args)
                result_str = _json.dumps(result, ensure_ascii=False)[:4000]
                print(f"  [tool_result] {result_str[:200]}...")

                if on_event:
                    summary = result_str[:80] if isinstance(result_str, str) else str(result)[:80]
                    on_event({"type": "tool_result", "name": fn_name, "summary": summary})

                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                })

        if on_event:
            on_event({"type": "thinking"})

        self._messages.append({
            "role": "user",
            "content": "请根据以上所有工具调用的结果，直接给出最终答案。不要再调用任何工具。",
        })
        final_resp = call_deepseek_tools(self._messages, [], max_tokens=4096)
        if final_resp and "choices" in final_resp:
            answer = final_resp["choices"][0]["message"].get("content", "信息不足，无法回答。")
            self._messages.append({"role": "assistant", "content": answer})
            if on_event:
                on_event({"type": "answer", "content": answer})
            return answer
        answer = "信息不足，无法回答。"
        if on_event:
            on_event({"type": "answer", "content": answer})
        return answer

    def _run_glm_ocr(self, image, prompt="Text Recognition:") -> str:
        self._unload_minicpmv_before_ocr()
        return call_glm_ocr(image, prompt)

    def _chunked_ocr(self, image: PILImage.Image, max_chunk_height: int = 1800) -> str:
        self._unload_minicpmv_before_ocr()
        from external_api import ocr_long_image
        return ocr_long_image(image, max_chunk_height=max_chunk_height, prompt="Text Recognition:")

    def _unload_minicpmv_before_ocr(self):
        if any(x is not None for x in (self._model, self._ctx, self._siglip, self._resampler)):
            print("  [model-switch] unloading MiniCPM-V before GLM-OCR")
            self.unload_models()

    def _stitch_frames(self, frames, pad=4):
        from frame_stitcher import deduplicate_frames, stitch_scrolling_frames
        if not frames:
            return None
        deduped = deduplicate_frames(frames)
        if len(deduped) <= 1:
            from PIL import Image as PILImage
            return deduped[0] if deduped else None
        try:
            return stitch_scrolling_frames(deduped)
        except Exception as e:
            print(f"  [stitch] fallback to naive concat: {e}")
            from PIL import Image as PILImage
            max_w = max(f.width for f in deduped)
            total_h = sum(f.height for f in deduped) + pad * (len(deduped) - 1)
            stitched = PILImage.new("RGB", (max_w, total_h), color=(255, 255, 255))
            y = 0
            for f in deduped:
                stitched.paste(f.resize((f.width, f.height)), (0, y))
                y += f.height + pad
            return stitched

    def _extract_dense_frames(self, start_sec, end_sec, n_frames=12):
        import av, numpy as np
        c = av.open(str(self._video_path))
        stream = c.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 30.0
        time_base = float(stream.time_base)

        duration = end_sec - start_sec
        step_secs = duration / n_frames
        target_ts = np.linspace(start_sec + step_secs / 2, end_sec - step_secs / 2, n_frames)

        c.seek(int(start_sec / time_base), stream=stream)
        frames, fi = [], 0
        for frame in c.decode(stream):
            pts = float(frame.pts * time_base) if frame.pts is not None else 0
            if pts > end_sec + 1:
                break
            while fi < n_frames and pts >= target_ts[fi]:
                img = frame.to_image()
                if img.mode != "RGB":
                    img = img.convert("RGB")
                frames.append(img)
                fi += 1
            if fi >= n_frames:
                break
        c.close()
        return frames[:n_frames]

    def _extract_mid_frame(self, start_sec, end_sec):
        from video_db import _extract_clip_frames
        mid = (start_sec + end_sec) / 2
        frames = _extract_clip_frames(self._video_path, max(0, mid - 0.5), mid + 0.5, video_fps=10, frames_per_clip=1)
        return frames[0] if frames else None

    def _execute_tool(self, name: str, args: dict):
        if name == "search_transcript":
            hits = search_transcript(self.srt, args["query"], top_k=args.get("top_k", 10))
            return {
                "_source": "search_transcript",
                "_description": f"在字幕中搜索关键词 '{args['query']}'，共 {len(hits)} 条命中",
                "results": [{"time": self._fmt(e["start"]), "text": e["text"], "score": e.get("score", 0)} for e in hits],
            }

        if name == "read_transcript_range":
            text = self._transcript_in_range(args["start_seconds"], args["end_seconds"])
            return {
                "_source": "read_transcript_range",
                "_description": f"读取 [{self._fmt(args['start_seconds'])}-{self._fmt(args['end_seconds'])}] 时间段原始字幕（最可靠）",
                "transcript": text,
            }

        if name == "visual_inspect":
            s, e = args["start_seconds"], args["end_seconds"]
            result = self.frame_inspect(args["question"], s, e)
            return {
                "_source": "visual_inspect (MiniCPM-V 4.5 8B 本地VLM)",
                "_time_range": f"[{self._fmt(s)}-{self._fmt(e)}]",
                "_note": "8B 模型在细粒度 OCR（命令/URL/代码）上可能幻觉。精确 OCR 请用 compare_ocr 或 inspect_scrolling（均基于 GLM-OCR）。",
                "answer": result or "视觉分析无法回答该问题",
            }

        if name == "compare_ocr":
            s, e = args["start_seconds"], args["end_seconds"]
            frame = self._extract_mid_frame(s, e)
            if frame is None:
                return {"_source": "compare_ocr", "error": f"无法提取 [{self._fmt(s)}-{self._fmt(e)}] 画面"}
            glm_result = self._run_glm_ocr(frame, "Text Recognition:")
            cp_v_result = ""
            try:
                self._ensure_models()
                vis = self._frames_to_visual([frame])
                if vis is not None:
                    cp_v_result = self._visual_ask("请抄写画面中所有可见的命令文本、代码和文字信息。", vis, 256)
            except Exception:
                pass
            return {
                "_source": "compare_ocr",
                "_time_range": f"[{self._fmt(s)}-{self._fmt(e)}]",
                "GLM_OCR_0_9B_llama_cpp": glm_result[:2000],
                "MiniCPM_V_8B": cp_v_result[:2000],
                "_verdict_hint": "GLM-OCR 0.9B (llama.cpp server + MTP) 专为 OCR 优化，结果通常更可靠。MiniCPM-V 8B 为通用 VLM，在细粒度文字识别上可能幻觉。优先采信 GLM-OCR。",
            }

        if name == "inspect_scrolling":
            s, e = args["start_seconds"], args["end_seconds"]
            frames = self._extract_dense_frames(s, e, n_frames=10)
            if not frames:
                return {"_source": "inspect_scrolling", "error": f"无法提取 [{self._fmt(s)}-{self._fmt(e)}] 的帧"}
            stitched = self._stitch_frames(frames)
            if stitched is None:
                return {"_source": "inspect_scrolling", "error": "帧拼接失败"}
            prompt = args.get("question", "Text Recognition:")
            if "Text Recognition:" not in prompt and "Formula Recognition:" not in prompt and "Table Recognition:" not in prompt:
                prompt = f"Text Recognition: {prompt}"
            if stitched.height > 2000:
                ocr_result = self._chunked_ocr(stitched)
                method = f"提取 {len(frames)} 帧，垂直拼接为 {stitched.height}px 长图后分块 OCR，并用 DeepSeek 合并去重"
            else:
                ocr_result = self._run_glm_ocr(stitched, prompt)
                method = f"提取 {len(frames)} 帧，垂直拼接为长图后一次性 OCR（via llama-server MTP）"
            return {
                "_source": "inspect_scrolling (GLM-OCR 0.9B llama.cpp server on stitched long image)",
                "_time_range": f"[{self._fmt(s)}-{self._fmt(e)}]",
                "_method": method,
                "ocr_result": ocr_result[:4000],
            }

        if name == "search_similar_clips":
            if not self._ensure_clip_embeds():
                return {"_source": "search_similar_clips", "error": "片段 embedding 未就绪"}
            qe = embed_texts([args["query"]])[0]
            scored = [(i, cosine_similarity(qe, self._clip_embeds[i])) for i in range(len(self.db["clips"]))]
            scored.sort(key=lambda x: x[1], reverse=True)
            top_k = args.get("top_k", 5)
            return {
                "_source": "search_similar_clips (基于片段 caption 描述的 embedding 搜索)",
                "results": [{"time": f"{self._fmt(self.db['clips'][i]['start'])}-{self._fmt(self.db['clips'][i]['end'])}", "similarity": round(sim, 3), "caption": self.db["clips"][i]["caption"]} for i, sim in scored[:top_k]],
            }

        if name == "detect_chapters":
            return self._detect_chapters(args.get("min_chapter_secs", 120))

        if name == "get_extracted_content":
            return self._get_extracted_content(args["start_seconds"], args["end_seconds"])

        if name == "summarize_chapter":
            return self._summarize_chapter(
                args["start_seconds"], args["end_seconds"], args.get("chapter_title", "")
            )

        if name == "read_summary":
            summary_path = self._find_summary_path()
            if not summary_path:
                return {"_source": "read_summary", "error": "未找到 /tmp 下的 summary markdown 文件"}
            text = self._load_summary_text()
            chapter = args.get("chapter")
            if not chapter:
                headings = [f"## {s['title']}" for s in self._summary_sections(text)]
                return {
                    "_source": "read_summary",
                    "summary_path": summary_path,
                    "toc": "\n".join(headings),
                }
            section = self._find_summary_section(text, chapter)
            if not section:
                return {
                    "_source": "read_summary",
                    "summary_path": summary_path,
                    "error": f"未找到匹配章节：{chapter}",
                }
            return {
                "_source": "read_summary",
                "summary_path": summary_path,
                "chapter": section["title"],
                "content": section["content"].strip(),
            }

        if name == "update_summary":
            summary_path = self._find_summary_path()
            if not summary_path:
                return {"_source": "update_summary", "error": "未找到 /tmp 下的 summary markdown 文件"}
            text = self._load_summary_text()
            chapter = args["chapter"]
            old_text = args["old_text"]
            new_text = args["new_text"]
            section = self._find_summary_section(text, chapter)
            if not section:
                return {
                    "_source": "update_summary",
                    "summary_path": summary_path,
                    "error": f"未找到匹配章节：{chapter}",
                }
            excerpt = old_text[:50]
            if not excerpt or excerpt not in section["content"]:
                return {
                    "_source": "update_summary",
                    "summary_path": summary_path,
                    "chapter": section["title"],
                    "error": "old_text 的前 50 个字符未出现在该章节中，拒绝修改",
                }
            if old_text not in section["content"]:
                return {
                    "_source": "update_summary",
                    "summary_path": summary_path,
                    "chapter": section["title"],
                    "error": "old_text 前缀已匹配，但完整 old_text 未在该章节中精确出现，拒绝修改",
                }
            updated_section = section["content"].replace(old_text, new_text, 1)
            updated = text[:section["start"]] + updated_section + text[section["end"]:]
            Path(summary_path).write_text(updated, encoding="utf-8")
            self._summary_text = None
            return {
                "_source": "update_summary",
                "summary_path": summary_path,
                "chapter": section["title"],
                "status": "updated",
                "diff_preview": {
                    "old": old_text[:200],
                    "new": new_text[:200],
                },
            }

        if name == "inspect_slide":
            slide_path = args["slide_path"]
            if not Path(slide_path).exists():
                return f"无法找到幻灯片图片：{slide_path}"
            img = PILImage.open(slide_path)
            question = args["question"]
            q_lower = question.lower()
            if any(kw.lower() in q_lower for kw in ["识别", "文字", "text", "OCR", "读取"]):
                return self._run_glm_ocr(img, "Text Recognition:")
            return self._run_glm_ocr(img, question)

        if name == "identify_image":
            s, e = args["start_seconds"], args["end_seconds"]
            n_frames = args.get("frames", 1)
            if n_frames <= 1:
                frame = self._extract_mid_frame(s, e)
                if frame is None:
                    return f"无法提取 [{self._fmt(s)}-{self._fmt(e)}] 的中间帧"
                image_b64 = _pil_to_base64(frame)
                return call_step_with_images(args["question"], [image_b64])
            else:
                n_frames = min(n_frames, 8)
                extracted = self._extract_dense_frames(s, e, n_frames=n_frames)
                if not extracted:
                    return f"无法提取 [{self._fmt(s)}-{self._fmt(e)}] 的帧"
                images_b64 = [_pil_to_base64(f) for f in extracted]
                return call_step_with_images(args["question"], images_b64)

        if name == "ask_world_knowledge":
            from external_api import call_knowledge_llm
            answer = call_knowledge_llm(args["question"])
            return {
                "_source": "ask_world_knowledge",
                "_description": f"查询外部世界知识：{args['question'][:50]}",
                "answer": answer or "外部模型未返回有效回答。",
            }

        return {"error": f"unknown tool: {name}"}

    def _ask_legacy(self, question, max_rounds=2):
        ctx_text, top_clips = self._build_context(question)
        prompt = (
            "你是视频分析助手。以下是来自不同来源的视频相关信息，可靠性从高到低："
            "transcript(原始字幕，最可靠) > visual_caption(AI视觉描述) > keyword_match(关键词匹配)。\n\n"
            f"{ctx_text}\n\n"
            f"问题：{question}\n\n请用{self._lang}详细回答，引用具体时间戳。优先使用transcript中的信息。信息不足请说明。"
        )
        remote = self._remote_ask(prompt[:15000], max_tokens=512)
        if remote and len(remote) > 30:
            answer = remote
        else:
            local = self._local_ask(prompt[:15000], 512)
            answer = local if local and len(local) > 30 else "信息不足，无法回答。"

        if top_clips:
            if self._has_temporal_intent(question):
                visual_evidence, temporal_range = self._temporal_inspect(question, top_clips)
            else:
                visual_evidence, temporal_range = self._topk_inspect(question, top_clips), None

            if visual_evidence:
                if temporal_range:
                    s_start, s_end = temporal_range
                    temporal_transcript = self._transcript_in_range(s_start, s_end)
                    synthesize_prompt = (
                        "你是视频分析助手。以下是锚定时间段的原始字幕和视觉验证。\n\n"
                        f"问题：{question}\n\n"
                        f"原始字幕（最可靠，时间段 [{self._fmt(s_start)}-{self._fmt(s_end)}]）：\n{temporal_transcript}\n\n"
                        f"视觉验证（大模型 VQA 结果）：\n{visual_evidence}\n\n"
                        "请综合字幕和视觉验证，给出最终答案。\n"
                        "优先使用字幕信息。回答必须包含具体命令文本或操作名称，引用时间戳。"
                    )
                else:
                    ranked_evidence = self._rank_evidence(question, visual_evidence)
                    synthesize_prompt = (
                        "你是视频分析助手。以下是与问题最相关的视觉验证结果。\n\n"
                        f"问题：{question}\n\n"
                        f"视觉验证：\n{ranked_evidence}\n\n"
                        "请给出最终答案。必须包含具体命令文本或操作名称，引用时间戳。"
                    )
                synthesized = self._remote_ask(synthesize_prompt[:15000], max_tokens=1024)
                if synthesized and len(synthesized) > 30:
                    answer = synthesized
                answer += f"\n\n---\n详细视觉验证：\n{visual_evidence}"

        for round_i in range(max_rounds):
            need_more, new_clips = self._self_check(question, answer)
            if not need_more:
                break
            print(f"  [react] round {round_i+1}: expanding to clips {[(self._fmt(c['start']), self._fmt(c['end'])) for c in new_clips]}")
            new_clips_sorted = sorted(new_clips, key=lambda c: c["start"])
            all_react_vis = []
            react_clip_info = []
            for c in new_clips_sorted:
                cs, ce = c["start"], c["end"]
                ci = self._find_clip_idx(cs)
                if ci is None:
                    continue
                vis = self._load_dense_tokens(ci)
                if vis is None:
                    vis = self._frames_to_visual_for_clip(ci)
                if vis is not None:
                    all_react_vis.append(vis)
                    react_clip_info.append((cs, ce))
                    print(f"  [react_collect] [{self._fmt(cs)}-{self._fmt(ce)}] {vis.shape[0]} tokens")

            new_evidence = ""
            if all_react_vis:
                combined_vis = np.concatenate(all_react_vis, axis=0)
                total_tokens = combined_vis.shape[0]
                clips_desc = ", ".join(f"[{self._fmt(cs)}-{self._fmt(ce)}]" for cs, ce in react_clip_info)
                first_start = react_clip_info[0][0]
                last_end = react_clip_info[-1][1]
                temporal_transcript = self._transcript_in_range(first_start, last_end)
                vqa_prompt = (
                    f"以下是 [{self._fmt(first_start)}-{self._fmt(last_end)}] 时间段的连续视频帧。\n"
                    f"时间段：{clips_desc}\n"
                    f"共 {len(react_clip_info)} 个片段，{total_tokens} 个视觉标记。\n\n"
                    f"该时间段字幕：\n{temporal_transcript}\n\n"
                    f"问题：{question}\n\n"
                    "请根据连续画面和字幕回答问题。\n"
                    "要求：\n"
                    "1. 优先使用字幕信息，字幕最可靠\n"
                    "2. 只回答你从画面/字幕中直接看到的事实，不要推测\n"
                    "3. 如果画面中有命令行，抄写终端里输入或显示的命令文本\n"
                    "4. 不要把网页按钮当作命令行命令\n"
                    "5. 引用具体时间戳"
                )
                react_answer = self._visual_ask(vqa_prompt, combined_vis, N_PREDICT)
                new_evidence = (
                    f"\n<react_verification type=\"merged\" "
                    f"time=\"{self._fmt(first_start)}-{self._fmt(last_end)}\" "
                    f"clips=\"{len(react_clip_info)}\" tokens=\"{total_tokens}\">\n"
                    f"{react_answer}\n</react_verification>\n"
                )

            if new_evidence:
                react_prompt = (
                    "你是视频分析助手。以下是之前的回答和补充的视觉验证。\n\n"
                    f"原始问题：{question}\n\n"
                    f"之前的回答：\n{answer[:4000]}\n\n"
                    f"补充视觉验证：\n{new_evidence}\n\n"
                    "请根据所有信息重新给出更准确、更完整的回答。"
                    "引用具体时间戳。如果之前回答有误，请纠正。" f"用{self._lang}回答。"
                )
                new_answer = self._remote_ask(react_prompt[:15000], max_tokens=1024)
                if new_answer and len(new_answer) > 30:
                    answer = new_answer
                    answer += f"\n\n---\n补充视觉验证：\n{new_evidence}"

        return answer

    def _topk_inspect(self, question, top_clips):
        all_vis = []
        clip_info = []
        seen_starts = set()
        for rank, (idx, sim) in enumerate(top_clips[:3]):
            clip = self.db["clips"][idx]
            s, e = clip["start"], clip["end"]
            if any(abs(s - ss) < 10 for ss in seen_starts):
                continue
            seen_starts.add(s)

            vis = self._load_dense_tokens(idx)
            if vis is not None:
                print(f"  [topk_inspect] top-{rank+1} [{self._fmt(s)}] sim={sim:.3f} (cached tokens)")
            else:
                print(f"  [topk_inspect] top-{rank+1} [{self._fmt(s)}] sim={sim:.3f} (computing...)")
                vis = self._frames_to_visual_for_clip(idx)

            if vis is not None:
                all_vis.append(vis)
                clip_info.append((rank + 1, s, e, sim))

        if not all_vis:
            return ""

        combined_vis = np.concatenate(all_vis, axis=0)
        total_tokens = combined_vis.shape[0]
        clips_desc = ", ".join(f"[{self._fmt(s)}-{self._fmt(e)}]" for _, s, e, _ in clip_info)

        vqa_prompt = (
            f"以下是来自 {len(clip_info)} 个时间段的视频画面（共 {total_tokens} 个视觉标记）。\n"
            f"时间段：{clips_desc}\n\n"
            f"问题：{question}\n\n"
            "请根据所有画面综合回答问题。\n"
            "要求：\n"
            "1. 只回答你从画面中直接看到的事实，不要推测\n"
            "2. 如果画面中有命令行，抄写终端里的命令文本\n"
            "3. 不要把网页按钮当作命令行命令\n"
            "4. 引用具体时间戳"
        )

        answer = self._visual_ask(vqa_prompt, combined_vis, N_PREDICT)
        clips_detail = "; ".join(f"top-{rank} [{self._fmt(s)}-{self._fmt(e)}] sim={sim:.3f}" for rank, s, e, sim in clip_info)
        evidence = f"\n<visual_verification type=\"combined_topk\" clips=\"{clips_detail}\" total_tokens=\"{total_tokens}\">\n{answer}\n</visual_verification>\n"
        return evidence

    def _temporal_inspect(self, question, top_clips):
        idx, sim = top_clips[0]
        clip = self.db["clips"][idx]
        anchor = clip["start"]
        fwd, bwd = self._temporal_direction(question)
        print(f"  [temporal_inspect] anchor=[{self._fmt(anchor)}] sim={sim:.3f}, fwd={fwd} bwd={bwd}")

        clip_indices = []
        first_start, last_end = anchor, clip["end"]

        if bwd:
            for offset in range(1, 9):
                ci = idx - offset
                if ci < 0:
                    break
                clip_indices.append(ci)
                first_start = self.db["clips"][ci]["start"]
            clip_indices.reverse()

        clip_indices.append(idx)

        if fwd:
            for offset in range(1, 9):
                ci = idx + offset
                if ci >= len(self.db["clips"]):
                    break
                clip_indices.append(ci)
                last_end = self.db["clips"][ci]["end"]

        all_vis = []
        for ci in clip_indices:
            vis = self._load_dense_tokens(ci)
            c = self.db["clips"][ci]
            if vis is not None:
                all_vis.append(vis)
                print(f"  [collect] [{self._fmt(c['start'])}-{self._fmt(c['end'])}] cached {vis.shape[0]} tokens")
            else:
                vis = self._frames_to_visual_for_clip(ci)
                if vis is not None:
                    all_vis.append(vis)
                    print(f"  [collect] [{self._fmt(c['start'])}-{self._fmt(c['end'])}] computed {vis.shape[0]} tokens")

        if not all_vis:
            return "", (first_start, last_end)

        combined_vis = np.concatenate(all_vis, axis=0)
        total_tokens = combined_vis.shape[0]
        print(f"  [temporal_inspect] combined {len(all_vis)} clips → {total_tokens} tokens, single 8B VQA")

        temporal_transcript = self._transcript_in_range(first_start, last_end)
        vqa_prompt = (
            f"以下是 [{self._fmt(first_start)}-{self._fmt(last_end)}] 时间段的连续视频帧和对应字幕。\n\n"
            f"共 {len(all_vis)} 个片段，{total_tokens} 个视觉标记。\n\n"
            f"问题：{question}\n\n"
            f"该时间段字幕：\n{temporal_transcript}\n\n"
            "请根据连续画面和字幕回答问题。\n"
            "要求：\n"
            "1. 优先使用字幕信息，字幕最可靠\n"
            "2. 只回答你从画面/字幕中直接看到的事实，不要推测\n"
            "3. 如果画面中有命令行，抄写终端里输入或显示的命令文本\n"
            "4. 不要把网页按钮当作命令行命令\n"
            "5. 引用具体时间戳"
        )
        answer = self._visual_ask(vqa_prompt, combined_vis, 512)
        evidence = f"\n<visual_verification type=\"merged\" time=\"{self._fmt(first_start)}-{self._fmt(last_end)}\" clips=\"{len(all_vis)}\" tokens=\"{total_tokens}\">\n{answer}\n</visual_verification>\n"
        return evidence, (first_start, last_end)

    def _transcript_in_range(self, start_sec, end_sec):
        lines = []
        for e in self.srt:
            if e["end"] <= start_sec:
                continue
            if e["start"] >= end_sec:
                break
            lines.append(f"[{self._fmt(e['start'])}] {e['text']}")
        return "\n".join(lines)

    def _rank_evidence(self, question, evidence):
        import re
        blocks = re.split(r'<visual_verification[^>]*>', evidence)
        blocks = [b.strip() for b in blocks if b.strip() and '</visual_verification>' in b]
        blocks = [b.replace('</visual_verification>', '').strip() for b in blocks]
        if not blocks or not self._clip_embeds:
            return evidence
        qe = embed_texts([question])[0]
        scored = [(i, cosine_similarity(qe, embed_texts([b[:512]])[0])) for i, b in enumerate(blocks)]
        scored.sort(key=lambda x: x[1], reverse=True)
        tags = re.findall(r'(<visual_verification[^>]*>)', evidence)
        top_parts = []
        for i, sim in scored[:4]:
            if i < len(tags):
                top_parts.append(f"{tags[i]}\n{blocks[i]}\n</visual_verification>")
        return "\n".join(top_parts) if top_parts else evidence

    def _self_check(self, question, answer):
        """Ask the model to judge if the answer is sufficient.
        Returns (need_more: bool, new_clips_to_inspect: list[dict]).
        """
        check_prompt = (
            "你是一个严格的回答质量检查员。请判断以下回答是否充分、准确地回答了问题。\n\n"
            f"问题：{question}\n\n"
            f"回答：{answer[:3000]}\n\n"
            "请特别检查：\n"
            "1. 回答是否包含问题所要求的具体事实（命令文本、名称、数值等），而不是笼统的描述\n"
            "2. 回答是否有明确的时间戳和来源支撑\n"
            "3. 是否有可能遗漏了更准确的信息（例如只给出了概括性描述但没有具体文本）\n\n"
            "请按以下格式回答（不要输出其他内容）：\n"
            "判断：充分/不充分\n"
            "原因：简要说明缺少什么具体信息\n"
            "建议关键词：如果需要补充检索，给出2-3个搜索关键词，用逗号分隔\n"
            "建议时间范围：如果需要查看特定时间段的画面，给出起止秒数（如 420-480），否则写 无"
        )
        check_result = self._remote_ask(check_prompt[:8000], max_tokens=300)
        if not check_result or "不充分" not in check_result:
            return False, []

        new_clips = []
        time_range = self._parse_time_range(check_result)
        if time_range:
            s, e = time_range
            for c in self.db["clips"]:
                if c["start"] >= s and c["end"] <= e:
                    new_clips.append(c)
            if not new_clips:
                mid = (s + e) / 2
                nearest = min(self.db["clips"], key=lambda c: abs(c["start"] - mid))
                idx = nearest["idx"]
                for off in range(-1, 3):
                    ci = idx + off
                    if 0 <= ci < len(self.db["clips"]):
                        new_clips.append(self.db["clips"][ci])

        if not new_clips:
            keywords = self._parse_suggested_keywords(check_result)
            if keywords:
                for kw in keywords:
                    kw_clips = self._search_captions_kw(kw, top_k=3)
                    if kw_clips:
                        import re
                        for line in kw_clips.split("\n")[:2]:
                            m = re.match(r'\[(\d+:\d+)\]', line)
                            if m:
                                t = m.group(1)
                                secs = int(t.split(":")[0]) * 60 + int(t.split(":")[1])
                                for c in self.db["clips"]:
                                    if abs(c["start"] - secs) < 5 and c not in new_clips:
                                        new_clips.append(c)

        if new_clips and self._clip_embeds is not None:
            already_times = set()
            import re
            for m in re.finditer(r'time="(\d+:\d+)-(\d+:\d+)"', answer):
                t = m.group(1)
                already_times.add(int(t.split(":")[0]) * 60 + int(t.split(":")[1]))
            new_clips = [c for c in new_clips if not any(abs(c["start"] - t) < 10 for t in already_times)]

        return len(new_clips) > 0, new_clips[:3]

    def _parse_time_range(self, text):
        """Parse '建议时间范围：420-480' from self-check result."""
        import re
        m = re.search(r'建议时间范围[：:]\s*(\d+)\s*[-–]\s*(\d+)', text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None

    def _parse_suggested_keywords(self, text):
        """Parse '建议关键词：kw1, kw2, kw3' from self-check result."""
        import re
        m = re.search(r'建议关键词[：:]\s*(.+)', text)
        if m:
            return [kw.strip() for kw in m.group(1).split(",") if kw.strip()]
        return []

    def external_knowledge(self, question):
        transcript_hits = search_transcript(self.srt, question, top_k=5)
        ctx = "\n".join(
            f"[{self._fmt(e['start'])}] {e['text']}" for e in transcript_hits
        )
        prompt = (
            f"你是视频分析助手，需要借助外部知识回答一个超出视频内容范围的问题。\n\n"
            f"== 视频中相关上下文 ==\n{ctx[:3000]}\n\n"
            f"== 需要外部知识的问题 ==\n{question}\n\n请结合外部知识回答，用{self._lang}。"
        )
        return self._external_ask(prompt)

    def _extract_frames(self, start_sec, end_sec):
        from video_db import _extract_clip_frames
        return _extract_clip_frames(self._video_path, start_sec, end_sec)

    def _frames_to_visual(self, frames):
        if not frames:
            return None
        self._ensure_models()
        from video_db import _preprocess_frames
        from config import NPPS, EMBED_DIM, MAX_SLICE_NUMS
        from preprocess import (
            get_2d_sincos_pos_embed_numpy, encode_video_temporal_ids,
            compute_temporal_embeddings_for_group,
        )
        from video_db import _get_video_fps, _compute_onnx_inputs_v45

        tiles, meta = _preprocess_frames(frames, max_slice_nums=MAX_SLICE_NUMS)
        vid_fps = _get_video_fps(self._video_path)

        siglip_features, patch_counts = [], []
        for tile in tiles:
            h, w = tile["h"], tile["w"]
            inputs = _compute_onnx_inputs_v45(h, w, NPPS)
            pv = tile["pixel_values"].astype(np.float32)
            feat = self._siglip.run(["siglip_features"], {"pixel_values": pv, "pos_ids": inputs["pos_ids"]})[0]
            siglip_features.append(feat)
            patch_counts.append(h * w)

        total = len(frames)
        tids = encode_video_temporal_ids(np.linspace(0, total - 1, total, dtype=int), vid_fps)

        gf = np.concatenate(siglip_features, axis=0)
        sp = np.concatenate([get_2d_sincos_pos_embed_numpy(EMBED_DIM, (tiles[i]["h"], tiles[i]["w"])).reshape(tiles[i]["h"] * tiles[i]["w"], -1) for i in range(len(tiles))], axis=0)
        te = compute_temporal_embeddings_for_group(patch_counts, tids, EMBED_DIM)
        vt = self._resampler.run(None, {
            "siglip_features": gf.astype(np.float16),
            "spatial_pos_embeds": sp.astype(np.float16),
            "temporal_pos_embeds": te.astype(np.float16),
        })[0]
        return vt.astype(np.float32)

    def _frames_to_visual_for_clip(self, clip_idx):
        self._ensure_models()
        c = self.db["clips"][clip_idx]
        frames = self._extract_frames(c["start"], c["end"])
        if not frames:
            return None
        return self._frames_to_visual(frames)

    def frame_inspect(self, question, start_sec, end_sec):
        self._ensure_models()

        clip_idx = self._find_clip_idx(start_sec)
        if clip_idx is not None:
            clip = self.db["clips"][clip_idx]
            vis = self._load_dense_tokens(clip_idx)
            if vis is not None and end_sec <= clip["end"] + 0.5:
                print(f"  [frame_inspect] using cached tokens ({vis.shape[0]} tokens)")
                from srt_utils import transcript_for_timerange
                transcript = transcript_for_timerange(self.srt, start_sec, end_sec)
                transcript_hint = f"\n该时间段字幕:\n{transcript}" if transcript else ""
                vqa_prompt = (
                    f"请仔细观察这段视频画面，回答问题。\n"
                    f"问题：{question}\n\n"
                    "要求：\n"
                    "1. 只回答你从画面中直接看到的事实，不要推测或编造\n"
                    "2. 如果画面中有命令行/终端窗口，只抄写终端里输入或显示的命令文本\n"
                    "3. 不要把网页界面上的按钮（如'登录'、'提交'）当作命令行命令\n"
                    "4. 如果画面中有菜单选项，列出编号和对应功能\n"
                    "5. 如果画面无法回答该问题，直接说'画面无法回答该问题'\n"
                    f"{transcript_hint}"
                )
                return self._visual_ask(vqa_prompt, vis, N_PREDICT)

        if not self._siglip or not self._resampler:
            return None
        from video_db import _extract_clip_frames, _preprocess_frames
        from config import NPPS, EMBED_DIM, MAX_SLICE_NUMS
        from preprocess import (
            get_2d_sincos_pos_embed_numpy, encode_video_temporal_ids,
            compute_temporal_embeddings_for_group,
        )
        from video_db import _get_video_fps, _compute_onnx_inputs_v45

        frames = _extract_clip_frames(self._video_path, start_sec, end_sec)
        if not frames:
            return None

        tiles, meta = _preprocess_frames(frames, max_slice_nums=MAX_SLICE_NUMS)
        vid_fps = _get_video_fps(self._video_path)

        siglip_features, patch_counts = [], []
        for tile in tiles:
            h, w = tile["h"], tile["w"]
            inputs = _compute_onnx_inputs_v45(h, w, NPPS)
            pv = tile["pixel_values"].astype(np.float32)
            feat = self._siglip.run(["siglip_features"], {"pixel_values": pv, "pos_ids": inputs["pos_ids"]})[0]
            siglip_features.append(feat)
            patch_counts.append(h * w)

        total = len(frames)
        tids = encode_video_temporal_ids(np.linspace(0, total - 1, total, dtype=int), vid_fps)

        gf = np.concatenate(siglip_features, axis=0)
        sp = np.concatenate([get_2d_sincos_pos_embed_numpy(EMBED_DIM, (tiles[i]["h"], tiles[i]["w"])).reshape(tiles[i]["h"] * tiles[i]["w"], -1) for i in range(len(tiles))], axis=0)
        te = compute_temporal_embeddings_for_group(patch_counts, tids, EMBED_DIM)
        vt = self._resampler.run(None, {
            "siglip_features": gf.astype(np.float16),
            "spatial_pos_embeds": sp.astype(np.float16),
            "temporal_pos_embeds": te.astype(np.float16),
        })[0]
        vis = vt.astype(np.float32)

        from srt_utils import transcript_for_timerange
        transcript = transcript_for_timerange(self.srt, start_sec, end_sec)
        transcript_hint = f"\n该时间段字幕:\n{transcript}" if transcript else ""
        vqa_prompt = (
            f"请仔细观察这段视频画面，回答问题。\n"
            f"问题：{question}\n\n"
            "要求：\n"
            "1. 只回答你从画面中直接看到的事实，不要推测或编造\n"
            "2. 如果画面中有命令行/终端窗口，只抄写终端里输入或显示的命令文本\n"
            "3. 不要把网页界面上的按钮（如'登录'、'提交'）当作命令行命令\n"
            "4. 如果画面中有菜单选项，列出编号和对应功能\n"
            "5. 如果画面无法回答该问题，直接说'画面无法回答该问题'\n"
            f"{transcript_hint}"
        )

        return self._visual_ask(vqa_prompt, vis, N_PREDICT)

    def _visual_ask(self, prompt, vis, n_predict):
        import math
        import minicpmv_llama
        if vis is None or getattr(vis, "shape", (0,))[0] <= 0:
            return "视觉 token 为空，无法进行本地视觉问答。"

        if not isinstance(vis, np.ndarray):
            vis = np.asarray(vis, dtype=np.float32)
        if vis.dtype != np.float32 or not vis.flags["C_CONTIGUOUS"]:
            vis = np.ascontiguousarray(vis.astype(np.float32, copy=False))

        _pad_id = self._model.tokenize("<|image_pad|>", parse_special=True)[0]
        tile_tokens = 64
        n_tiles_total = vis.shape[0] // tile_tokens
        if n_tiles_total <= 0:
            return "视觉 token 数量不足，无法进行本地视觉问答。"
        vis = vis[:n_tiles_total * tile_tokens]

        def _sample_tiles(source_vis, n_tiles):
            if n_tiles >= n_tiles_total:
                return source_vis, n_tiles_total
            tiles = source_vis.reshape(n_tiles_total, tile_tokens, source_vis.shape[1])
            idx = np.linspace(0, n_tiles_total - 1, n_tiles, dtype=int)
            sampled = tiles[idx].reshape(n_tiles * tile_tokens, source_vis.shape[1])
            return np.ascontiguousarray(sampled.astype(np.float32, copy=False)), n_tiles

        def _truncate_middle(text, max_chars):
            if len(text) <= max_chars:
                return text
            marker = "\n\n[...上下文过长，已截断以适配本地模型上下文...]\n\n"
            if max_chars <= len(marker) + 200:
                return text[:max_chars]
            head = max_chars // 2
            tail = max_chars - head - len(marker)
            return text[:head] + marker + text[-tail:]

        def _build_segments(prompt_text, n_tiles):
            tile_str = "<image>" + "<|image_pad|>" * tile_tokens + "</image>"
            slice_str = "<slice>" + "<|image_pad|>" * tile_tokens + "</slice>"
            image_str = tile_str if n_tiles == 1 else tile_str + slice_str * (n_tiles - 1)
            full_prompt = f"<|im_start|>user\n{image_str}\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"
            tokens = self._model.tokenize(full_prompt, add_special=True, parse_special=True)

            segments = []
            current_text = []
            visual_tokens = 0
            for tok in tokens:
                if tok == _pad_id:
                    visual_tokens += 1
                    if current_text:
                        segments.append(("text", current_text))
                        current_text = []
                    if segments and segments[-1][0] == "visual":
                        segments[-1] = ("visual", segments[-1][1] + 1)
                    else:
                        segments.append(("visual", 1))
                else:
                    current_text.append(tok)
            if current_text:
                segments.append(("text", current_text))
            return segments, len(tokens), visual_tokens

        requested_predict = max(1, int(n_predict or 1))
        reserved_gen = min(requested_predict, max(64, N_CTX // 4))
        input_budget = max(128, N_CTX - reserved_gen - 4)
        prompt_text = prompt
        n_tiles = n_tiles_total
        sampled_visual = False
        truncated_prompt = False

        for _ in range(12):
            segments, input_tokens, visual_tokens = _build_segments(prompt_text, n_tiles)
            if input_tokens <= input_budget:
                break
            overflow = input_tokens - input_budget
            if n_tiles > 1 and visual_tokens > tile_tokens:
                remove_tiles = max(1, math.ceil(overflow / tile_tokens))
                new_tiles = max(1, n_tiles - remove_tiles)
                if new_tiles < n_tiles:
                    n_tiles = new_tiles
                    sampled_visual = True
                    continue

            max_chars = max(300, int(len(prompt_text) * input_budget / max(input_tokens, 1) * 0.85))
            if len(prompt_text) > max_chars:
                next_prompt = _truncate_middle(prompt_text, max_chars)
                if next_prompt != prompt_text:
                    prompt_text = next_prompt
                    truncated_prompt = True
                    continue
            break

        segments, input_tokens, visual_tokens = _build_segments(prompt_text, n_tiles)
        if input_tokens >= N_CTX:
            return (
                f"本地视觉模型上下文不足：输入 {input_tokens} tokens >= N_CTX {N_CTX}。"
                "请缩短时间范围后重试。"
            )

        vis, n_tiles = _sample_tiles(vis, n_tiles)
        if visual_tokens != vis.shape[0]:
            usable = min(visual_tokens, vis.shape[0])
            usable -= usable % tile_tokens
            if usable <= 0:
                return "视觉 token 与 prompt 占位符不匹配，无法进行本地视觉问答。"
            vis = vis[:usable]
            n_tiles = usable // tile_tokens
            segments, input_tokens, visual_tokens = _build_segments(prompt_text, n_tiles)

        n_predict = min(requested_predict, max(1, N_CTX - input_tokens))
        batch_limit = max(1, min(int(N_BATCH or 512), N_CTX))
        if sampled_visual:
            print(f"  [visual_ask] sampled visual tiles {n_tiles}/{n_tiles_total} to fit N_CTX={N_CTX}")
        if truncated_prompt:
            print(f"  [visual_ask] truncated prompt to fit N_CTX={N_CTX}")

        def _check_decode(ret, stage):
            if ret not in (0, None):
                raise RuntimeError(f"llama decode failed during {stage}: {ret}")

        self._ctx.clear_kv()
        pos, vis_idx = 0, 0
        for stype, sdata in segments:
            if stype == "text":
                for off in range(0, len(sdata), batch_limit):
                    chunk = sdata[off:off + batch_limit]
                    if pos + len(chunk) > N_CTX:
                        return f"本地视觉模型上下文不足：prefill pos={pos}, chunk={len(chunk)}, N_CTX={N_CTX}"
                    batch = minicpmv_llama.LlamaBatch(len(chunk), embd_dim=0)
                    batch.set_tokens(chunk, pos_offset=pos)
                    _check_decode(self._ctx.decode(batch), "text prefill")
                    pos += len(chunk)
            else:
                n = sdata
                for off in range(0, n, batch_limit):
                    chunk_n = min(batch_limit, n - off)
                    if pos + chunk_n > N_CTX:
                        return f"本地视觉模型上下文不足：visual pos={pos}, chunk={chunk_n}, N_CTX={N_CTX}"
                    chunk = vis[vis_idx + off:vis_idx + off + chunk_n]
                    batch = minicpmv_llama.LlamaBatch(chunk_n, embd_dim=self._model.n_embd)
                    batch.set_embd(chunk, pos_offset=pos)
                    _check_decode(self._ctx.decode(batch), "visual prefill")
                    pos += chunk_n
                vis_idx += n

        raw = bytearray()
        for _ in range(n_predict):
            if pos >= N_CTX:
                break
            tok = self._sampler.sample(self._ctx)
            self._sampler.accept(tok)
            if tok == self._model.eos_token:
                break
            raw.extend(self._model.detokenize(tok))
            _check_decode(self._ctx.decode_token(tok, pos=pos), "token decode")
            pos += 1
        return raw.decode("utf-8", errors="replace").strip()

    def _build_context(self, question):
        parts = []

        transcript_hits = self._search_transcript_embed(question, top_k=10)
        if not transcript_hits:
            transcript_hits = search_transcript(self.srt, question, top_k=10)
        if transcript_hits:
            lines = [f"[{self._fmt(e['start'])}] {e['text']}" for e in transcript_hits]
            parts.append(f"<source type=\"transcript\" reliability=\"high\">\n" + "\n".join(lines) + "\n</source>")

        embed_ctx, top_clips = self._search_captions_embed(question, top_k=15)
        if embed_ctx:
            parts.append(f"<source type=\"visual_caption\" reliability=\"medium\">\n{embed_ctx}\n</source>")

        kw_ctx = self._search_captions_kw(question, top_k=10)
        if kw_ctx:
            parts.append(f"<source type=\"keyword_match\" reliability=\"low\">\n{kw_ctx}\n</source>")

        combined = "\n\n".join(parts)
        return combined, top_clips

    def _search_transcript_embed(self, query, top_k=10):
        if self._srt_embeds is None:
            texts = [e["text"] for e in self.srt]
            print(f"  计算 {len(texts)} 条字幕的 embedding...")
            self._srt_embeds = embed_texts(texts)
            print("  字幕 embedding 完成.")
        qe = embed_texts([query])[0]
        scored = [(i, cosine_similarity(qe, self._srt_embeds[i])) for i in range(len(self.srt))]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [{**self.srt[i], "score": round(sim, 3)} for i, sim in scored[:top_k]]

    def _search_captions_embed(self, query, top_k=10):
        if not self._ensure_clip_embeds():
            return "", []
        qe = embed_texts([query])[0]
        scored = [(i, cosine_similarity(qe, self._clip_embeds[i]))
                  for i in range(len(self.db["clips"]))]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_k]
        deduped = []
        for idx, sim in top:
            duped = False
            for kept_idx, _ in deduped:
                if cosine_similarity(self._clip_embeds[idx], self._clip_embeds[kept_idx]) > 0.9:
                    duped = True
                    break
            if not duped:
                deduped.append((idx, sim))
        lines = []
        for idx, sim in deduped[:8]:
            c = self.db["clips"][idx]
            lines.append(f"[{self._fmt(c['start'])}-{self._fmt(c['end'])} sim={sim:.3f}] {c['caption']}")
        return "\n".join(lines), scored[:top_k]

    def _search_captions_kw(self, query, top_k=10):
        is_cn = any('\u4e00' <= c <= '\u9fff' for c in query)
        kw = list(set(query[i:i+2] for i in range(len(query)-1))) if is_cn else query.lower().split()
        scored = []
        for c in self.db["clips"]:
            cl = c["caption"].lower()
            s = sum(cl.count(k) for k in kw)
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return "\n".join(
            f"[{self._fmt(c['start'])}] {c['caption']}" for _, c in scored[:top_k]
        )
