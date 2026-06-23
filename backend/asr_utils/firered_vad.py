"""
FireRed VAD ONNX wrapper — VADIterator-compatible interface.

Uses lxp3/vad-filter-onnx firered_vad.int8.onnx with fbank built-in.
Input: raw float32 waveform (normalized to [-1, 1]), 16kHz mono.
Output: per-frame speech probability → speech segment boundaries.
"""

import numpy as np
import onnxruntime as ort
from pathlib import Path


class FireRedVAD:
    """Streaming VAD with VADIterator-compatible __call__ interface.

    Drop-in replacement for silero_vad.VADIterator.
    """

    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        min_silence_duration_ms: int = 300,
        speech_pad_ms: int = 30,
    ):
        if sampling_rate != 16000:
            raise ValueError("FireRed VAD only supports 16kHz")

        self.threshold = threshold
        self.sampling_rate = sampling_rate

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=opts
        )

        self.num_caches = 8
        self.cache_shape = (1, 128, 19)
        self.caches = np.zeros(
            (self.num_caches, *self.cache_shape), dtype=np.float32
        )

        self.min_silence_samples = sampling_rate * min_silence_duration_ms // 1000
        self.speech_pad_samples = sampling_rate * speech_pad_ms // 1000

        self._buffer = np.array([], dtype=np.float32)
        # Absolute sample index of self._buffer[0]. This must advance by the
        # number of samples removed from the rolling buffer, not by the number
        # of model output frames. Otherwise long streams drift.
        self._sample_offset = 0

        # speech boundary tracking
        self._in_speech = False
        self._speech_start = None
        self._silence_start = None

    def reset(self) -> None:
        self.caches = np.zeros(
            (self.num_caches, *self.cache_shape), dtype=np.float32
        )
        self._buffer = np.array([], dtype=np.float32)
        self._sample_offset = 0
        self._in_speech = False
        self._speech_start = None
        self._silence_start = None

    def __call__(self, x, return_seconds: bool = False) -> dict:
        """Process audio chunk and return speech boundary if detected.

        Args:
            x: numpy array (n_samples,) float32, normalized to [-1, 1]
            return_seconds: ignored (sample indices returned)
        Returns:
            {}  - no boundary detected
            {"start": int}  - speech just started
            {"end": int}    - speech just ended
            {"start": int, "end": int}  - short utterance fully contained
        """
        if isinstance(x, np.ndarray):
            pass
        elif hasattr(x, "numpy"):  # torch tensor
            x = x.numpy().astype(np.float32)
        else:
            x = np.array(x, dtype=np.float32)
        x = x.ravel()

        self._buffer = np.concatenate([self._buffer, x])

        # Process full frames: need at least 400 samples per chunk
        chunk_size = 1840  # 115ms → 10 frames; good real-time latency
        frame_shift = 160
        window_len = 400
        overlap = window_len - frame_shift  # 240 samples

        result = {}

        while len(self._buffer) >= window_len:
            end = min(chunk_size, len(self._buffer))
            chunk = self._buffer[:end].reshape(1, -1).astype(np.float32)

            probs, self.caches = self.session.run(
                None, {"speech": chunk, "caches_in": self.caches}
            )
            probs = probs.ravel()  # [num_frames]

            buffer_start_sample = self._sample_offset
            for frame_idx, prob in enumerate(probs):
                sample_pos = buffer_start_sample + frame_idx * frame_shift

                if self._in_speech:
                    if prob < self.threshold:
                        if self._silence_start is None:
                            self._silence_start = sample_pos
                        silence_dur = sample_pos - self._silence_start
                        if silence_dur >= self.min_silence_samples:
                            end_sample = self._silence_start - self.speech_pad_samples
                            result["end"] = max(
                                self._speech_start + self.speech_pad_samples, end_sample
                            )
                            self._in_speech = False
                            self._speech_start = None
                            self._silence_start = None
                    else:
                        self._silence_start = None
                else:
                    if prob >= self.threshold:
                        self._in_speech = True
                        self._speech_start = max(
                            0, sample_pos - self.speech_pad_samples
                        )
                        self._silence_start = None
                        result["start"] = self._speech_start

            processed = min(end - overlap, end)
            self._sample_offset += processed
            self._buffer = self._buffer[processed:] if processed < len(self._buffer) else np.array([], dtype=np.float32)

        return result
