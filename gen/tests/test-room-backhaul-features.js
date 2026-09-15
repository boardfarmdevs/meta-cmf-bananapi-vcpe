'use strict';

const assert = require('assert').strict;
const {interfaceState, summarizeNative} = require('./room-backhaul-features.js');
const inactive = 'Interface wifi1.1\n addr 02:00:00:00:01:01\n type AP\n' +
  'Connected to 02:00:00:00:02:02 (on wifi1.3)\n SSID: mesh_backhaul\n freq: 5180\nPROBE_EXIT=0\n';
assert.equal(interfaceState(inactive).apOperating, false, 'STA SSID does not prove its backhaul AP is running');
assert.equal(interfaceState(inactive + '\nFRONTHAUL_APS=6\n').fronthaulAps, 6);
assert.ok(Number.isNaN(interfaceState(inactive).fronthaulAps), 'Missing AP observation must not imply readiness');
assert.equal(interfaceState(inactive).parentBssid, '02:00:00:00:02:02');
assert.equal(interfaceState(inactive).pingOk, true);
const active = inactive.replace(' type AP', ' ssid mesh_backhaul\n channel 36 (5180 MHz), width: 20 MHz\n type AP');
assert.equal(interfaceState(active).apOperating, true);
assert.equal(interfaceState('Not connected.\nPROBE_EXIT=1\n').parentBssid, null);
assert.equal(interfaceState('Not connected.\nPROBE_EXIT=1\n').pingOk, false);
const observed = [{native: {parents: {extender_3: 'extender_1', extender_4: 'extender_2'}, nodes: {extender_4: {pingOk: true}}}}];
assert.equal(summarizeNative(observed, 'backhaul-branch-formation').branchObserved, true);
assert.equal(summarizeNative(observed, 'backhaul-parent-handover').lowerRelayObserved, false);
assert.equal(summarizeNative([{native: {parents: {}, nodes: {extender_4: {pingOk: null}}}}],
  'backhaul-isolation-recovery').upstreamOutageObserved, false, 'Missing observations are not successful isolation');
assert.equal(summarizeNative([{native: {parents: {extender_4: null}, nodes: {extender_4: {pingOk: false}}}}],
  'backhaul-isolation-recovery').upstreamOutageObserved, true);
assert.equal(summarizeNative([{native: {parents: {extender_4: 'gateway'}, nodes: {extender_4: {pingOk: false}}}}],
  'backhaul-isolation-recovery').upstreamOutageObserved, false, 'One lost ping is not proof of backhaul isolation');
console.log('PASS: backhaul AP readiness, native parents, traffic and missing-observation classification');
