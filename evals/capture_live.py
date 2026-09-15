"""Opt-in synthetic live capture. Never infer safety review, tool traces, or cost."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from evals.safety_runner import read_records


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def capture(case, send):
    start = time.monotonic()
    try:
        status, response = send(case['prompt'])
    except Exception:
        status, response = None, None
    return {'id': case['id'], 'response': response, 'httpStatus': status,
            'latencyMs': round((time.monotonic() - start) * 1000, 2),
            'modelCostUsd': None, 'toolCalls': None, 'observedOutcomes': None,
            'evidenceComplete': False, 'evidenceRef': None, 'reviewPassed': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live', action='store_true', help='Authorize paid calls against the configured synthetic test deployment')
    parser.add_argument('--confirm-synthetic', action='store_true')
    parser.add_argument('--dataset', default='evals/datasets/nemo-guardrails.jsol')
    parser.add_argument('--mode', choices=['baseline', 'guarded'], required=True)
    parser.add_argument('--model', required=True, help='Actual generation model/version, identical in both runs')
    parser.add_argument('--fixtures', required=True, help='Version/hash of catalogue and other fixtures')
    parser.add_argument('--account-scope', required=True, help='Synthetic account/role scope, never a token')
    parser.add_argument('--out-dir', required=True, help='New private directory; never overwritten')
    args = parser.parse_args()
    if not args.run_live or not args.confirm_synthetic:
        parser.error('Live calls require --run-live and --confirm-synthetic')
    endpoint, token = os.environ.get('EVAL_ASSISTANT_URL', ''), os.environ.get('EVAL_BEARER_TOKEN', '')
    url = urlsplit(endpoint)
    if (not token or not url.hostname or url.username or url.password or url.query or url.fragment or
            (url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}))):
        parser.error('Set EVAL_ASSISTANT_URL to HTTPS (or local HTTP) and EVAL_BEARER_TOKEN; URL credentials/query/fragment are forbidden')
    cases = read_records(args.dataset)
    if not cases:
        parser.error('Dataset must not be empty')
    directory = Path(args.out_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = {'mode': args.mode, 'datasetSha256': hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
                'model': args.model, 'fixtures': args.fixtures, 'accountScope': args.account_scope,
                'capturedAt': datetime.now(timezone.utc).isoformat(), 'modeVerifiedByReviewer': False}
    def write_private(name, content):
        with os.fdopen(os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
            output.write(content)
    write_private('manifest.json', json.dumps(manifest, indent=2))
    opener = build_opener(NoRedirect())
    def send(prompt):
        request = Request(endpoint, data=json.dumps({'message': prompt}).encode(),
                          headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        try:
            response = opener.open(request, timeout=140)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(262145)
            if len(body) > 262144:
                return response.code, None
            try:
                value = json.loads(body)
            except (ValueError, UnicodeError):
                value = None
            return response.code, value if isinstance(value, dict) else None
    with os.fdopen(os.open(directory / 'observations.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
        for case in cases.values():
            record = capture(case, send)
            output.write(json.dumps(record) + '\n')
            output.flush()
            print(case['id'] + ': captured; trace, state, cost and policy review pending', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
