from copy import deepcopy
import datetime as dt
import importlib.util
from pathlib import Path
import time

import pytest


specification = importlib.util.spec_from_file_location(
    'recovery', Path(__file__).with_name('rdk-controller-recovery-acceptance.py'))
recovery = importlib.util.module_from_spec(specification)
specification.loader.exec_module(recovery)


def sample():
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    stations = [f'sta_{kind}_{ordinal:02d}' for kind in ('mobile', 'static') for ordinal in range(1, 11)]
    roles = {role: {'present': True} for role in [*stations, 'gateway', *[f'extender_{ordinal}' for ordinal in range(1, 5)]]}
    roles.update({f'sta_pool_{ordinal:03d}': {'present': False} for ordinal in range(21, 101)})
    clients = [{'role': role, 'sta_mac': f'sta-{index}', 'connected_bssid': f'bss-{index}',
                'metric_observed_at': timestamp, 'rcpi': 120,
                'measurement_source': 'associated_sta_link_metrics'} for index, role in enumerate(stations)]
    decisions = [{'sta_mac': client['sta_mac'], 'source_bssid': client['connected_bssid'],
                  'current_rcpi': 120, 'scores': [{'bssid': f'candidate-{index}'} for index in range(4)]}
                 for client in clients]
    current = {'health': {'healthy': True, 'api_total': 20}, 'network': {'clients': clients},
               'environment_epoch': 'epoch', 'optimizer': {'environment_epoch': 'epoch',
               'evaluated_at': timestamp, 'client_decisions': decisions, 'maximum_actions': None,
               'steering_safety': {'enabled': True}, 'candidate_selection': {'maximum_cache_age_seconds': 30},
               'fleet': {'candidate_measurements': 80, 'measurement_complete': True,
                         'clients_checked': 20, 'clients_evaluated': 20, 'converged': True}}}
    state = {'roles': roles, 'selected_world': 'home-five-agent--private-client-room-walk',
             'pool_clients': 100, 'expected_online_clients': 20, 'environment_epoch': 'epoch',
             'playback': {'status': 'paused', 'time_ms': 0}, 'lease': {'held': False},
             'fault': None, 'recording': {'active': False}}
    bsses = {'bsses': [{'bssid': f'bss-{index}', 'channel': 6} for index in range(30)]}
    return current, state, bsses


def test_complete_recovery_requires_new_metrics_and_expired_candidate_cache():
    values = sample()
    assert all(recovery.evaluate(*values)[0].values())
    assert not recovery.evaluate(*values, after=time.time() - 5)[0]['native_candidates_80']
    assert all(recovery.evaluate(*values, after=time.time() - 31)[0].values())
    assert not recovery.evaluate(*values, after=time.time() + 1)[0]['fresh_native_clients_20']


@pytest.mark.parametrize('failure', ['unknown-channel', 'changed-channel', 'duplicate-bss', 'missing-candidate', 'stale-client'])
def test_incomplete_recovery_fails(failure):
    current, state, bsses = sample()
    expected = {row['bssid']: row['channel'] for row in bsses['bsses']}
    if failure == 'unknown-channel':
        bsses['bsses'][0]['channel'] = 0
    elif failure == 'changed-channel':
        bsses['bsses'][0]['channel'] = 1
    elif failure == 'duplicate-bss':
        bsses['bsses'][0]['bssid'] = bsses['bsses'][1]['bssid']
    elif failure == 'missing-candidate':
        current['optimizer']['client_decisions'][0]['scores'].pop()
    else:
        current['network']['clients'][0]['metric_observed_at'] = '2020-01-01T00:00:00Z'
    assert not all(recovery.evaluate(current, state, bsses, expected)[0].values())


def test_identity_allows_only_controller_service_change():
    before = {'medium': {'pid': 80}, 'bpibroadband': {'pid': 2, 'services':
        'Id=em_agent.service\nMainPID=3\nActiveState=active\nNRestarts=0\n\n'
        'Id=em_ctrl.service\nMainPID=4\nActiveState=active\nNRestarts=0'},
        **{f'bpiap-{index}': {'pid': 10 + index} for index in range(4)}}
    after = deepcopy(before)
    after['bpibroadband']['services'] = after['bpibroadband']['services'].replace('MainPID=4', 'MainPID=5')
    assert recovery.split_identity(before)[0] == recovery.split_identity(after)[0]
    after['medium']['pid'] = 90
    assert recovery.split_identity(before)[0] != recovery.split_identity(after)[0]


def test_disruption_requires_explicit_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery.sys, 'argv', ['recovery', '--mode', 'kill', '--output', str(tmp_path / 'result')])
    with pytest.raises(SystemExit) as error:
        recovery.main()
    assert error.value.code == 2
    assert not (tmp_path / 'result').exists()
