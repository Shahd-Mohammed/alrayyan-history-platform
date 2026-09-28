from alrayyan.services.challenge_engine import (
    calculate_award,
    choose_next_difficulty,
)


def run_tests():
    beginner = calculate_award("beginner", True, 0, 0)
    assert beginner["score"] == 100
    assert beginner["xp"] == 10
    assert beginner["new_combo"] == 1

    hinted = calculate_award("medium", True, 2, 2)
    assert hinted["score"] < 150
    assert hinted["xp"] < 15

    wrong = calculate_award("advanced", False, 0, 4)
    assert wrong == {"score": 0, "xp": 0, "new_combo": 0}

    assert choose_next_difficulty("medium", True, 0, 2) == "advanced"
    assert choose_next_difficulty("advanced", False, 1, 0) == "medium"
    assert choose_next_difficulty("beginner", False, 2, 0) == "beginner"

    print("PASS: Challenge scoring and adaptive difficulty")


if __name__ == "__main__":
    run_tests()
