import unittest

from server.username_moderation import moderate_username


class UsernameModerationTests(unittest.TestCase):
    def test_policy_normalizes_case_unicode_and_common_obfuscation(self):
        for name in ('N1gger', 'n-i-g-g-e-r', 'Ｆａｇｇｏｔ'):
            with self.subTest(name=name):
                self.assertEqual(moderate_username(name).status, 'pending')

    def test_benign_names_remain_clear(self):
        for name in ('Builder_42', 'FriendlyGamer', 'night-owl'):
            with self.subTest(name=name):
                self.assertEqual(moderate_username(name).status, 'clear')


if __name__ == '__main__':
    unittest.main()
