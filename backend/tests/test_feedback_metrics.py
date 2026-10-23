from copy import deepcopy
from dataclasses import dataclass, replace

import pytest

from app.services.feedback_metrics import (
    calculate_speaking_metrics,
    count_transcript_fillers,
    count_words,
)


@dataclass
class Timing:
    clock_id: str = "clock"
    start_ms: float = 0
    end_ms: float = 1000
    source: str = "provider_vad"


@dataclass
class Turn:
    turn_id: str = "t1"
    question_id: str = "q1"
    speaker: str = "candidate"
    transcript_status: str = "final"
    text: str = "Um I built it"
    timing: Timing | None = None


def metrics(turns):
    return calculate_speaking_metrics(turns, question_id="q1")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", 0),
        (" ... ___ -- ", 0),
        ("I built it.", 3),
        ("Don't stop; rock’n’roll", 3),
        ("full-stack snake_case", 4),
        ("Ｃａｆé １２３ 中文", 3),
        ("'quoted' 42", 2),
        ("a''b", 2),
    ],
)
def test_word_count(text, expected):
    assert count_words(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("UM, uh! Erm; er.", 4),
        ("um um uh", 3),
        ("ｕｍ", 1),
        ("summer urban Germany umbrella", 0),
        ("like so you know", 0),
        ("um's uhuh", 0),
        ("um-uh_er", 3),
        ("", 0),
    ],
)
def test_filler_boundaries(text, expected):
    assert count_transcript_fillers(text) == expected


def test_normal_metrics_and_rounding():
    result = metrics([Turn(timing=Timing(end_ms=7000))])
    assert [item.name for item in result] == [
        "words_per_minute",
        "transcript_filler_count",
        "pause_count",
    ]
    assert result[0].value == pytest.approx(round(4 * 60000 / 7000, 2))
    assert result[1].value == 1
    assert result[2].status == "not_available"
    assert result[2].value is None
    assert result[0].unit == "words/min"
    assert result[1].unit == result[2].unit == "count"


@pytest.mark.parametrize(
    "intervals,duration",
    [
        ([(0, 2000), (1000, 3000)], 3000),
        ([(0, 3000), (1000, 2000)], 3000),
        ([(0, 1000), (0, 1000)], 1000),
        ([(0, 1000), (1000, 2000)], 2000),
        ([(0, 1000), (5000, 6000)], 2000),
    ],
)
def test_interval_union(intervals, duration):
    turns = [
        Turn(turn_id=f"t{i}", text="one", timing=Timing(start_ms=start, end_ms=end))
        for i, (start, end) in enumerate(intervals)
    ]
    assert metrics(turns)[0].value == pytest.approx(round(2 * 60000 / duration, 2))


def test_different_clocks_and_recording_source():
    turns = [
        Turn(text="one", timing=Timing(start_ms=9000, end_ms=10000)),
        Turn(turn_id="t2", text="two", timing=Timing(clock_id="reset", source="recording")),
    ]
    assert metrics(turns)[0].value == 60


def test_identical_retry_and_order_independence():
    first = Turn(timing=Timing())
    second = Turn(turn_id="t2", timing=Timing(start_ms=2000, end_ms=3000))
    assert metrics([first, second]) == metrics([second, deepcopy(first), first])
    assert metrics([first, second])[0].turn_ids == ["t1", "t2"]


@pytest.mark.parametrize(
    "changes",
    [
        dict(question_id="q2"),
        dict(speaker="interviewer"),
        dict(transcript_status="partial"),
        dict(text="changed"),
        dict(timing=None),
        dict(timing=Timing(clock_id="other")),
        dict(timing=Timing(start_ms=1)),
        dict(timing=Timing(end_ms=2000)),
        dict(timing=Timing(source="recording")),
    ],
)
def test_conflicting_consumed_fields(changes):
    first = Turn(timing=Timing())
    with pytest.raises(ValueError, match="conflicting"):
        metrics([first, replace(first, **changes)])


@pytest.mark.parametrize(
    "timing",
    [
        None,
        Timing(start_ms=2000),
        Timing(end_ms=0),
        Timing(start_ms=-1),
        Timing(start_ms=float("nan")),
        Timing(end_ms=float("inf")),
        Timing(start_ms=True),
        Timing(end_ms=False),
        Timing(clock_id=" "),
        Timing(source="arrival_time"),
    ],
)
def test_invalid_timing_excluded_but_fillers_counted(timing):
    result = metrics([Turn(timing=timing)])
    assert result[0].status == "not_available"
    assert result[0].value is None
    assert result[0].turn_ids == []
    assert result[1].value == 1


def test_untimed_words_never_enter_wpm_numerator():
    result = metrics(
        [Turn(text="one", timing=Timing()), Turn(turn_id="t2", text="um many untimed words")]
    )
    assert result[0].value == 60
    assert result[0].turn_ids == ["t1"]
    assert result[1].turn_ids == ["t1", "t2"]
    assert result[1].value == 1
    method = result[0].method
    for description in [
        "Unicode NFKC",
        "internal apostrophes",
        "timed final candidate",
        "per clock",
        "1/2",
        "1 excluded",
        "not articulation speed",
    ]:
        assert description in method


@pytest.mark.parametrize(
    "changes",
    [
        dict(speaker="interviewer"),
        dict(transcript_status="pending"),
        dict(transcript_status="partial"),
        dict(transcript_status="failed"),
        dict(text=" "),
        dict(text="..."),
        dict(question_id="q2"),
    ],
)
def test_unusable_turns(changes):
    result = metrics([replace(Turn(timing=Timing()), **changes)])
    assert all(item.status == "not_available" and item.value is None for item in result)
    assert all(item.unavailable_reason and item.turn_ids == [] for item in result)


def test_empty_input():
    assert all(item.status == "not_available" for item in metrics([]))


def test_zero_fillers_available():
    assert metrics([Turn(text="no hesitation")])[1].value == 0
    assert metrics([Turn(text="no hesitation")])[1].status == "available"


@pytest.mark.parametrize("question_id", ["", " ", "\t\n"])
def test_blank_question_id(question_id):
    with pytest.raises(ValueError, match="question_id"):
        calculate_speaking_metrics([], question_id=question_id)


def test_inputs_unchanged():
    turns = [Turn(text="  UM’s full-stack  ", timing=Timing()), Turn(turn_id="t2")]
    before = deepcopy(turns)
    metrics(turns)
    assert turns == before
    assert turns[0].text == before[0].text
    assert turns[0].timing == before[0].timing


def test_no_cross_turn_tokens_or_pause_inference():
    result = metrics(
        [
            Turn(text="u", timing=Timing()),
            Turn(turn_id="t2", text="m ...", timing=Timing(start_ms=6000, end_ms=7000)),
        ]
    )
    assert result[1].value == 0
    assert result[2].status == "not_available"
    assert "threshold" in result[2].unavailable_reason
