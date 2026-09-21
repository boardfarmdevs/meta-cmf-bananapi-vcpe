import test from 'node:test';
import assert from 'node:assert/strict';
import { MediumModel, compare, counter, frameType } from './model.mjs';

const source = '02:00:00:00:00:01', destination = '02:00:00:00:00:02';
function fixture(now = Date.now()) {
  const timestamp = new Date(now).toISOString();
  return { daemon: { instance_id: 'one', generation: '3' }, captured_at: timestamp, last_success: timestamp,
    summary: { summary: { uptime_usec: '10000000' } }, coverage: { paths: { observed_at: timestamp } },
    radios: [{ mac: source, label: 'sta-01', role: 'wlan-client', owner: 'client-001' }, { mac: destination, label: 'Agent-1', role: 'controller-agent' }],
    room: { available: true, observed_at: timestamp, data: { instance_id: 'one', live: true, roles: [{ radio: source, container: 'client-001', present: false, position: [2, 4] }] } },
    paths: [{ source, destination, frequency_mhz: '5180', frames: '9007199254740993', first_seen_usec: '1000', last_seen_usec: '9999999', last_update_sequence: '20', last_snr_db: '30', last_type: '0', last_subtype: '8', multicast: true }] };
}

test('large counters sort and delta without rounding', () => {
  assert.equal(compare('9007199254740993', '9007199254740992'), 1);
  assert.equal(counter('18446744073709551615'), 18446744073709551615n);
  const now = Date.now(), model = new MediumModel(), data = fixture(now);
  model.update(data, now);
  model.update({ coverage: { paths: { observed_at: new Date(now + 2000).toISOString() } }, paths: [{ ...data.paths[0], frames: '9007199254740995', last_update_sequence: '21' }] }, now + 2000);
  assert.equal(model.explore({}, now + 2000).paths[0].rate, 1);
});
test('entry lifetime changes and counter regressions warm up rates', () => {
  const now = Date.now(), model = new MediumModel(), data = fixture(now);
  model.update(data, now);
  model.update({ paths: [{ ...data.paths[0], frames: '1', first_seen_usec: '10000000', last_update_sequence: '22' }], coverage: { paths: { observed_at: new Date(now + 2000).toISOString() } } }, now + 2000);
  assert.equal(model.explore({}, now + 2000).paths[0].rate, null);
});
test('room exclusion remains a bound radio and can have frames', () => {
  const now = Date.now(), model = new MediumModel(); model.update(fixture(now));
  const result = model.explore({ presence: 'room-excluded' }, now);
  assert.equal(result.pool.bound, 1); assert.equal(result.pool.excluded, 1); assert.equal(result.paths.length, 1);
  assert.equal(result.paths[0].multicast, true); assert.equal(result.radios[0].label, 'sta-01');
});
test('stale or foreign room data means unknown, not excluded', () => {
  const now = Date.now(), model = new MediumModel(), data = fixture(now); data.room.data.instance_id = 'different'; model.update(data);
  assert.equal(model.explore({}, now).pool.unknown, 1);
  data.room.data.instance_id = 'one'; data.room.observed_at = new Date(now - 10000).toISOString(); model.update(data);
  assert.equal(model.explore({}, now).pool.excluded, 0);
});
test('table filters and hierarchical expansion preserve directed keys', () => {
  const now = Date.now(), model = new MediumModel(); model.update(fixture(now));
  const result = model.explore({ search: 'sta-01', band: '5GHz', type: '0', expanded: [source, `${source}@5180`] }, now);
  assert.equal(result.paths.length, 1); assert.deepEqual(result.rows.map(row => row.kind), ['radio', 'frequency', 'path']);
  assert.equal(result.paths[0].type, 'Beacon');
  assert.equal(model.explore({ band: '6GHz' }, now).paths.length, 0);
});
test('old traffic and unverified RF do not retain green signal', () => {
  const now = Date.now(), model = new MediumModel(), data = fixture(now); model.update(data);
  assert.equal(model.explore({}, now + 6000).paths[0].snr, null);
  model.update({ pairs: [{ source, destination, snr_db: '40' }], coverage: { pairs: { state: 'complete', generation: '2' } } });
  assert.equal(model.explore({ mode: 'configured' }, now).paths[0].snr, null);
});
test('daemon restart discards old rows and rate state', () => {
  const model = new MediumModel(); model.update(fixture()); model.update({ daemon: { instance_id: 'new', generation: '0' } });
  assert.equal(model.explore().paths.length, 0); assert.equal(model.previous.size, 0);
});
test('unknown frame type is not manufactured as management', () => { assert.equal(frameType(undefined, undefined), 'Unavailable'); });

test('exact-frequency matrix includes pair fallback only with complete override coverage', () => {
  const now = Date.now(), model = new MediumModel(), data = fixture(now);
  data.daemon.capabilities = ['frequency_qualified_snr'];
  data.pairs = [{ source, destination, snr_db: '33' }];
  data.coverage = { pairs: { state: 'complete', generation: '3' }, frequencies: { state: 'complete', generation: '3' } };
  model.update(data);
  let row = model.explore({ mode: 'matrix', frequency: '5180' }, now).paths[0];
  assert.equal(row.snr, 33); assert.equal(row.snrProvenance, 'current pair fallback');
  model.update({ frequencies: [{ source, destination, frequency_mhz: '5180', override: true, snr_db: '-20' }] });
  row = model.explore({ mode: 'matrix', frequency: '5180' }, now).paths[0]; assert.equal(row.snr, -20);
  model.update({ coverage: { ...data.coverage, frequencies: { state: 'collecting', generation: '3' } } });
  assert.equal(model.explore({ mode: 'matrix', frequency: '5180' }, now).paths[0].snr, null);
});
