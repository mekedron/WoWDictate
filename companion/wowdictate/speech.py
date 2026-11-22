"""Speech recognition backends (onnx-asr, CPU)."""

from __future__ import annotations

import logging
import threading
import time

import numpy as np
import onnx_asr
import onnxruntime as ort

log = logging.getLogger(__name__)

MODELS = {
    "parakeet-v3": dict(model="nemo-parakeet-tdt-0.6b-v3", quantization="int8"),
    "canary-v2": dict(model="nemo-canary-1b-v2", quantization="int8"),
    "gigaam-v3": dict(model="gigaam-v3-e2e-rnnt"),
    "gigaam-multi": dict(model="gigaam-multilingual-ctc"),
    "whisper-turbo": dict(model="onnx-community/whisper-large-v3-turbo", quantization="int8"),
}
NEEDS_LANGUAGE = {"canary-v2"}
TRANSLATOR = "canary-v2"


class Recognizer:
    """Holds the main model and, on first use, the Canary model for translation."""

    def __init__(self, name: str, language: str, threads: int = 0):
        if name not in MODELS:
            raise ValueError(f"unknown model {name!r}, choose one of {', '.join(MODELS)}")
        self.name = name
        self.language = language
        self.threads = threads
        self.models: dict[str, object] = {}
        self.lock = threading.Lock()

    def _load(self, name: str):
        if name not in self.models:
            options = ort.SessionOptions()
            if self.threads:
                options.intra_op_num_threads = self.threads
            start = time.perf_counter()
            self.models[name] = onnx_asr.load_model(**MODELS[name], sess_options=options)
            log.info("model %s loaded in %.1f s", name, time.perf_counter() - start)
        return self.models[name]

    def preload(self, translator: bool = False) -> None:
        """Load and warm up the models, so the first dictation is as fast as the rest."""
        with self.lock:
            names = [self.name] + ([TRANSLATOR] if translator and self.name != TRANSLATOR else [])
            for name in names:
                self._load(name)
                noise = np.random.default_rng(0).normal(0, 0.01, 16000 * 3).astype(np.float32)
                for _ in range(3):
                    self._recognize(name, noise)

    def _recognize(self, name: str, audio: np.ndarray, **kwargs) -> str:
        model = self._load(name)
        if name in NEEDS_LANGUAGE and "language" not in kwargs:
            kwargs["language"] = self.language
        return str(model.recognize(audio, sample_rate=16000, **kwargs)).strip()

    def transcribe(self, audio: np.ndarray, translate: str | None = None) -> str:
        with self.lock:
            if translate:
                return self._recognize(
                    TRANSLATOR, audio, language=self.language, target_language=translate
                )
            return self._recognize(self.name, audio)
