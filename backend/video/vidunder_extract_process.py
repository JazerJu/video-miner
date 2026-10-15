"""Process entrypoint for VidUnder extract isolation.

This module intentionally has no Django imports. multiprocessing spawn imports
the target module in the child before Django app setup is guaranteed.
"""
from __future__ import annotations

import os
import sys
import traceback


def vidunder_extract_process_main(progress_q, vid_under_dir: str, video_path: str, srt_path: str,
                                  output_dir: str, clip_scenes: dict):
    """Run GLM-OCR extract in a child process so its llama.cpp decoder dies on exit.

    The decoder cannot be freed and rebuilt in one process (external_api._get_glm_ocr_engine),
    so a decoder left in the web process would hold ~1.4 GB through the next task's build.
    Inside this child the layout is unchanged: the decoder runs here, the ONNX encoder in its
    own worker process.
    """
    try:
        if vid_under_dir not in sys.path:
            sys.path.insert(0, vid_under_dir)

        os.environ["VIDUNDER_VIDEO_PATH"] = video_path
        os.environ["VIDUNDER_SRT_PATH"] = srt_path

        from main import cmd_extract, _log_rss
        from external_api import shutdown_glm_ocr_workers

        def _child_progress(stage, current, total):
            progress_q.put({
                "type": "progress",
                "stage": stage,
                "current": current,
                "total": total,
            })

        try:
            cmd_extract(video_path, srt_path=srt_path, output_dir=output_dir,
                        progress_cb=_child_progress, clip_scenes=clip_scenes)
        finally:
            shutdown_glm_ocr_workers(stop_decoder=True)
            _log_rss("ocr workers stopped")
        progress_q.put({"type": "done"})
    except BaseException:
        progress_q.put({"type": "error", "traceback": traceback.format_exc()})
        raise
