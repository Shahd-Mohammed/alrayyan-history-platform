"""Unit tests for advanced worksheet question configuration and grading."""

from types import SimpleNamespace

from alrayyan.services.question_interactions import (
    build_config,
    dump_config,
    encode_submission,
    grade_interaction,
)


def question(question_type, config):
    return SimpleNamespace(question_type=question_type, interaction_config=dump_config(config))


config, errors = build_config("multiple_select", ["اقتصادي", "سياسي", "طبيعي"], "اقتصادي | سياسي")
assert not errors
correct, ratio = grade_interaction(question("multiple_select", config), encode_submission("multiple_select", ["سياسي", "اقتصادي"]))
assert correct and ratio == 1.0

config, errors = build_config("ordering", ["الأول", "الثاني", "الثالث"], "")
assert not errors
correct, ratio = grade_interaction(question("ordering", config), encode_submission("ordering", ["الأول", "الثالث", "الثاني"]))
assert not correct and 0 < ratio < 1

config, errors = build_config("matching", ["حدث أ | 1914", "حدث ب | 1917"], "")
assert not errors
correct, ratio = grade_interaction(question("matching", config), encode_submission("matching", ["حدث أ|||1914", "حدث ب|||1917"]))
assert correct and ratio == 1.0

print("PASS: multiple-select, ordering, and matching grading")
