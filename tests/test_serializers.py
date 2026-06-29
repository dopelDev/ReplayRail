import pytest

from replayrail.errors import SerializationError
from replayrail.serializers import JsonSerializer


def test_json_serializer_dumps_and_loads_dict() -> None:
    serializer = JsonSerializer()

    assert serializer.loads(serializer.dumps({"order_id": "ord_123"})) == {"order_id": "ord_123"}


def test_non_serializable_payload_raises() -> None:
    serializer = JsonSerializer()

    with pytest.raises(SerializationError):
        serializer.dumps({"bad": object()})
