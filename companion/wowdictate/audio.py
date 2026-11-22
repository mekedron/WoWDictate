"""Microphone capture at 16 kHz mono with an optional pre-roll ring buffer."""

from __future__ import annotations

import collections
import logging
import threading

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK = 480  # 30 ms


def find_device(name: str) -> int | None:
    if not name or name == "default":
        return None
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and name.lower() in dev["name"].lower():
            return index
    log.warning("input device %r not found, using default", name)
    return None


class Microphone:
    def __init__(self, device: str, preroll_ms: int, max_seconds: float):
        self.device = find_device(device)
        self.always_open = preroll_ms > 0
        self.preroll = collections.deque(maxlen=max(1, preroll_ms * SAMPLE_RATE // 1000 // BLOCK))
        self.max_blocks = int(max_seconds * SAMPLE_RATE / BLOCK)
        self.chunks: list[np.ndarray] | None = None
        self.lock = threading.Lock()
        self.stream: sd.InputStream | None = None
        if self.always_open:
            self._open()

    def _open(self) -> None:
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK,
            device=self.device,
            callback=self._callback,
        )
        self.stream.start()

    def _close(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        block = indata[:, 0].copy()
        with self.lock:
            if self.chunks is not None:
                if len(self.chunks) < self.max_blocks:
                    self.chunks.append(block)
            elif self.always_open:
                self.preroll.append(block)

    def start(self) -> None:
        with self.lock:
            self.chunks = list(self.preroll) if self.always_open else []
            self.preroll.clear()
        if not self.always_open:
            self._open()

    def stop(self) -> np.ndarray:
        if not self.always_open:
            self._close()
        with self.lock:
            chunks, self.chunks = self.chunks or [], None
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def close(self) -> None:
        self._close()


def rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))
