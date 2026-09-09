import unittest

from app.domain.order_policy import can_close_cycle, can_edit_line, can_transition_fulfilment


class OrderPolicyTests(unittest.TestCase):
    def test_member_edits_only_own_line(self):
        self.assertTrue(can_edit_line(app_role="MEMBER",member_role="MEMBER",actor_id="a",owner_id="a"))
        self.assertFalse(can_edit_line(app_role="MEMBER",member_role="MEMBER",actor_id="a",owner_id="b"))

    def test_admin_and_coordinator_manage_shared_cart(self):
        self.assertTrue(can_edit_line(app_role="ADMIN",member_role="MEMBER",actor_id="a",owner_id="b"))
        self.assertTrue(can_edit_line(app_role="MEMBER",member_role="COORDINATOR",actor_id="a",owner_id="b"))
        self.assertTrue(can_close_cycle(app_role="ADMIN",member_role="MEMBER"))
        self.assertTrue(can_close_cycle(app_role="MEMBER",member_role="COORDINATOR"))

    def test_retail_member_cannot_close_and_invalid_transitions_fail(self):
        self.assertFalse(can_close_cycle(app_role="MEMBER",member_role="MEMBER"))
        self.assertTrue(can_transition_fulfilment("ORDER_PLACED","PREPARING"))
        self.assertFalse(can_transition_fulfilment("ORDER_PLACED","FULFILLED"))
        self.assertFalse(can_transition_fulfilment("FULFILLED","PREPARING"))


if __name__ == "__main__":
    unittest.main()
