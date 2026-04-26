from __future__ import annotations

from opentower_cli.intent_parser import parse_objective
from opentower_cli.security_agent import assess_intent


def test_assess_intent_requires_confirmation_for_delete_user() -> None:
    intent = parse_objective("delete user dev01")
    assessment = assess_intent(intent)

    assert assessment.decision == "confirm"
    assert assessment.risk_level == "high"
    assert assessment.requires_reason is True


def test_assess_intent_blocks_root_delete_request() -> None:
    intent = parse_objective("删除 /")
    assessment = assess_intent(intent)

    assert assessment.decision == "block"
    assert assessment.risk_level == "critical"


def test_assess_intent_requires_confirmation_for_create_user() -> None:
    intent = parse_objective("create user dev01")
    assessment = assess_intent(intent)

    assert assessment.decision == "confirm"
    assert assessment.risk_level == "high"
    assert assessment.requires_reason is True


def test_assess_intent_requires_confirmation_for_add_user_to_group() -> None:
    intent = parse_objective("将用户 dev01 加入 sudo 组")
    assessment = assess_intent(intent)

    assert assessment.decision == "confirm"
    assert assessment.risk_level == "high"
    assert assessment.requires_reason is True
