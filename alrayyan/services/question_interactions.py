"""Validation and grading shared by interactive worksheet question types."""

import json


INTERACTIVE_TYPES = {"multiple_select", "matching", "ordering"}


def normalize(value):
    return " ".join((value or "").strip().casefold().split())


def build_config(question_type, choices, correct_answer):
    """Return a serializable config and teacher-facing validation errors."""
    errors = []
    config = {}

    if question_type == "multiple_select":
        correct = [item.strip() for item in correct_answer.split("|") if item.strip()]
        normalized_choices = {normalize(item) for item in choices}
        if len(choices) < 2:
            errors.append("الاختيارات المتعددة تحتاج خيارين على الأقل.")
        if not correct:
            errors.append("افصلي الإجابات الصحيحة بعلامة | في حقل الإجابة الصحيحة.")
        if any(normalize(item) not in normalized_choices for item in correct):
            errors.append("كل إجابة صحيحة يجب أن تطابق أحد الخيارات.")
        config = {"correct_values": correct}

    elif question_type == "ordering":
        if len(choices) < 2:
            errors.append("سؤال الترتيب يحتاج عنصرين على الأقل، بالترتيب الصحيح.")
        config = {
            "items": choices,
            "display_items": list(reversed(choices)),
            "correct_order": choices,
        }

    elif question_type == "matching":
        pairs = []
        for line in choices:
            parts = [part.strip() for part in line.split("|", 1)]
            if len(parts) != 2 or not all(parts):
                errors.append("اكتبي كل زوج مطابقة بهذا الشكل: المفهوم | الإجابة")
                break
            pairs.append({"left": parts[0], "right": parts[1]})
        if len(pairs) < 2:
            errors.append("سؤال المطابقة يحتاج زوجين على الأقل.")
        config = {"pairs": pairs}

    return config, errors


def dump_config(config):
    return json.dumps(config or {}, ensure_ascii=False)


def load_config(question):
    try:
        return json.loads(question.interaction_config or "{}")
    except (TypeError, ValueError):
        return {}


def encode_submission(question_type, submitted_values):
    values = [str(value).strip() for value in submitted_values if str(value).strip()]
    if question_type in {"multiple_select", "ordering", "matching"}:
        return json.dumps(values, ensure_ascii=False)
    return values[0] if values else ""


def decode_submission(question_type, stored_value):
    if question_type in {"multiple_select", "ordering", "matching"}:
        try:
            payload = json.loads(stored_value or "[]")
            return payload if isinstance(payload, list) else []
        except (TypeError, ValueError):
            return []
    return stored_value or ""


def grade_interaction(question, stored_value):
    """Return (is_correct, awarded_ratio) for an auto-graded interaction."""
    config = load_config(question)
    submitted = decode_submission(question.question_type, stored_value)

    if question.question_type == "multiple_select":
        expected = {normalize(item) for item in config.get("correct_values", [])}
        actual = {normalize(item) for item in submitted}
        correct = bool(expected) and actual == expected
        return correct, 1.0 if correct else 0.0

    if question.question_type == "ordering":
        expected = [normalize(item) for item in config.get("correct_order", [])]
        actual = [normalize(item) for item in submitted]
        correct = bool(expected) and actual == expected
        if not expected:
            return False, 0.0
        matches = sum(1 for index, item in enumerate(actual[: len(expected)]) if item == expected[index])
        return correct, matches / len(expected)

    if question.question_type == "matching":
        expected = {
            normalize(pair.get("left")): normalize(pair.get("right"))
            for pair in config.get("pairs", [])
        }
        actual = {}
        for item in submitted:
            left, separator, right = item.partition("|||")
            if separator:
                actual[normalize(left)] = normalize(right)
        correct_count = sum(actual.get(left) == right for left, right in expected.items())
        correct = bool(expected) and correct_count == len(expected)
        return correct, (correct_count / len(expected)) if expected else 0.0

    return False, 0.0
