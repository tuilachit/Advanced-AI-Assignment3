import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.feedback_models import (
    CriterionFeedback,
    EvidenceQuote,
    FeedbackReport,
    FeedbackRequest,
    FeedbackStartResponse,
    ModelFeedbackAssessment,
    ModelQuestionAssessment,
    QuestionFeedback,
    SpeakingMetric,
)


def criterion(**changes):
    return (
        dict(
            criterion="relevance",
            applicability="assessed",
            score=3,
            explanation="Addresses the question",
            evidence=[{"turn_id": "t1", "quote": " I did it. "}],
            improvement=None,
        )
        | changes
    )


def metric(**changes):
    return (
        dict(
            name="words_per_minute",
            status="available",
            value=120.5,
            unit="words/min",
            method="Transcript words / utterance minutes",
            unavailable_reason=None,
            turn_ids=["t1"],
        )
        | changes
    )


def question(**changes):
    return dict(question_id="q1", criteria=[criterion()], speaking_metrics=[metric()]) | changes


def report(**changes):
    return (
        dict(
            report_id="r1",
            interview_id="i1",
            context_hash="opaque-hash",
            transcript_revision=0,
            generated_at="2026-10-21T10:00:00+11:00",
            question_feedback=[question()],
            limitations=[],
        )
        | changes
    )


def test_valid_report_round_trip_preserves_quotes_and_normalizes_utc():
    parsed = FeedbackReport.model_validate(report())
    assert parsed.generated_at == datetime(2026, 10, 20, 23, tzinfo=UTC)
    assert parsed.generated_at.tzinfo is UTC
    payload = parsed.model_dump(mode="json")
    assert payload["generated_at"].endswith("Z")
    assert payload["question_feedback"][0]["criteria"][0]["evidence"][0]["quote"] == " I did it. "
    assert payload["question_feedback"][0]["criteria"][0]["improvement"] is None
    assert FeedbackReport.model_validate_json(json.dumps(payload)) == parsed


@pytest.mark.parametrize("score", range(5))
def test_score_anchors(score):
    assert CriterionFeedback.model_validate(criterion(score=score)).score == score


@pytest.mark.parametrize("score", [-1, 5, True, "3", 3.0, None])
def test_invalid_assessed_scores(score):
    with pytest.raises(ValidationError):
        CriterionFeedback.model_validate(criterion(score=score))


def test_assessed_requires_evidence():
    with pytest.raises(ValidationError):
        CriterionFeedback.model_validate(criterion(evidence=[]))


@pytest.mark.parametrize("applicability", ["not_applicable", "insufficient_evidence"])
def test_non_assessed_requires_null_score(applicability):
    assert (
        CriterionFeedback.model_validate(
            criterion(applicability=applicability, score=None, evidence=[])
        ).score
        is None
    )
    with pytest.raises(ValidationError):
        CriterionFeedback.model_validate(criterion(applicability=applicability))


@pytest.mark.parametrize("value", [True, "120", -1, float("inf"), float("-inf"), float("nan")])
def test_invalid_metric_numbers(value):
    with pytest.raises(ValidationError):
        SpeakingMetric.model_validate(metric(value=value))


@pytest.mark.parametrize("name", ["transcript_filler_count", "pause_count"])
@pytest.mark.parametrize("value", [0, 2, 2.0])
def test_whole_counts(name, value):
    assert (
        SpeakingMetric.model_validate(metric(name=name, unit="count", value=value)).value == value
    )


@pytest.mark.parametrize("name", ["transcript_filler_count", "pause_count"])
def test_fractional_counts_rejected(name):
    with pytest.raises(ValidationError):
        SpeakingMetric.model_validate(metric(name=name, unit="count", value=1.5))


@pytest.mark.parametrize(
    "name,unit",
    [
        ("words_per_minute", "count"),
        ("pause_count", "words/min"),
        ("transcript_filler_count", "words/min"),
    ],
)
def test_wrong_units(name, unit):
    with pytest.raises(ValidationError):
        SpeakingMetric.model_validate(metric(name=name, unit=unit))


@pytest.mark.parametrize(
    "changes",
    [
        dict(value=None),
        dict(unavailable_reason="Missing"),
        dict(status="not_available", value=None),
        dict(status="not_available", unavailable_reason="Missing"),
    ],
)
def test_invalid_availability(changes):
    with pytest.raises(ValidationError):
        SpeakingMetric.model_validate(metric(**changes))


def test_unavailable_and_zero_are_distinct():
    unavailable = SpeakingMetric.model_validate(
        metric(status="not_available", value=None, unavailable_reason="No timing", turn_ids=[])
    )
    assert unavailable.value is None
    assert SpeakingMetric.model_validate(metric(value=0)).value == 0


