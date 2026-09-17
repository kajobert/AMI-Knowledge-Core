from ami_knowledge_core.identity import canonical_json, sha256_text, stable_id


def test_stable_id_is_order_independent_for_mappings() -> None:
    left = stable_id("claim", {"a": 1, "b": 2})
    right = stable_id("claim", {"b": 2, "a": 1})
    assert left == right


def test_stable_id_changes_when_semantics_change() -> None:
    assert stable_id("claim", "alpha") != stable_id("claim", "beta")


def test_canonical_json_is_compact_and_stable() -> None:
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_sha256_text_is_deterministic() -> None:
    assert sha256_text("AMI") == sha256_text("AMI")
    assert len(sha256_text("AMI")) == 64
