from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from replayrail import ReplayRail, new_event_from_dict, new_event_to_dict

"""
Conceptual example only.

ReplayRail does not implement database outbox storage.
Your application owns the transaction, table, worker, and retry policy.
"""


def app_owned_transaction() -> Any:
    raise NotImplementedError("provided by your application")


def save_ticket_item(*_args: Any, **_kwargs: Any) -> None:
    raise NotImplementedError("provided by your application")


def save_outbox_event(_data: dict[str, Any]) -> None:
    raise NotImplementedError("provided by your application")


def claim_pending_outbox_events() -> Iterable[dict[str, Any]]:
    raise NotImplementedError("provided by your application")


def mark_outbox_event_published(_event_id: str, *, stream_id: str) -> None:
    raise NotImplementedError("provided by your application")


async def write_business_change_and_outbox_event(
    rail: ReplayRail,
    *,
    ticket_id: str,
    item_id: str,
    user_id: str,
) -> None:
    event = rail.prepare_event(
        channel=f"ticket:{ticket_id}",
        event_type="ticket.item.added",
        payload={"item_id": item_id},
        actor={"type": "user", "id": user_id},
        metadata={"source": "example"},
    )
    data = new_event_to_dict(event)

    with app_owned_transaction():
        save_ticket_item(ticket_id=ticket_id, item_id=item_id)
        save_outbox_event(data)


async def publish_claimed_outbox_events(rail: ReplayRail) -> None:
    for data in claim_pending_outbox_events():
        event = new_event_from_dict(data)
        published = await rail.publish_event(event)
        mark_outbox_event_published(event.event_id, stream_id=published.id)
