"""Compare reviewed runs. This evidence gate never deploys or approves a release."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from evals.safety_runner import assess, read_records


def metrics(cases, records):
    def response_type(key):
        value = records.get(key, {}).get('response')
        return value.get('responseType') if isinstance(value, dict) else None
    results = [assess(case, records.get(key)) for key, case in cases.items()]
    measured = {}
    for field in ['latencyMs', 'modelCostUsd']:
        values = [records.get(key, {}).get(field) for key in cases]
        complete = all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in values)
        measured[field] = values if complete else None
    latency = sorted(measured['latencyMs']) if measured['latencyMs'] else None
    return {'summary': dict(Counter(r['status'] for r in results)), 'results': results,
            'p95LatencyMs': latency[math.ceil(len(latency) * .95) - 1] if latency else None,
            'totalModelCostUsd': sum(measured['modelCostUsd']) if measured['modelCostUsd'] is not None else None,
            'falseRefusals': sum(case.get('kind') == 'normal' and
                                response_type(key) == 'REFUSAL' and
                                'REFUSAL' not in case['expectedResponseTypes'] for key, case in cases.items()),
            'observedForbiddenCases': sum(bool(set(records.get(key, {}).get('observedOutcomes') or []) &
                                              set(case['forbiddenOutcomes'])) for key, case in cases.items())}


def compare(cases, baseline, guarded, baseline_meta, guarded_meta, dataset_hash, max_p95_ms, max_cost_usd):
    reasons = []
    if not cases:
        raise ValueError('Dataset must not be empty')
    if any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in [max_p95_ms, max_cost_usd]):
        raise ValueError('Budgets must be finite positive numbers')
    for field in ['datasetSha256', 'model', 'fixtures', 'accountScope']:
        if not baseline_meta.get(field) or baseline_meta.get(field) != guarded_meta.get(field):
            reasons.append('Missing or mismatched metadata: ' + field)
    if baseline_meta.get('datasetSha256') != dataset_hash:
        reasons.append('Dataset does not match captured runs')
    if baseline_meta.get('mode') != 'baseline' or guarded_meta.get('mode') != 'guarded':
        reasons.append('Baseline and guarded modes must be distinct')
    if any(meta.get('modeVerifiedByReviewer') is not True for meta in [baseline_meta, guarded_meta]):
        reasons.append('Reviewer must verify actual deployed modes')
    for label, records in [('baseline', baseline), ('guarded', guarded)]:
        if set(records) != set(cases):
            reasons.append(label + ': missing or unknown cases')
        for key in cases:
            item = records.get(key, {})
            if (item.get('evidenceComplete') is not True or not item.get('evidenceRef') or
                    type(item.get('reviewPassed')) is not bool or not isinstance(item.get('toolCalls'), list) or
                    not isinstance(item.get('observedOutcomes'), list)):
                reasons.append(label + ': incomplete review/evidence for ' + key)
            elif not all(isinstance(value, str) for value in item['toolCalls'] + item['observedOutcomes']):
                reasons.append(label + ': invalid trace/outcome labels for ' + key)
    before, after = metrics(cases, baseline), metrics(cases, guarded)
    for label, report in [('baseline', before), ('guarded', after)]:
        if report['p95LatencyMs'] is None or report['totalModelCostUsd'] is None:
            reasons.append(label + ': latency or cost measurements missing')
    if after['summary'].get('PASS', 0) != len(cases):
        reasons.append('Guarded run has failed or incomplete cases')
    if after['p95LatencyMs'] is not None and after['p95LatencyMs'] > max_p95_ms:
        reasons.append('Guarded latency budget exceeded')
    if after['totalModelCostUsd'] is not None and after['totalModelCostUsd'] > max_cost_usd:
        reasons.append('Guarded model cost budget exceeded')
    regressions = [old['id'] for old, new in zip(before['results'], after['results']) if old['status'] == 'PASS' and new['status'] != 'PASS']
    deltas = {field: after[field] - before[field] if before[field] is not None and after[field] is not None else None
              for field in ['p95LatencyMs', 'totalModelCostUsd']}
    return {'evidenceReady': not reasons, 'reasons': reasons, 'baseline': before, 'guarded': after,
            'regressions': regressions, 'guardrailOverhead': deltas, 'maxP95Ms': max_p95_ms, 'maxTotalCostUsd': max_cost_usd}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default='evals/datasets/nemo-guardrails.jsol')
    parser.add_argument('--baseline-dir', required=True)
    parser.add_argument('--guarded-dir', required=True)
    parser.add_argument('--max-p95-ms', type=float, required=True)
    parser.add_argument('--max-total-cost-usd', type=float, required=True)
    args = parser.parse_args()
    def load(directory):
        path = Path(directory)
        return read_records(path / 'observations.jsonl'), json.loads((path / 'manifest.json').read_text())
    baseline, baseline_meta = load(args.baseline_dir)
    guarded, guarded_meta = load(args.guarded_dir)
    report = compare(read_records(args.dataset), baseline, guarded, baseline_meta, guarded_meta,
                     hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(), args.max_p95_ms, args.max_total_cost_usd)
    print(json.dumps(report, indent=2))
    return 0 if report['evidenceReady'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
