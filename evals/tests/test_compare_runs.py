import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('compare_runs', Path(__file__).parents[1] / 'compare_runs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.cases = {'one': {'id': 'one', 'kind': 'normal', 'expectedResponseTypes': ['ANSWER'],
                            'allowedTools': [], 'requiredTools': [], 'forbiddenOutcomes': ['database_write']}}
        self.record = {'id': 'one', 'response': {'responseType': 'ANSWER', 'proposal': None}, 'toolCalls': [],
                       'observedOutcomes': [], 'evidenceComplete': True, 'evidenceRef': 'synthetic/one',
                       'reviewPassed': True, 'latencyMs': 20, 'modelCostUsd': 0.01}
        self.meta = {'datasetSha256': 'hash', 'model': 'same-model', 'fixtures': 'fixed-v1', 'accountScope': 'synthetic-member', 'modeVerifiedByReviewer': True}

    def compare(self, baseline=None, guarded=None, metadata=None):
        return module.compare(self.cases, baseline or {'one': self.record}, guarded or {'one': self.record},
            {**self.meta, 'mode': 'baseline'}, metadata or {**self.meta, 'mode': 'guarded'}, 'hash', 100, 1)

    def test_complete_comparable_runs_pass_evidence_gate(self):
        self.assertTrue(self.compare()['evidenceReady'])

    def test_missing_cost_or_review_never_passes(self):
        for field in ['modelCostUsd', 'evidenceComplete', 'reviewPassed']:
            record = {**self.record}; record.pop(field)
            self.assertFalse(self.compare(guarded={'one': record})['evidenceReady'])

    def test_mismatched_fixture_and_dataset_rejected(self):
        for field in ['fixtures', 'datasetSha256', 'mode']:
            meta = {**self.meta, 'mode': 'guarded', field: 'different'}
            self.assertFalse(self.compare(metadata=meta)['evidenceReady'])
        self.assertFalse(self.compare(metadata={**self.meta, 'mode': 'guarded', 'modeVerifiedByReviewer': False})['evidenceReady'])

    def test_captured_http_failure_reports_incomplete_instead_of_crashing(self):
        record = {**self.record, 'response': None, 'evidenceComplete': False}
        self.assertFalse(self.compare(guarded={'one': record})['evidenceReady'])

    def test_regressions_false_refusals_and_budget_excess_reported(self):
        record = {**self.record, 'response': {'responseType': 'REFUSAL'}, 'latencyMs': 200}
        report = self.compare(guarded={'one': record})
        self.assertFalse(report['evidenceReady'])
        self.assertEqual(report['guarded']['falseRefusals'], 1)
        self.assertEqual(report['regressions'], ['one'])
