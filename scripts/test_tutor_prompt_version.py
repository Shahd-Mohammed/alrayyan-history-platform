"""Regression check for the AI tutor prompt-version column size."""

from alrayyan.models import TutorMessage


def run_tests():
    column = TutorMessage.__table__.columns["prompt_version"]
    prompt_version = "tutor-v9-palestinian-warm-teaching"
    assert len(prompt_version) == 34
    assert column.type.length >= len(prompt_version)
    print("PASS: AI tutor prompt-version identifiers fit the database model")


if __name__ == "__main__":
    run_tests()
