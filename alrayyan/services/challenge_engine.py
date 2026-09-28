DIFFICULTIES = ("beginner", "medium", "advanced")

BASE_SCORE = {
    "beginner": 100,
    "medium": 150,
    "advanced": 220,
}

BASE_XP = {
    "beginner": 10,
    "medium": 15,
    "advanced": 22,
}

HINT_MULTIPLIER = {
    0: 1.0,
    1: 0.8,
    2: 0.6,
}


def calculate_award(difficulty, is_correct, hints_used, combo):
    """Return deterministic score and XP for one answer."""
    if not is_correct:
        return {"score": 0, "xp": 0, "new_combo": 0}

    normalized = (
        difficulty if difficulty in DIFFICULTIES else "medium"
    )
    safe_hints = min(max(int(hints_used or 0), 0), 2)
    new_combo = combo + 1
    combo_bonus = min(max(new_combo - 1, 0) * 0.10, 0.40)
    hint_multiplier = HINT_MULTIPLIER[safe_hints]

    score = round(
        BASE_SCORE[normalized]
        * hint_multiplier
        * (1 + combo_bonus)
    )
    xp = round(BASE_XP[normalized] * hint_multiplier)

    return {"score": score, "xp": xp, "new_combo": new_combo}


def choose_next_difficulty(current, is_correct, hints_used, combo):
    """Adjust difficulty with rules that can be tested and explained."""
    current = current if current in DIFFICULTIES else "medium"
    index = DIFFICULTIES.index(current)

    if is_correct and hints_used == 0 and combo >= 2:
        return DIFFICULTIES[min(index + 1, len(DIFFICULTIES) - 1)]

    if not is_correct:
        return DIFFICULTIES[max(index - 1, 0)]

    return current
