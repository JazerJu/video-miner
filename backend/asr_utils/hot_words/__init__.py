# pyright: reportImportCycles=false, reportUnsupportedDunderAll=false
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .algo_phoneme import Phoneme
    from .hot_phoneme import CorrectionResult, PhonemeCorrector

__all__ = [
    "PhonemeCorrector",
    "CorrectionResult",
    "get_phoneme_info",
    "Phoneme",
    "get_corrector",
    "correct_srt_text",
]

_corrector: PhonemeCorrector | None = None
_current_hotwords: str = ""


def __getattr__(name: str):
    if name in {"PhonemeCorrector", "CorrectionResult"}:
        from .hot_phoneme import CorrectionResult, PhonemeCorrector

        return {"PhonemeCorrector": PhonemeCorrector, "CorrectionResult": CorrectionResult}[
            name
        ]
    if name in {"get_phoneme_info", "Phoneme"}:
        from .algo_phoneme import Phoneme, get_phoneme_info

        return {"get_phoneme_info": get_phoneme_info, "Phoneme": Phoneme}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_corrector(
    hotwords: str = "",
    threshold: float = 0.8,
    similar_threshold: float = 0.6,
) -> PhonemeCorrector:
    """Get or create the global PhonemeCorrector singleton."""
    from .hot_phoneme import PhonemeCorrector

    global _corrector, _current_hotwords
    if _corrector is None or _current_hotwords != hotwords:
        _corrector = PhonemeCorrector(
            threshold=threshold,
            similar_threshold=similar_threshold,
        )
        if hotwords.strip():
            count = _corrector.update_hotwords(hotwords)
            logger.info(f"Loaded {count} hotwords")
        _current_hotwords = hotwords
    return _corrector


def correct_srt_text(srt_content: str, hotwords: str) -> str:
    """Apply hotword correction to SRT content. Preserves timestamps, only fixes text."""
    if not hotwords.strip():
        return srt_content

    corrector = get_corrector(hotwords)

    srt_time_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3}\s-->\s\d{2}:\d{2}:\d{2}[.,]\d{3})"
    )

    blocks = re.split(r"\n\s*\n", srt_content.strip())
    corrected_blocks = []
    idx = 1

    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            corrected_blocks.append(block)
            continue

        time_line_idx = None
        for i, line in enumerate(lines):
            if srt_time_pattern.match(line):
                time_line_idx = i
                break

        if time_line_idx is None:
            corrected_blocks.append(block)
            continue

        text_lines = lines[time_line_idx + 1 :]
        original_text = "\n".join(text_lines)

        result = corrector.correct(original_text)
        corrected_text = result.text

        new_block = f"{idx}\n{lines[time_line_idx]}\n{corrected_text}"
        corrected_blocks.append(new_block)
        idx += 1

    return "\n\n".join(corrected_blocks) + "\n"
