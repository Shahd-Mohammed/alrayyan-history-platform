from types import SimpleNamespace

from datetime import datetime, timedelta, timezone

from alrayyan.services.datetime_utils import as_utc_naive
from alrayyan.services.semantic_search import _normalize_keyword_text
from alrayyan.services.tutor_engine import (
    _extract_json,
    _history_text,
    _validate_payload,
    is_non_learning_message,
    preserve_concept_for_evaluated_answer,
)


def run_tests():
    # Database DateTime columns are naive UTC, while newly assigned timestamps
    # can be timezone-aware. Comparing them directly raises TypeError.
    aware_utc = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)
    naive_utc = datetime(2026, 10, 15, 11, 0)
    assert as_utc_naive(aware_utc) == naive_utc
    assert as_utc_naive(naive_utc) == naive_utc
    assert as_utc_naive(None) is None
    assert _normalize_keyword_text("الإِسْتِعْمَار") == "الاستعمار"
    assert _normalize_keyword_text("الاستعماررررررر") == "الاستعمار"
    assert as_utc_naive(
        datetime(2026, 10, 15, 13, 0, tzinfo=timezone(timedelta(hours=2)))
    ) == naive_utc
    wrapped_payload = _extract_json(
        'سأعيد النتيجة المنظمة الآن: {"reply": "مرحبًا"}'
    )
    assert wrapped_payload["reply"] == "مرحبًا"

    payload = _validate_payload(
        {
            "reply": "إجابة جيدة. لماذا تعتقد أن ذلك حدث؟",
            "action": "ask_follow_up",
            "evaluation": "correct",
            "concept": "الدوافع الاقتصادية",
            "mastery_delta": 8,
            "source_chunk_ids": [1, "2", 99],
            "suggest_quick_quiz": True,
        },
        {1, 2, 3},
    )
    assert payload["action"] == "ask_follow_up"
    assert payload["evaluation"] == "correct"
    assert payload["source_chunk_ids"] == [1, 2]
    assert payload["mastery_delta"] == 8

    safe = _validate_payload(
        {
            "reply": "لنراجع الفكرة.",
            "action": "unknown",
            "evaluation": "unknown",
            "mastery_delta": 500,
        },
        set(),
    )
    assert safe["action"] == "explain"
    assert safe["evaluation"] == "not_evaluated"
    assert safe["mastery_delta"] == 0

    history = _history_text([
        SimpleNamespace(role="student", content="ما السبب؟"),
        SimpleNamespace(role="tutor", content="ماذا تتذكر؟"),
    ])
    assert "الطالب: ما السبب؟" in history
    assert "المعلم: ماذا تتذكر؟" in history

    # Evaluated answers stay attached to the current concept, so a model label
    # variation cannot create a new 0% mastery row. A deliberate advance may switch.
    for evaluation in ("correct", "partially_correct", "incorrect", "needs_explanation", "off_topic"):
        payload = {"evaluation": evaluation, "concept": "صياغة مختلفة"}
        preserve_concept_for_evaluated_answer(
            "دوافع الاستعمار", "ask_follow_up", payload
        )
        assert payload["concept"] == "دوافع الاستعمار"

    verification_payload = {"evaluation": "not_evaluated", "concept": "المفهوم العام"}
    preserve_concept_for_evaluated_answer(
        "دوافع الاستعمار", "verify_mastery", verification_payload
    )
    assert verification_payload["concept"] == "دوافع الاستعمار"

    advanced_payload = {"evaluation": "correct", "concept": "النتائج السياسية"}
    preserve_concept_for_evaluated_answer(
        "دوافع الاستعمار", "advance", advanced_payload
    )
    assert advanced_payload["concept"] == "النتائج السياسية"

    # Casual replies must never count as academic answers, while a real answer
    # that ends with a friendly phrase must still be evaluated normally.
    assert is_non_learning_message("حبيبي انت")
    assert is_non_learning_message("ياخوي")
    assert is_non_learning_message("لا عنجد")
    assert not is_non_learning_message("عشان تسيطر على ثرواتها ياخوي")

    print("PASS: Tutor payload validation, social-message guard, and conversation history")


if __name__ == "__main__":
    run_tests()
