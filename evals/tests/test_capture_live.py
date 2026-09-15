import unittest
import subprocess
import sys
from evals.capture_live import capture


class CaptureTests(unittest.TestCase):
    def test_cli_requires_explicit_live_authorization(self):
        result = subprocess.run([sys.executable, '-m', 'evals.capture_live', '--mode', 'guarded',
            '--model', 'test', '--fixtures', 'test', '--account-scope', 'synthetic', '--out-dir', '/tmp/unused-evaluation'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--run-live and --confirm-synthetic', result.stderr)

    def test_success_does_not_manufacture_safety_evidence(self):
        value = capture({'id': 'one', 'prompt': 'Bread'}, lambda _: (200, {'responseType': 'CART_PROPOSAL'}))
        self.assertFalse(value['evidenceComplete'])
        for field in ['toolCalls', 'observedOutcomes', 'reviewPassed', 'modelCostUsd']:
            self.assertIsNone(value[field])

    def test_failure_records_no_raw_diagnostics(self):
        def failing(_):
            raise RuntimeError('private token')
        value = capture({'id': 'one', 'prompt': 'Bread'}, failing)
        self.assertIsNone(value['response'])
        self.assertNotIn('private token', str(value))
