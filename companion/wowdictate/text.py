"""Clean-up of recognized text before it goes to chat."""

from __future__ import annotations

import re


def build_replacer(replace: dict[str, str]):
    rules = [
        (re.compile(rf"(?<!\w){re.escape(src)}(?!\w)", re.IGNORECASE), dst)
        for src, dst in sorted(replace.items(), key=lambda kv: -len(kv[0]))
    ]

    def apply(text: str) -> str:
        for pattern, dst in rules:
            text = pattern.sub(dst, text)
        return text

    return apply


def clean(text: str, strip_final_period: bool, replacer) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Some models glue a dash to the previous word ("язык- это").
    text = re.sub(r"(\w)([-–—]) ", r"\1 \2 ", text)
    text = replacer(text)
    if strip_final_period and text.endswith(".") and not text.endswith(".."):
        text = text[:-1]
    return text
