from replayrail.errors import ReplayRailError, StoreError


def test_replayrail_error_context_defaults_to_empty_dict() -> None:
    error = ReplayRailError("x")

    assert error.context == {}


def test_store_error_preserves_context() -> None:
    error = StoreError("x", channel="ticket:1")

    assert error.context["channel"] == "ticket:1"
