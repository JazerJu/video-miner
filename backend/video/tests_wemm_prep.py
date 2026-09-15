"""vid_under/wemm_prep.py 的纯 numpy 部分：与 torch 流水线（qwen_vl_utils / Qwen3VL 处理器 / get_rope_index）对齐的规则。
取帧（ffmpeg）和分词（tokenizers）不在这里测，它们在 549 的真实片段上与 torch 输出逐项核对过。"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vid_under"))
import wemm_prep as P  # noqa: E402


class WeMMPrepTests(unittest.TestCase):
    def test_smart_resize_rounds_to_merged_patch_size(self):
        min_pixels = P.VIDEO_MIN_TOKEN_NUM * P.FACTOR * P.FACTOR
        max_pixels = P.VIDEO_MAX_TOKEN_NUM * P.FACTOR * P.FACTOR
        self.assertEqual(P.smart_resize(360, 640, P.FACTOR, min_pixels, max_pixels), (352, 640))
        # 1080p 被每两帧 768 个 token 的上限压到 1152x640（torch 版实测的就是这个尺寸）
        self.assertEqual(P.smart_resize(1080, 1920, P.FACTOR, min_pixels, max_pixels), (640, 1152))

    def test_smart_nframes_samples_even_counts(self):
        self.assertEqual(P.smart_nframes(20, 2.0), 20)
        self.assertEqual(P.smart_nframes(19, 2.0), 18)
        self.assertEqual(P.smart_nframes(250, 25.0), 20)

    def test_timestamps_average_each_temporal_pair(self):
        ts = P.timestamps(list(range(20)), 2.0)
        self.assertEqual(len(ts), 10)
        self.assertAlmostEqual(ts[0], 0.25)
        self.assertEqual(f"{ts[0]:.1f}", "0.2")
        self.assertEqual(len(P.timestamps(list(range(19)), 2.0)), 10)

    def test_same_size_resize_is_identity(self):
        frames = np.random.default_rng(0).integers(0, 256, (2, 32, 48, 3), dtype=np.uint8)
        np.testing.assert_array_equal(P.resize_bicubic_aa(frames, 32, 48), frames)

    def test_video_patches_pad_odd_frames_and_flatten(self):
        frames = np.random.default_rng(1).integers(0, 256, (3, 64, 64, 3), dtype=np.uint8)
        pixels, grid = P.video_patches(frames)
        self.assertEqual(grid, (2, 4, 4))
        self.assertEqual(pixels.shape, (2 * 4 * 4, 3 * 2 * 16 * 16))
        self.assertLessEqual(float(np.abs(pixels).max()), 1.0)

    def test_rope_index_gives_each_frame_group_its_own_grid(self):
        text, start, end = [11, 12, 13], P.VISION_START, 99
        group = [start] + [P.VIDEO_TOKEN] * 4 + [end]
        ids = np.array(text + group + [21] + group + [31, 32], np.int64)
        pos = P.rope_index(ids, (2, 4, 4))
        self.assertEqual(pos.shape, (3, 1, len(ids)))
        np.testing.assert_array_equal(pos[:, 0, :4], np.tile(np.arange(4), (3, 1)))
        # 第一组 2x2 视觉 token：t 恒为起始位置，h/w 按网格展开
        np.testing.assert_array_equal(pos[:, 0, 4:8], np.array([[4, 4, 4, 4], [4, 4, 5, 5], [4, 5, 4, 5]]))
        # 视觉 token 之后的文字从最大位置 +1 接着排
        np.testing.assert_array_equal(pos[:, 0, 8], [6, 6, 6])
        self.assertEqual(int(pos.max()), int(pos[0, 0, -1]))


if __name__ == "__main__":
    unittest.main()