@pytest.mark.parametrize(
    "model,payload",
    [
        (EvidenceQuote, dict(turn_id=" ", quote="quote")),
        (EvidenceQuote, dict(turn_id="t", quote="\t\n")),
        (CriterionFeedback, criterion(explanation=" ")),
        (CriterionFeedback, criterion(improvement=" ")),
        (SpeakingMetric, metric(method=" ")),
        (SpeakingMetric, metric(turn_ids=[" "])),
        (SpeakingMetric, metric(status="not_available", value=None, unavailable_reason=" ")),
        (QuestionFeedback, question(question_id=" ")),
        (FeedbackReport, report(report_id=" ")),
        (FeedbackReport, report(interview_id=" ")),
        (FeedbackReport, report(context_hash=" ")),
        (FeedbackReport, report(limitations=[" "])),
        (ModelQuestionAssessment, dict(question_id=" ", criteria=[])),
        (FeedbackRequest, dict(request_id=" ", expected_transcript_revision=0)),
    ],
)
def test_blank_text_rejected(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("value", [-1, True, "0", 0.0])
def test_strict_revisions(value):
    for model, payload in [
        (FeedbackReport, report(transcript_revision=value)),
        (FeedbackRequest, dict(request_id="request", expected_transcript_revision=value)),
    ]:
        with pytest.raises(ValidationError):
            model.model_validate(payload)


@pytest.mark.parametrize("value", ["2026-10-21T10:00:00", datetime(2026, 10, 21)])
def test_naive_timestamp_rejected(value):
    with pytest.raises(ValidationError):
        FeedbackReport.model_validate(report(generated_at=value))


def test_aware_datetime_input_normalized():
    parsed = FeedbackReport.model_validate(
        report(generated_at=datetime(2026, 10, 21, tzinfo=timezone(timedelta(hours=-5))))
    )
    assert parsed.generated_at == datetime(2026, 10, 21, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    "model,payload",
    [
        (QuestionFeedback, question(criteria=[criterion(), criterion()])),
        (QuestionFeedback, question(speaking_metrics=[metric(), metric()])),
        (SpeakingMetric, metric(turn_ids=["t1", "t1"])),
        (FeedbackReport, report(question_feedback=[question(), question()])),
        (ModelQuestionAssessment, dict(question_id="q", criteria=[criterion(), criterion()])),
        (ModelFeedbackAssessment, dict(questions=[dict(question_id="q", criteria=[])] * 2)),
    ],
)
def test_duplicates_rejected(model, payload):
    with pytest.raises(ValidationError, match="unique"):
        model.model_validate(payload)


def test_distinct_questions_can_reuse_criterion_and_turn_ids():
    parsed = FeedbackReport.model_validate(
        report(question_feedback=[question(), question(question_id="q2")])
    )
    assert len(parsed.question_feedback) == 2
    # Ownership of these turn IDs is deliberately left to the service.


def test_empty_collections_and_opaque_ids_allowed():
    assert FeedbackReport.model_validate(report(question_feedback=[])).question_feedback == []
    assert ModelFeedbackAssessment(questions=[]).questions == []
    assert FeedbackRequest(request_id="fixture-label", expected_transcript_revision=0)


@pytest.mark.parametrize(
    "model,payload",
    [
        (EvidenceQuote, dict(turn_id="t", quote="x", unknown=True)),
        (FeedbackReport, report(schema_version="2.0")),
        (FeedbackReport, report(rubric_version="2.0")),
        (CriterionFeedback, criterion(criterion="accent")),
        (CriterionFeedback, criterion(applicability="unknown")),
        (SpeakingMetric, metric(name="emotion")),
        (SpeakingMetric, metric(status="unknown")),
        (SpeakingMetric, metric(unit="seconds")),
        (FeedbackRequest, dict(request_id="x" * 201, expected_transcript_revision=0)),
        (EvidenceQuote, dict(turn_id="t", quote="x" * 1001)),
        (CriterionFeedback, criterion(explanation="x" * 1501)),
        (CriterionFeedback, criterion(improvement="x" * 1001)),
    ],
)
def test_schema_constraints(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_generating_only_start_response():
    assert FeedbackStartResponse(feedback_status="generating").model_dump() == {
        "feedback_status": "generating"
    }
    for status in ["ready", "failed", "not_requested"]:
        with pytest.raises(ValidationError):
            FeedbackStartResponse.model_validate(dict(feedback_status=status))


def test_json_schema_generation():
    schema = FeedbackReport.model_json_schema()
    assert schema["additionalProperties"] is False
    assert FeedbackStartResponse.model_json_schema()["properties"]["feedback_status"]["const"] == (
        "generating"
    )
