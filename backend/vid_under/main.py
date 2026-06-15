# coding=utf-8
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    VIDEO_PATH, SRT_PATH, DB_DIR, GGUF_PATH, EXPORT_DIR,
    N_CTX, N_GPU_LAYERS, N_BATCH, N_PREDICT, KV_CACHE_TYPE, ONNX_PROVIDER,
)
from srt_utils import parse_srt
from agent import VideoAgent


def _load_models():
    import external_api as _ext
    if hasattr(_ext, "shutdown_glm_ocr_workers"):
        _ext.shutdown_glm_ocr_workers(stop_decoder=True)
    else:
        engine = getattr(_ext, "_glm_ocr_engine", None)
        if engine is not None:
            if hasattr(engine, "close"):
                engine.close()
            _ext._glm_ocr_engine = None
            import gc
            gc.collect()

    import minicpmv_llama
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if ONNX_PROVIDER == "cpu":
        providers = ["CPUExecutionProvider"]
    else:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    model = minicpmv_llama.LlamaModel(str(GGUF_PATH), n_gpu_layers=N_GPU_LAYERS)
    kv_type = {"q4_0": 2, "q8_0": 8, "fp16": 1}.get(KV_CACHE_TYPE, 0)
    ctx = minicpmv_llama.LlamaContext(model, n_ctx=N_CTX, n_batch=N_BATCH, n_ubatch=N_BATCH, cache_type_k=kv_type, cache_type_v=kv_type)
    sampler = minicpmv_llama.LlamaSampler(temperature=0, repeat_penalty=1.1)

    siglip = ort.InferenceSession(str(Path(EXPORT_DIR) / "minicpmv_v45_siglip.fp32.onnx"), sess_options=opts, providers=providers)
    resampler = ort.InferenceSession(str(Path(EXPORT_DIR) / "minicpmv_v45_resampler_temporal.fp16.onnx"), sess_options=opts, providers=providers)

    return model, ctx, sampler, siglip, resampler


def _db_name():
    return Path(VIDEO_PATH).stem

def _load_db():
    db_path = DB_DIR / f"{_db_name()}.json"
    if not db_path.exists():
        print(f"请先运行 build (expected {db_path})")
        sys.exit(1)
    db = json.loads(db_path.read_text(encoding="utf-8"))
    srt = parse_srt(db["srt_path"])
    return db, srt


def cmd_build(clip_secs=None, video_fps=None, frames_per_clip=None):
    import time
    from config import THINKING_BUDGET_FRAMES
    from video_db import build_database
    t0 = time.time()
    db_name = _db_name()

    if isinstance(frames_per_clip, str) and frames_per_clip in THINKING_BUDGET_FRAMES:
        frames_per_clip = THINKING_BUDGET_FRAMES[frames_per_clip]

    print(f"构建视频数据库...\n  Video: {VIDEO_PATH}\n  SRT:   {SRT_PATH}\n  DB:    {db_name}")
    if clip_secs:
        print(f"  clip_secs: {clip_secs}")
    if video_fps:
        print(f"  video_fps: {video_fps}")
    if frames_per_clip:
        print(f"  frames_per_clip: {frames_per_clip}")
    build_database(VIDEO_PATH, SRT_PATH, db_name=db_name,
                   clip_secs=clip_secs, video_fps=video_fps,
                   frames_per_clip=frames_per_clip)
    elapsed = time.time() - t0
    print(f"完成。耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")


def cmd_summarize(thinking_budget="low", top_n=20, output_path=None, min_coverage=0.60):
    import time
    t0 = time.time()
    db, srt = _load_db()
    agent = VideoAgent(db, srt)
    answer = agent.summarize(thinking_budget=thinking_budget, top_n=top_n, min_coverage=min_coverage)
    elapsed = time.time() - t0
    if output_path:
        from pathlib import Path
        Path(output_path).write_text(answer, encoding="utf-8")
        print(f"已保存到 {output_path}")
    else:
        print(answer)
    print(f"\n耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")


