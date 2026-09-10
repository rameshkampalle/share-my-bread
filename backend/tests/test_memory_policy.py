import unittest

from app.domain.memory_policy import scoped_user_id


class MemoryPolicyTests(unittest.TestCase):
    def test_mem0_identity_is_namespaced(self):
        self.assertEqual(scoped_user_id("abc"), "share-my-bread:abc")
        self.assertNotEqual(scoped_user_id("abc"), scoped_user_id("def"))


if __name__ == "__main__":
    unittest.main()
