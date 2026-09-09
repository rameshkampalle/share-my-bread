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
