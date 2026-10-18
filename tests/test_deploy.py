import unittest

from src.deploy_worker import build_script_body, derive_secrets


class DeployTests(unittest.TestCase):
    def test_secrets_stay_stable_and_do_not_repeat_the_password(self):
        feedback, admin = derive_secrets("gmail-sovellus-salasana")
        self.assertEqual((feedback, admin), derive_secrets("gmail-sovellus-salasana"))
        self.assertNotEqual(feedback, admin)
        self.assertEqual(len(feedback), 64)
        self.assertNotIn("gmail", feedback)
        self.assertNotIn("salasana", admin)

    def test_script_upload_contains_the_storage_binding(self):
        body, boundary = build_script_body(b"export default {}", "kv-123")
        text = body.decode()
        self.assertIn("kv-123", text)
        self.assertIn("index.js", text)
        self.assertIn(boundary, text)
        self.assertTrue(text.endswith(f"--{boundary}--\r\n"))
