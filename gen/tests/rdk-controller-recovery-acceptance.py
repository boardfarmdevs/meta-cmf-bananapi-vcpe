#!/usr/bin/env python3
"""Run inside the RDK root VM; preserve all services except em_ctrl."""

import argparse
from copy import deepcopy
import datetime as dt
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def sibling(name):
    specification = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


readiness = sibling('room-final-readiness')
audit = sibling('room-feature-guest-audit')


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def split_identity(identity):
    unchanged = deepcopy(identity)
    if not identity.get('medium') or len(identity) < 6:
        raise RuntimeError('incomplete native identity')
    services = {}
    for block in identity['bpibroadband']['services'].strip().split('\n\n'):
        service = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        services[service['Id']] = service
    controller = services.pop('em_ctrl.service')
    if controller.get('ActiveState') != 'active' or int(controller.get('MainPID', '0')) <= 1:
        raise RuntimeError('controller is not active')
    unchanged['bpibroadband']['services'] = services
    return unchanged, controller


def evaluate(current, state, native_bsses, expected_channels=None, after=0):
    optimizer = current.get('optimizer') or {}
    health = current.get('health') or {}
    fleet = optimizer.get('fleet') or {}
    clients = current.get('network', {}).get('clients', [])
    decisions = optimizer.get('client_decisions') or []
    now = dt.datetime.now(dt.timezone.utc)

    def fresh(timestamp):
        observed = readiness.parse_timestamp(timestamp)
        return observed.timestamp() > after and 0 <= (now - observed).total_seconds() <= 30

    rows = native_bsses.get('bsses', [])
    channels = {row['bssid']: row.get('channel') for row in rows}
    native_channels = len(rows) == len(channels) == 30 and all(
        type(channel) is int and channel > 0 for channel in channels.values())
    scores = [(row.get('sta_mac'), score.get('bssid')) for row in decisions
              for score in row.get('scores', [])]
    cache_age = optimizer.get('candidate_selection', {}).get('maximum_cache_age_seconds')
    cache_expired = after == 0 or (isinstance(cache_age, (float, int))
        and not isinstance(cache_age, bool) and math.isfinite(cache_age)
        and 0 < cache_age <= 30 and time.time() - after > cache_age)
    convergence = readiness.convergence_state(optimizer, clients)
    checks = {
        'native_channels_30': native_channels and (expected_channels is None or channels == expected_channels),
        'fresh_native_clients_20': len(clients) == 20 and all(
            fresh(client['metric_observed_at']) and (client.get('rcpi') or 0) > 0
            and client.get('measurement_source') == 'associated_sta_link_metrics' for client in clients),
        'native_candidates_80': fleet.get('candidate_measurements') == 80
            and fleet.get('measurement_complete') is True
            and fleet.get('clients_checked') == fleet.get('clients_evaluated') == 20
            and len(scores) == len(set(scores)) == 80
            and all(len(row.get('scores', [])) == 4 for row in decisions) and cache_expired,
        'default_health': health.get('healthy') is True and readiness.default_roster(health, clients, state),
        'default_idle': state['playback']['status'] == 'paused' and state['playback']['time_ms'] == 0
            and not state['lease']['held'] and not state['fault'] and not state['recording']['active'],
        'steering_budget': readiness.default_steering_budget(optimizer),
        'current_epoch': current['environment_epoch'] == state['environment_epoch'] == optimizer.get('environment_epoch'),
        'fresh_evaluation': fresh(optimizer['evaluated_at']),
        'policy_converged': convergence['policy_converged'],
    }
    return checks, channels


def wait_ready(args, phase, expected_channels=None, after=0, action_started=None):
    started = time.monotonic()
    stable_since = None
    milestones = {}
    with (args.output / (phase + '.jsonl')).open('w') as journal:
        while time.monotonic() - started < args.timeout:
            sample = {'at': time.time()}
            try:
                current = fetch(args.room_url.rstrip('/') + '/api/demo/current')
                state = fetch(args.room_url.rstrip('/') + '/api/demo/interactions')
                bsses = fetch(args.controller_url.rstrip('/') + '/api/v1/bsses')
                checks, channels = evaluate(current, state, bsses, expected_channels, after)
                sample['checks'] = checks
                sample['elapsed_seconds'] = time.monotonic() - (action_started or started)
                for name, passed in checks.items():
                    if passed:
                        milestones.setdefault(name, sample['elapsed_seconds'])
                sample['milestones_seconds'] = milestones
                for name, value in [('current', current), ('interactions', state), ('bsses', bsses)]:
                    (args.output / (phase + '-' + name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
                if all(checks.values()):
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 5:
                        return {'channels': channels, 'milestones_seconds': milestones,
                                'stable_ready_seconds': sample['elapsed_seconds']}
                else:
                    stable_since = None
            except (OSError, ValueError, KeyError, TypeError) as error:
                sample['error'] = str(error)
                stable_since = None
            finally:
                journal.write(json.dumps(sample) + '\n')
                journal.flush()
            time.sleep(1)
    raise RuntimeError(phase + ': recovery did not satisfy all checks within timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yes-change-lab', action='store_true')
    parser.add_argument('--mode', choices=('restart', 'kill'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--room-url', default='http://127.0.0.1:8891')
    parser.add_argument('--controller-url', default='http://127.0.0.1:8888')
    args = parser.parse_args()
    if os.geteuid() or not args.yes_change_lab:
        parser.error('requires RDK root VM, root and --yes-change-lab')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be finite and positive')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'mode': args.mode, 'started_at': time.time(),
              'timing_scope': 'first sampled evidence from action start; full candidate gate waits out pre-action cache'}
    try:
        report['before'] = wait_ready(args, 'before')
        report['identity_before'] = audit.identity('rdk')
        unchanged_before, controller_before = split_identity(report['identity_before'])
        action = ['systemctl', 'restart', 'em_ctrl.service'] if args.mode == 'restart' else [
            'systemctl', 'kill', '--kill-who=main', '--signal=SIGKILL', 'em_ctrl.service']
        report['action'] = ['lxc', 'exec', 'bpibroadband', '--', *action]
        action_started = time.monotonic()
        report['action_started_at'] = time.time()
        subprocess.run(report['action'], check=True, capture_output=True, text=True, timeout=60)
        report['action_command_seconds'] = time.monotonic() - action_started
        report['after'] = wait_ready(args, 'after', report['before']['channels'],
                                     report['action_started_at'], action_started)
        report['identity_after'] = audit.identity('rdk')
        unchanged_after, controller_after = split_identity(report['identity_after'])
        if unchanged_before != unchanged_after:
            raise RuntimeError('agent/native/container/medium identity changed')
        if controller_before['MainPID'] == controller_after['MainPID']:
            raise RuntimeError('controller PID did not change')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        try:
            report['identity_after'] = audit.identity('rdk')
        except Exception as identity_error:
            report['identity_error'] = str(identity_error)
    finally:
        report['finished_at'] = time.time()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