def cmd_ask(questions=None):
    db, srt = _load_db()
    model, ctx, sampler, siglip, resampler = _load_models()
    agent = VideoAgent(db, srt, model=model, ctx=ctx, sampler=sampler,
                       siglip_sess=siglip, resampler_sess=resampler)

    if questions:
        for q in questions:
            print(f"\n查询: {q}")
            answer = agent.ask(q)
            print(f"\n{'='*60}\n{answer}\n{'='*60}")
        return

    print("多轮对话模式 (输入 exit/quit 退出, reset 重置上下文)")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            break
        if question.lower() == "reset":
            agent.reset_conversation()
            print("  上下文已重置")
            continue

        answer = agent.ask(question)
        print(f"\n{'='*60}\n{answer}\n{'='*60}")


def cmd_frame_inspect(question: str, start: float, end: float):
    db, srt = _load_db()
    model, ctx, sampler, siglip, resampler = _load_models()
    agent = VideoAgent(db, srt, model=model, ctx=ctx, sampler=sampler,
                       siglip_sess=siglip, resampler_sess=resampler)
    print(f"视觉VQA: [{start:.0f}s-{end:.0f}s] {question}")
    answer = agent.frame_inspect(question, start, end)
    print(f"\n{'='*60}\n{answer}\n{'='*60}")


def cmd_external(question: str):
    db, srt = _load_db()
    agent = VideoAgent(db, srt)
    print(f"外部知识查询: {question}")
    answer = agent.external_knowledge(question)
    print(f"\n{'='*60}\n{answer}\n{'='*60}")


