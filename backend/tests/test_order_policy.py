import unittest

from app.domain.order_policy import can_cancel_order, can_close_cycle, can_edit_line, can_transition_fulfilment, inventory_recovery_target


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

    def test_cancellation_is_blocked_after_collection(self):
        self.assertTrue(can_cancel_order(order_status="PREPARING",cash_collections=0,item_collections=0))
        self.assertFalse(can_cancel_order(order_status="READY_FOR_PICKUP",cash_collections=1,item_collections=0))
        self.assertFalse(can_cancel_order(order_status="READY_FOR_PICKUP",cash_collections=0,item_collections=1))
        self.assertFalse(can_cancel_order(order_status="FULFILLED",cash_collections=0,item_collections=0))

    def test_reset_recovers_the_correct_inventory_bucket(self):
        self.assertEqual(inventory_recovery_target("AWAITING_COMMITMENT"),"RESERVED")
        self.assertEqual(inventory_recovery_target("ORDER_PLACED"),"AVAILABLE")
        self.assertEqual(inventory_recovery_target("PREPARING"),"AVAILABLE")
        self.assertIsNone(inventory_recovery_target("FULFILLED"))


if __name__ == "__main__":
    unittest.main()
