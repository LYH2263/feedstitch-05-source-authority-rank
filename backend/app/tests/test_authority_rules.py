from app.modules.source_authority_rank import (
    compare_authority,
    conflict_reason,
    decide_divergence,
)


def test_compare_authority():
    assert compare_authority(100, 10) == "higher"
    assert compare_authority(10, 100) == "lower"
    assert compare_authority(50, 50) == "equal"
    assert compare_authority(None, 10) == "unknown"
    assert compare_authority(10, None) == "unknown"


def test_decide_divergence():
    assert decide_divergence(100, 10) == "authority_override"
    assert decide_divergence(10, 100) == "authority_lost"
    assert decide_divergence(50, 50) == "conflict"
    assert decide_divergence(None, 10) == "conflict"
    assert decide_divergence(10, None) == "conflict"


def test_conflict_reasons():
    assert conflict_reason(10, 100, "authority_lost") == "authority_lost"
    assert conflict_reason(100, 100) == "authority_equal"
    assert conflict_reason(None, 100) == "authority_unknown"
    assert conflict_reason(10, 100) == "non_key_field_mismatch"
