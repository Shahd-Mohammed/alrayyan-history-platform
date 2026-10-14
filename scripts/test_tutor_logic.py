from types import SimpleNamespace

from alrayyan.services.tutor_engine import (
    _extract_json,
    _history_text,
    _validate_payload,
    is_non_learning_message,
)


def run_tests():
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

    # Casual replies must never count as academic answers, while a real answer
    # that ends with a friendly phrase must still be evaluated normally.
    assert is_non_learning_message("حبيبي انت")
    assert is_non_learning_message("ياخوي")
    assert is_non_learning_message("لا عنجد")
    assert not is_non_learning_message("عشان تسيطر على ثرواتها ياخوي")

    print("PASS: Tutor payload validation, social-message guard, and conversation history")


if __name__ == "__main__":
    run_tests()
