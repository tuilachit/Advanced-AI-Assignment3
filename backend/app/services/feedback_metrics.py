from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from app.domain.feedback_models import SpeakingMetric


class _UtteranceTimingLike(Protocol):
    @property
    def clock_id(self) -> str: ...
    @property
    def start_ms(self) -> float: ...
    @property
    def end_ms(self) -> float: ...
    @property
    def source(self) -> str: ...


class _TranscriptTurnLike(Protocol):
    @property
    def turn_id(self) -> str: ...
    @property
    def question_id(self) -> str: ...
    @property
    def speaker(self) -> str: ...
    @property
    def transcript_status(self) -> str: ...
    @property
    def text(self) -> str: ...
    @property
    def timing(self) -> _UtteranceTimingLike | None: ...


_TimingFingerprint = tuple[str, float, float, str]
_TurnFingerprint = tuple[str, str, str, str, str, _TimingFingerprint | None]
_TOKEN_METHOD = (
    "Unicode NFKC and casefold; curly apostrophes normalized; Unicode letter/digit runs "
    "with internal apostrophes are words; hyphens and underscores separate words."
)
_FILLERS = frozenset({"um", "uh", "erm", "er"})


def _tokens(text: str) -> list[str]:
    normalized = (
        unicodedata.normalize("NFKC", text)
        .casefold()
        .translate(str.maketrans("\u2019\u2018", "''"))
    )
    tokens: list[str] = []
    current: list[str] = []
    for index, char in enumerate(normalized):
        word_char = char.isalpha() or char.isdecimal()
        internal_apostrophe = (
            char == "'"
            and bool(current)
            and index + 1 < len(normalized)
            and (normalized[index + 1].isalpha() or normalized[index + 1].isdecimal())
        )
        if word_char or internal_apostrophe:
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def count_words(text: str) -> int:
    """Count normalized Unicode words without changing the source text."""
    return len(_tokens(text))


def count_transcript_fillers(text: str) -> int:
    """Count only exact um/uh/erm/er tokens preserved in the transcript."""
    return sum(token in _FILLERS for token in _tokens(text))


def _fingerprint(turn: _TranscriptTurnLike) -> _TurnFingerprint:
    timing = turn.timing
    timing_key = (
        None if timing is None else (timing.clock_id, timing.start_ms, timing.end_ms, timing.source)
    )
    return (
        turn.turn_id,
        turn.question_id,
        turn.speaker,
        turn.transcript_status,
        turn.text,
        timing_key,
    )


def _valid_timing(timing: _TimingFingerprint | None) -> bool:
    if timing is None:
        return False
    clock, start, end, source = timing
    return (
        bool(clock.strip())
        and source in {"provider_vad", "recording"}
        and not isinstance(start, bool)
        and not isinstance(end, bool)
        and isinstance(start, (int, float))
        and isinstance(end, (int, float))
        and math.isfinite(start)
        and math.isfinite(end)
        and 0 <= start < end
    )


def _duration(intervals: list[tuple[float, float]]) -> float:
    total = 0.0
    left, right = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = start, end
    return total + right - left


def calculate_speaking_metrics(
    turns: Sequence[_TranscriptTurnLike], *, question_id: str
) -> list[SpeakingMetric]:
    """Measure current submitted-answer snapshots; ownership is the caller's responsibility."""
    if not question_id.strip():
        raise ValueError("question_id must not be blank")
    unique: dict[str, _TurnFingerprint] = {}
    for turn in turns:
        fingerprint = _fingerprint(turn)
        if turn.turn_id in unique and unique[turn.turn_id] != fingerprint:
            raise ValueError(f"conflicting records for turn ID {turn.turn_id!r}")
        unique[turn.turn_id] = fingerprint
    usable = [
        record
        for _, record in sorted(unique.items())
        if record[1] == question_id
        and record[2] == "candidate"
        and record[3] == "final"
        and count_words(record[4]) > 0
    ]
    timed = [record for record in usable if _valid_timing(record[5])]
    clocks: dict[str, list[tuple[float, float]]] = {}
    for record in timed:
        timing = record[5]
        assert timing is not None
        clocks.setdefault(timing[0], []).append((timing[1], timing[2]))
    duration = sum(_duration(intervals) for _, intervals in sorted(clocks.items()))
    wpm_method = (
        f"{_TOKEN_METHOD} Only timed final candidate turns used. Overlapping/touching "
        "utterance intervals merged separately per clock; durations summed across clocks "
        "without cross-clock subtraction or inter-utterance gaps. "
        f"Timed-turn coverage: {len(timed)}/{len(usable)} usable turns; "
        f"{len(usable) - len(timed)} excluded for missing/invalid timing, including their words. "
        "Approximate transcript WPM, not articulation speed."
    )
    available = bool(timed) and math.isfinite(duration) and duration > 0
    wpm = sum(count_words(record[4]) for record in timed) * 60000 / duration if available else None
    if wpm is not None and not math.isfinite(wpm):
        available = False
        wpm = None
    return [
        SpeakingMetric(
            name="words_per_minute",
            status="available" if available else "not_available",
            value=round(wpm, 2) if wpm is not None else None,
            unit="words/min",
            method=wpm_method,
            unavailable_reason=None
            if available
            else "Insufficient valid positive timing evidence.",
            turn_ids=[record[0] for record in timed] if available else [],
        ),
        SpeakingMetric(
            name="transcript_filler_count",
            status="available" if usable else "not_available",
            value=float(sum(count_transcript_fillers(record[4]) for record in usable))
            if usable
            else None,
            unit="count",
            method=f"{_TOKEN_METHOD} Exact tokens: um, uh, erm, er. "
            "Unique final candidate turns only. Counts ASR-preserved occurrences, "
            "not all fillers spoken.",
            unavailable_reason=None if usable else "No usable final candidate transcript.",
            turn_ids=[record[0] for record in usable],
        ),
        SpeakingMetric(
            name="pause_count",
            status="not_available",
            value=None,
            unit="count",
            method="No pauses inferred from punctuation, transcript arrival times "
            "or ordinary gaps.",
            unavailable_reason="Explicit audio-analysis pause intervals and a documented "
            "threshold were not supplied.",
            turn_ids=[],
        ),
    ]