def cmd_extract(video_path: str, srt_path: str | None = None,
                clip_secs: int = 10, frames_per_clip: int = 7,
                output_dir: str | None = None, perspective: bool = False,
                progress_cb=None):
    import time, av
    import numpy as np
    from video_structure import classify_scene, VideoStructure, SlideEntry, CodeSnapshot
    from layout_detector import detect_layout, crop_content, detect_ui_strips, get_vision_bbox, LayoutResult
    from content_extractor import (
        extract_unique_slides, ocr_slides, detect_code_changes, extract_code_snapshots,
    )

    video_path = str(video_path)
    name = Path(video_path).stem
    out = Path(output_dir) if output_dir else Path("output") / name
    out.mkdir(parents=True, exist_ok=True)

    print(f"提取视频内容: {video_path}")
    print(f"输出目录: {out}")
    t0 = time.time()

    # 1. Load SRT if available
    transcript = []
    if srt_path and Path(srt_path).exists():
        from srt_utils import parse_srt
        transcript = parse_srt(srt_path)
        print(f"  字幕: {len(transcript)} 条")

    # 2. Get video info
    c = av.open(video_path)
    stream = c.streams.video[0]
    time_base = float(stream.time_base)
    if stream.duration:
        duration = float(stream.duration * time_base)
    else:
        import subprocess
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
            capture_output=True, text=True,
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0.0
    n_clips = int(duration / clip_secs)
    print(f"  时长: {duration:.0f}s, {n_clips} clips ({clip_secs}s/clip)")

    # 3. Phase 1: Extract mid frame + layout per clip
    slide_clips = {}
    code_clips = {}
    terminal_clips = {}
    clip_captions = {}
    clip_mid_frames = {}
    clip_all_frames = {}
    clip_layouts = {}
    cached_vision_bbox = None

    for clip_idx in range(n_clips):
        start_sec = clip_idx * clip_secs
        end_sec = start_sec + clip_secs

        target_ts = np.linspace(start_sec + 0.3, end_sec - 0.3, frames_per_clip)
        c.seek(int(start_sec / time_base), stream=stream)
        frames, fi = [], 0
        for frame in c.decode(stream):
            pts = float(frame.pts * time_base) if frame.pts is not None else 0
            if pts > end_sec + 1:
                break
            while fi < frames_per_clip and pts >= target_ts[fi]:
                img = frame.to_image().convert("RGB")
                frames.append(img)
                fi += 1
            if fi >= frames_per_clip:
                break

        if not frames:
            continue

        if perspective and len(frames) >= 1:
            from perspective import auto_correct
            corrected = []
            for f in frames:
                result = auto_correct(f)
                corrected.append(result)
            frames = corrected

        if len(frames) >= 3:
            layout = detect_layout(frames)

            if layout.layout_type == "fullscreen" and cached_vision_bbox is not None:
                bx, by, bw, bh = cached_vision_bbox
                layout = LayoutResult("vision_crop", cached_vision_bbox, 0.80)
                content_frames = [f.crop((bx, by, bx + bw, by + bh)) for f in frames]
            elif layout.layout_type == "fullscreen":
                mid = frames[len(frames) // 2]
                bbox = get_vision_bbox(mid)
                ow, oh = mid.size
                if bbox:
                    bx, by, bw, bh = bbox
                    coverage = (bw * bh) / (ow * oh)
                    if coverage >= 0.40:
                        cached_vision_bbox = bbox
                        layout = LayoutResult("vision_crop", bbox, 0.80)
                        content_frames = [f.crop((bx, by, bx + bw, by + bh)) for f in frames]
                    else:
                        content_frames = [crop_content(f, layout) for f in frames]
                else:
                    content_frames = [crop_content(f, layout) for f in frames]
            else:
                content_frames = [crop_content(f, layout) for f in frames]
        else:
            layout = None
            content_frames = frames

        clip_layouts[clip_idx] = layout
        clip_mid_frames[clip_idx] = content_frames[len(content_frames) // 2]
        clip_all_frames[clip_idx] = content_frames
        del frames  # raw frames discarded; content_frames kept for terminal/code stitching

        if clip_idx % 50 == 0:
            m, s = divmod(int(start_sec), 60)
            lt = layout.layout_type if layout else "none"
            print(f"  [{m:02d}:{s:02d}] layout={lt} frames collected")
        if progress_cb:
            progress_cb("layout", clip_idx + 1, n_clips)

    c.close()
    print(f"  Phase 1 done: {len(clip_mid_frames)} clips")

    # Phase 2: Batch OCR (sequential)
    from external_api import call_glm_ocr
    sorted_indices = sorted(clip_mid_frames.keys())
    print(f"  Phase 2: OCR on {len(sorted_indices)} clips...")
    for ocr_i, clip_idx in enumerate(sorted_indices):
        mid_content = clip_mid_frames[clip_idx]
        caption = call_glm_ocr(mid_content, "Describe this image in one short sentence:", max_tokens=128)
        clip_captions[clip_idx] = caption

        if clip_idx % 50 == 0:
            m, s = divmod(int(clip_idx * clip_secs), 60)
            print(f"  [{m:02d}:{s:02d}] {caption[:50]}...")
        if progress_cb:
            progress_cb("ocr", ocr_i + 1, len(sorted_indices))

    # Phase 3: Classify scenes
    for clip_idx in sorted_indices:
        start_sec = clip_idx * clip_secs
        caption = clip_captions[clip_idx]
        scene = classify_scene(caption)
        layout = clip_layouts[clip_idx]

        if clip_idx % 50 == 0:
            m, s = divmod(int(start_sec), 60)
            lt = layout.layout_type if layout else "none"
            print(f"  [{m:02d}:{s:02d}] scene={scene} layout={lt}")

        mid_frame = clip_mid_frames[clip_idx]

        if scene == "slide":
            slide_clips[clip_idx] = [mid_frame]
        elif scene == "code":
            code_clips[clip_idx] = [mid_frame]
        elif scene == "terminal":
            terminal_clips[clip_idx] = [mid_frame]
        elif scene == "other":
            slide_clips[clip_idx] = [mid_frame]

    print(f"\n场景分类完成:")
    print(f"  slide: {len(slide_clips)} clips")
    print(f"  code: {len(code_clips)} clips")
    print(f"  terminal: {len(terminal_clips)} clips")
    print(f"  other: {n_clips - len(slide_clips) - len(code_clips) - len(terminal_clips)} clips")

    # 4. Extract unique slides
    print("\n提取幻灯片...")
    slides = extract_unique_slides(slide_clips, clip_captions, output_dir=str(out / "slides"))
    print(f"  unique slides: {len(slides)}")

    # 5. OCR slides
    print("OCR 幻灯片...")
    slides = ocr_slides(slides)

    # 6. Add transcript to slides
    for slide in slides:
        clip_idx = slide["clip_idx"]
        t = clip_idx * clip_secs
        slide["time"] = t
        m, s = divmod(int(t), 60)
        slide["time_str"] = f"{m:02d}:{s:02d}"
        # Find matching transcript
        for e in transcript:
            if e["start"] <= t <= e["end"]:
                slide["transcript"] = e["text"]
                break

    # 7. Track code changes
    print("\n追踪代码变化...")
    change_points = detect_code_changes(code_clips)
    print(f"  变化点: {len(change_points)}")

    code_snapshots = []
    if change_points:
        print("OCR 代码快照...")
        code_snapshots = extract_code_snapshots(code_clips, change_points)
        for snap in code_snapshots:
            clip_idx = snap["clip_idx"]
            t = clip_idx * clip_secs
            snap["time"] = t
            m, s = divmod(int(t), 60)
            snap["time_str"] = f"{m:02d}:{s:02d}"
            for e in transcript:
                if e["start"] <= t <= e["end"]:
                    snap["transcript"] = e["text"]
                    break
    print(f"  unique code snapshots: {len(code_snapshots)}")

    # 8. Terminal outputs — 复用 Phase 1 全帧：去重→拼接→长图分块OCR
    print("\n提取终端输出...")
    terminal_outputs = []
    from frame_stitcher import deduplicate_frames, stitch_scrolling_frames
    from external_api import ocr_long_image
    for clip_idx in sorted(terminal_clips.keys()):
        clip_frames = clip_all_frames.get(clip_idx, [])
        if not clip_frames:
            continue
        try:
            deduped = deduplicate_frames(clip_frames)
            stitched = stitch_scrolling_frames(deduped)
            text = ocr_long_image(stitched)
        except Exception:
            text = call_glm_ocr(clip_frames[len(clip_frames) // 2], "Text Recognition:", max_tokens=1024)
        if text and len(text) > 20:
            t = clip_idx * clip_secs
            m, s = divmod(int(t), 60)
            entry = {
                "time": t,
                "time_str": f"{m:02d}:{s:02d}",
                "text": text,
            }
            for e in transcript:
                if e["start"] <= t <= e["end"]:
                    entry["transcript"] = e["text"]
                    break
            terminal_outputs.append(entry)
    # Free non-terminal frame data
    for idx in list(clip_all_frames):
        if idx not in terminal_clips and idx not in code_clips:
            del clip_all_frames[idx]
    print(f"  terminal outputs: {len(terminal_outputs)}")

    # 9. Build structured output
    vs = VideoStructure(
        video_path=video_path,
        duration=duration,
        slides=[SlideEntry(
            time=s["time"],
            image_path=s.get("image_path", ""),
            ocr_text=s.get("ocr_text", ""),
            diagram_description=s.get("diagram_description", ""),
            transcript=s.get("transcript", ""),
        ) for s in slides],
        code_snapshots=[CodeSnapshot(
            time=s["time"],
            file_name=s.get("file_name", ""),
            code=s.get("code", ""),
            event=s.get("event", ""),
            transcript=s.get("transcript", ""),
        ) for s in code_snapshots],
        terminal_outputs=[{"time": t["time"], "text": t["text"], "transcript": t.get("transcript", "")}
                          for t in terminal_outputs],
        transcript=[{"start": e["start"], "end": e["end"], "text": e["text"]} for e in transcript],
    )

    json_path = str(out / f"{name}_structure.json")
    vs.save(json_path)
    print(f"\nJSON: {json_path}")

    # 10. Generate PDF
    pdf_data = vs.to_dict()
    for i, s in enumerate(pdf_data["slides"]):
        s["time_str"] = f"{int(s['time'])//60:02d}:{int(s['time'])%60:02d}"
    for s in pdf_data["code_snapshots"]:
        s["time_str"] = f"{int(s['time'])//60:02d}:{int(s['time'])%60:02d}"
    for t in pdf_data.get("terminal_outputs", []):
        t["time_str"] = f"{int(t['time'])//60:02d}:{int(t['time'])%60:02d}"

    elapsed = time.time() - t0
    print(f"\n完成! {len(slides)} slides, {len(code_snapshots)} code snapshots, {len(terminal_outputs)} terminal outputs")
    print(f"耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    return vs


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")

    sum_p = sp.add_parser("summarize", help="生成视频摘要")
    sum_p.add_argument("--thinking-budget", choices=["low", "medium", "high"],
                       default="low", help="8B 视觉描述详细程度 (low=默认, high=逐行抄录所有可见文本)")
    sum_p.add_argument("--top-n", type=int, default=20,
                       help="用 high 档重新描述的 clip 数 (按 embedding 重要性排序)")
    sum_p.add_argument("--output", default=None, help="输出文件路径 (默认 stdout)")
    sum_p.add_argument("--min-coverage", type=float, default=0.60,
                       help="Gemini 裁切的最小覆盖率阈值 (0-1, 默认 0.60, 越小越允许裁切)")
    ask_p = sp.add_parser("ask", help="多轮对话 (无参数进入交互模式)")
    ask_p.add_argument("question", nargs="*", help="可选，直接提问")
    fi_p = sp.add_parser("inspect", help="对指定时间段做视觉VQA")
    fi_p.add_argument("question", nargs="+")
    fi_p.add_argument("--start", type=float, required=True)
    fi_p.add_argument("--end", type=float, required=True)
    ext_p = sp.add_parser("external", help="外部知识查询（Gemini）")
    ext_p.add_argument("question", nargs="+")
    build_p = sp.add_parser("build", help="构建视频数据库（离线）")
    build_p.add_argument("--clip-secs", type=int, default=None, help="每个 clip 秒数 (默认 10)")
    build_p.add_argument("--fps", type=float, default=None, help="解码帧率 (默认 2)")
    build_p.add_argument("--frames", default=None,
                          help="每 clip 帧数：low=7, medium=14, high=21，或数字 (默认 low)")

    ext_p2 = sp.add_parser("extract", help="提取视频内容（幻灯片+代码+终端）→ JSON+PDF")
    ext_p2.add_argument("video", help="视频文件路径")
    ext_p2.add_argument("--srt", default=None, help="字幕文件路径")
    ext_p2.add_argument("--clip-secs", type=int, default=10, help="每个 clip 秒数 (默认 10)")
    ext_p2.add_argument("--output", default=None, help="输出目录")
    ext_p2.add_argument("--perspective", action="store_true", help="自动透视矫正倾斜帧")

    args = p.parse_args()
    if args.cmd == "build":
        frames = args.frames
        if frames is not None:
            try:
                frames = int(frames)
            except ValueError:
                pass
        cmd_build(clip_secs=args.clip_secs, video_fps=args.fps,
                  frames_per_clip=frames)
    elif args.cmd == "summarize":
        cmd_summarize(thinking_budget=args.thinking_budget, top_n=args.top_n,
                       output_path=args.output, min_coverage=args.min_coverage)
    elif args.cmd == "ask":
        cmd_ask(args.question or None)
    elif args.cmd == "inspect":
        cmd_frame_inspect(" ".join(args.question), args.start, args.end)
    elif args.cmd == "external":
        cmd_external(" ".join(args.question))
    elif args.cmd == "extract":
        try:
            cmd_extract(args.video, srt_path=args.srt,
                        clip_secs=args.clip_secs, output_dir=args.output,
                        perspective=args.perspective)
        finally:
            from external_api import shutdown_glm_ocr_workers
            shutdown_glm_ocr_workers()
    else:
        p.print_help()
