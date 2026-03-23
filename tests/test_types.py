from __future__ import annotations
import unittest
from opencode_agent_sdk.types import ResultMessage, Usage

class TestTypes(unittest.TestCase):
    def test_result_message_usage_robustness(self):
        # Testing the new Usage class integration
        usage = Usage(input_tokens=10, output_tokens=20)
        msg = ResultMessage(usage=usage, total_cost_usd=0.01)
        
        self.assertEqual(msg.usage.input_tokens, 10)
        self.assertEqual(msg.usage.output_tokens, 20)
        self.assertEqual(msg.total_cost_usd, 0.01)

    def test_usage_default_values(self):
        usage = Usage()
        self.assertEqual(usage.input_tokens, 0)
        self.assertEqual(usage.output_tokens, 0)
        self.assertIsNone(usage.cache_read_input_tokens)

if __name__ == "__main__":
    unittest.main()
