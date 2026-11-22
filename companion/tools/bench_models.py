"""Benchmark speech recognition models on WAV files (16 kHz mono).

Usage: uv run python tools/bench_models.py file1.wav [file2.wav ...] [--models a,b]
Prints load time, per-file latency (warm, median of 3) and the text.
"""

import argparse
import statistics
import time

import onnx_asr

MODELS = {
    "parakeet-v3": dict(model="nemo-parakeet-tdt-0.6b-v3", quantization="int8"),
    "canary-v2": dict(model="nemo-canary-1b-v2", quantization="int8"),
    "gigaam-multi": dict(model="gigaam-multilingual-ctc"),
    "gigaam-v3-ru": dict(model="gigaam-v3-e2e-rnnt"),
    "whisper-turbo": dict(model="onnx-community/whisper-large-v3-turbo", quantization="int8"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--models", default=",".join(MODELS))
    args = ap.parse_args()
    for name in args.models.split(","):
        spec = MODELS[name]
        t0 = time.perf_counter()
        try:
            model = onnx_asr.load_model(**spec)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"{name}: load failed: {exc!r}")
            continue
        print(f"\n== {name}: loaded in {time.perf_counter() - t0:.1f} s")
        for path in args.files:
            model.recognize(path)  # warm-up
            times, text = [], ""
            for _ in range(3):
                t = time.perf_counter()
                text = model.recognize(path)
                times.append(time.perf_counter() - t)
            print(f"  {path.rsplit('/', 1)[-1]}: {statistics.median(times) * 1000:.0f} ms | {text}")


if __name__ == "__main__":
    main()
