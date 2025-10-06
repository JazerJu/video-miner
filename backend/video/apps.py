# video/apps.py
from django.apps import AppConfig
import threading
import time
import random
from django.db import connection
from concurrent.futures import ThreadPoolExecutor
import os

class VideoConfig(AppConfig):
    name = "video"

    def ready(self):
        if getattr(self, "_worker_started", False):
            return

        from .tasks import process_next_task, process_download_task, process_export_task, process_tts_task

        # ===== 线程池配置 =====
        # 根据 CPU 核心数动态计算
        cpu_count = os.cpu_count() or 4

        # 字幕任务：注意 optimise_srt 内部会创建 8 个线程（嵌套线程池）
        # 为避免线程爆炸（4 核 × 8 = 32 个内层线程），限制外层并发数
        subtitle_pool_size = min(2, cpu_count // 2)  # 最多 2 个，避免过度调度

        # 下载任务：I/O 密集（网络下载），建议 2-3 倍 CPU 核心数
        # 注意：受网络带宽限制，不宜过大
        download_pool_size = min(cpu_count * 3, 12)  # 最多 12 个并发

        # 导出任务：CPU 密集（FFmpeg），建议等于 CPU 核心数
        export_pool_size = cpu_count

        # TTS任务：CPU密集（音频合成 + FFmpeg），建议等于 CPU 核心数
        tts_pool_size = cpu_count

        # 创建线程池
        subtitle_executor = ThreadPoolExecutor(
            max_workers=subtitle_pool_size,
            thread_name_prefix="subtitle-worker"
        )

        download_executor = ThreadPoolExecutor(
            max_workers=download_pool_size,
            thread_name_prefix="download-worker"
        )

        export_executor = ThreadPoolExecutor(
            max_workers=export_pool_size,
            thread_name_prefix="export-worker"
        )

        tts_executor = ThreadPoolExecutor(
            max_workers=tts_pool_size,
            thread_name_prefix="tts-worker"
        )

        print(f"[ThreadPool] Subtitle workers: {subtitle_pool_size} (each creates 8 nested threads)")
        print(f"[ThreadPool] Download workers: {download_pool_size}")
        print(f"[ThreadPool] Export workers: {export_pool_size}")
        print(f"[ThreadPool] TTS workers: {tts_pool_size}")
        print(f"[ThreadPool] Total estimated threads: ~{subtitle_pool_size * 8 + download_pool_size + export_pool_size + tts_pool_size + 12}")

        # ===== 任务调度器 =====
        def _subtitle_dispatcher():
            """字幕任务调度器：从队列取任务，提交到线程池"""
            while True:
                try:
                    connection.close_if_unusable_or_obsolete()

                    # 包装任务执行函数
                    def task_wrapper():
                        try:
                            # 每个线程需要独立的数据库连接
                            connection.close_if_unusable_or_obsolete()
                            process_next_task()
                        except Exception as e:
                            print(f"Subtitle task error: {e}")

                    # 提交到线程池（非阻塞）
                    subtitle_executor.submit(task_wrapper)

                    # 短暂休眠，避免空轮询消耗 CPU
                    time.sleep(0.1 + random.random() * 0.1)
                except Exception as e:
                    print(f"Subtitle dispatcher error: {e}")
                    time.sleep(5)

        def _download_dispatcher():
            """下载任务调度器"""
            while True:
                try:
                    connection.close_if_unusable_or_obsolete()

                    def task_wrapper():
                        try:
                            connection.close_if_unusable_or_obsolete()
                            process_download_task()
                        except Exception as e:
                            print(f"Download task error: {e}")

                    download_executor.submit(task_wrapper)
                    time.sleep(0.1 + random.random() * 0.1)
                except Exception as e:
                    print(f"Download dispatcher error: {e}")
                    time.sleep(5)

        def _export_dispatcher():
            """导出任务调度器"""
            while True:
                try:
                    connection.close_if_unusable_or_obsolete()

                    def task_wrapper():
                        try:
                            connection.close_if_unusable_or_obsolete()
                            process_export_task()
                        except Exception as e:
                            print(f"Export task error: {e}")

                    export_executor.submit(task_wrapper)
                    time.sleep(0.1 + random.random() * 0.1)
                except Exception as e:
                    print(f"Export dispatcher error: {e}")
                    time.sleep(5)

        def _tts_dispatcher():
            """TTS任务调度器"""
            while True:
                try:
                    connection.close_if_unusable_or_obsolete()

                    def task_wrapper():
                        try:
                            connection.close_if_unusable_or_obsolete()
                            process_tts_task()
                        except Exception as e:
                            print(f"TTS task error: {e}")

                    tts_executor.submit(task_wrapper)
                    time.sleep(0.1 + random.random() * 0.1)
                except Exception as e:
                    print(f"TTS dispatcher error: {e}")
                    time.sleep(5)

        # 启动调度器线程（守护线程）
        threading.Thread(target=_subtitle_dispatcher, daemon=True, name="subtitle-dispatcher").start()
        threading.Thread(target=_download_dispatcher, daemon=True, name="download-dispatcher").start()
        threading.Thread(target=_export_dispatcher, daemon=True, name="export-dispatcher").start()
        threading.Thread(target=_tts_dispatcher, daemon=True, name="tts-dispatcher").start()

        self._worker_started = True
        print("[Workers] Background task dispatchers with thread pools started")
