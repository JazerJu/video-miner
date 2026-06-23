import os

import numpy as np
import onnxruntime as ort


class SileroOnnxModel:
    def __init__(self, model_path: str):
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.reset_states()

    def reset_states(self, batch_size: int = 1) -> None:
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = np.zeros((batch_size, 0), dtype=np.float32)
        self._last_batch_size = batch_size

    def __call__(self, x: np.ndarray, sampling_rate: int) -> float:
        if sampling_rate != 16000:
            raise ValueError("Silero ONNX VAD only supports 16kHz in this wrapper")

        x = np.asarray(x, dtype=np.float32).reshape(1, -1)
        if x.shape[1] != 512:
            if x.shape[1] < 512:
                x = np.pad(x, ((0, 0), (0, 512 - x.shape[1])), mode="constant")
            else:
                x = x[:, :512]

        if self._context.shape[1] == 0:
            self._context = np.zeros((x.shape[0], 64), dtype=np.float32)
        model_input = np.concatenate([self._context, x], axis=1)
        output, state = self.session.run(
            None,
            {
                "input": model_input,
                "state": self._state,
                "sr": np.array(sampling_rate, dtype=np.int64),
            },
        )
        self._state = state.astype(np.float32, copy=False)
        self._context = model_input[:, -64:].astype(np.float32, copy=False)
        return float(output.reshape(-1)[0])


class SileroOnnxVAD:
    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        min_silence_duration_ms: int = 300,
        speech_pad_ms: int = 30,
    ):
        self.model = SileroOnnxModel(model_path)
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.min_silence_samples = sampling_rate * min_silence_duration_ms // 1000
        self.speech_pad_samples = sampling_rate * speech_pad_ms // 1000
        self.reset()

    def reset(self) -> None:
        self.model.reset_states()
        self.triggered = False
        self.temp_end = 0
        self.current_sample = 0

    def __call__(self, x, return_seconds: bool = False) -> dict:
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        window_size_samples = min(x.size, 512)
        if window_size_samples <= 0:
            return {}
        speech_prob = self.model(x, self.sampling_rate)
        self.current_sample += window_size_samples

        if speech_prob >= self.threshold and self.temp_end:
            self.temp_end = 0

        if speech_prob >= self.threshold and not self.triggered:
            self.triggered = True
            speech_start = max(
                0,
                self.current_sample - self.speech_pad_samples - window_size_samples,
            )
            return {"start": int(speech_start)}

        if speech_prob < self.threshold - 0.15 and self.triggered:
            if not self.temp_end:
                self.temp_end = self.current_sample
            if self.current_sample - self.temp_end < self.min_silence_samples:
                return {}
            speech_end = self.temp_end + self.speech_pad_samples
            self.temp_end = 0
            self.triggered = False
            return {"end": int(speech_end)}

        return {}


def default_silero_onnx_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "third_party",
        "silero-vad",
        "src",
        "silero_vad",
        "data",
        "silero_vad.onnx",
    )
