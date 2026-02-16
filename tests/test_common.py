from __future__ import annotations

import unittest

from opencode_agent_sdk.common import Policy, PolicyViolation, extract_text


class PolicyTests(unittest.TestCase):
    def test_policy_blocks_dangerous_bash_command(self) -> None:
        policy = Policy()
        with self.assertRaises(PolicyViolation):
            policy.check_tool_call("bash", {"command": "rm -rf /tmp/example"})

    def test_policy_blocks_sensitive_file_path(self) -> None:
        policy = Policy()
        with self.assertRaises(PolicyViolation):
            policy.check_tool_call("read", {"path": "/Users/example/.env"})


class ExtractTextTests(unittest.TestCase):
    def test_extract_text_handles_mapping_and_list_fields(self) -> None:
        self.assertEqual(extract_text({"output_text": "ok"}), "ok")
        self.assertEqual(extract_text({"content": ["line1", "line2"]}), "line1\nline2")


if __name__ == "__main__":
    unittest.main()
