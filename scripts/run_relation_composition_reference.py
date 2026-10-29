#!/usr/bin/env python3
"""Exploratory finite reference: paired hazard/visibility sequences and a fixed receiver.

No learned causal structure, HUGSIM, real driving, or independent blind test.
The two calibration cases and two held-out pairings are specified in this file.
"""
import argparse
import hashlib
import json
import os
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HORIZON = 8
HAZARD_STARTS = {"early": 2, "late": 5}
WINDOWS = {"early": (1, 2), "late": (4, 5)}


def sequences(hazard_start, window, horizon=HORIZON):
    return ([int(t >= hazard_start) for t in range(horizon)],
            [int(t in window) for t in range(horizon)])


def reference(hazard, visible, deadline):
    """Fixed receiver acts on the first visible active hazard, by a deadline."""
    if len(hazard) != len(visible) or type(deadline) is not int or not 0 <= deadline < len(hazard):
        return None
    acted = False
    for t in range(deadline + 1):
        if hazard[t] and visible[t]:
            acted = True
    return acted


def relation_predict(hazard, visible, deadline):
    if len(hazard) != len(visible) or type(deadline) is not int or not 0 <= deadline < len(hazard):
        return None
    return any(h and v for h, v in zip(hazard[:deadline + 1], visible[:deadline + 1]))


def execute():
    cases = []
    for split, pairings in [("calibration", [("early", "early"), ("late", "late")]),
                            ("heldout", [("early", "late"), ("late", "early")])]:
        for h, v in pairings:
            hazard, visible = sequences(HAZARD_STARTS[h], WINDOWS[v])
            deadline = HAZARD_STARTS[h] + 1
            cases.append(dict(split=split, hazard=h, visibility=v, hazard_sequence=hazard,
                              visibility_sequence=visible, deadline=deadline,
                              observed_joint=[a * b for a, b in zip(hazard, visible)],
                              reference=reference(hazard, visible, deadline),
                              relation_prediction=relation_predict(hazard, visible, deadline)))
    # Baseline learns each hazard's outcome from aligned cases, ignoring window timing.
    # Both visibility windows have equal total available frames.
    lookup = {(r['hazard'], sum(r['visibility_sequence'])): r['reference']
              for r in cases if r['split'] == 'calibration'}
    for r in cases:
        r['marginal_prediction'] = lookup[(r['hazard'], sum(r['visibility_sequence']))]
    def multiset(split, field):
        return Counter(tuple(r[field]) for r in cases if r['split'] == split)
    assert multiset('calibration', 'hazard_sequence') == multiset('heldout', 'hazard_sequence')
    assert multiset('calibration', 'visibility_sequence') == multiset('heldout', 'visibility_sequence')
    heldout = [r for r in cases if r['split'] == 'heldout']
    return {'scope': 'exploratory designed reference; no HUGSIM, real AD or blind validation',
            'horizon': HORIZON, 'cases': cases,
            'checks': {'equal_hazard_sequence_multisets': True,
                       'equal_visibility_sequence_multisets': True,
                       'calibration_successes': sum(r['reference'] for r in cases if r['split']=='calibration'),
                       'heldout_successes': sum(r['reference'] for r in heldout),
                       'heldout_relation_correct': sum(r['reference']==r['relation_prediction'] for r in heldout),
                       'heldout_marginal_correct': sum(r['reference']==r['marginal_prediction'] for r in heldout)},
            'limitations': ['the joint rule and receiver are predefined, not discovered',
                            'two constructed heldout pairings are not independent real samples',
                            'response by a synthetic deadline is not driving safety',
                            'the predictor observes the full declared hazard sequence and deadline']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    environment = {'role': 'exploratory synthetic relation-composition reference',
                   'started_utc': datetime.now(timezone.utc).isoformat(),
                   'host': platform.node(), 'working_directory': os.getcwd(),
                   'output': str(out.resolve()), 'python': platform.python_version(),
                   'pid': os.getpid(), 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
    (out / 'status.json').write_text(json.dumps({'status': 'running'}) + '\n')
    print(json.dumps(environment), flush=True)
    try:
        result = execute()
        result['script_sha256'] = environment['script_sha256']
        (out / 'summary.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        (out / 'status.json').write_text(json.dumps({'status': 'complete'}) + '\n')
        print(json.dumps(result['checks'], indent=2), flush=True)
    except Exception as error:
        (out / 'status.json').write_text(json.dumps({'status': 'failed', 'error': str(error)}) + '\n')
        raise


if __name__ == '__main__':
    main()
