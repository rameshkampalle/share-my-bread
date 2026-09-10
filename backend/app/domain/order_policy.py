FULFILMENT_TRANSITIONS = {
    "ORDER_PLACED": {"PREPARING", "CANCELLED"},
    "PREPARING": {"READY_FOR_PICKUP", "CANCELLED"},
    "READY_FOR_PICKUP": {"FULFILLED", "CANCELLED"},
}


def can_edit_line(*, app_role: str, member_role: str, actor_id: str, owner_id: str) -> bool:
    return actor_id == owner_id or app_role == "ADMIN" or member_role == "COORDINATOR"


def can_close_cycle(*, app_role: str, member_role: str) -> bool:
    return app_role == "ADMIN" or member_role == "COORDINATOR"


def can_transition_fulfilment(old_status: str, new_status: str) -> bool:
    return new_status in FULFILMENT_TRANSITIONS.get(old_status, set())


def can_cancel_order(*, order_status: str, cash_collections: int, item_collections: int) -> bool:
    return (
        can_transition_fulfilment(order_status, "CANCELLED")
        and cash_collections == 0
        and item_collections == 0
    )


def inventory_recovery_target(order_status: str) -> str | None:
    if order_status == "AWAITING_COMMITMENT":
        return "RESERVED"
    if order_status in {"ORDER_PLACED", "PREPARING", "READY_FOR_PICKUP"}:
        return "AVAILABLE"
    return None
