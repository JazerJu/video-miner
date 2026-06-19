"""Process entrypoint for VidUnder build/caption isolation.

This module intentionally has no Django imports. multiprocessing spawn imports
the target module in the child before Django app setup is guaranteed.
"""
from __future__ import annotations

import os
import sys
import traceback


def vidunder_build_process_main(progress_q, vid_under_dir: str, video_path: str, srt_path: str, db_name: str):
    """Run MiniCPM build in a clean child process so CUDA state dies on exit."""
    try:
        if vid_under_dir not in sys.path:
            sys.path.insert(0, vid_under_dir)

        os.environ["VIDUNDER_VIDEO_PATH"] = video_path
        os.environ["VIDUNDER_SRT_PATH"] = srt_path
        os.environ.setdefault("VIDUNDER_ONNX_THREADS", "0")

        from video_db import build_database

        def _child_progress(stage, current, total):
            progress_q.put({
                "type": "progress",
                "stage": stage,
                "current": current,
                "total": total,
            })

        build_database(video_path, srt_path, db_name=db_name, progress_cb=_child_progress)
        progress_q.put({"type": "done"})
    except BaseException:
        progress_q.put({"type": "error", "traceback": traceback.format_exc()})
        raise
