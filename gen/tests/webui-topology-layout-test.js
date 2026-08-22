#!/usr/bin/env node

'use strict';

const assert = require('assert').strict;
const path = require('path');

if (process.argv.length !== 3) {
  console.error(`Usage: ${path.basename(process.argv[1])} SCRIPT_JS`);
  process.exit(2);
}

global.document = { addEventListener() {}, getElementById() { return null; } };
global.window = { addEventListener() {} };

const Controller = require(path.resolve(process.argv[2]));
const controller = new Controller();
const topology = {
  nodes: [{
    id: 'agent-1',
    haulTypes: [{
      BSSList: [
        { BSSID: '02:00:00:00:00:01', Band: 0, IEEE: '' },
        { BSSID: '02:00:00:00:00:02', Band: 1, IEEE: '' },
        { BSSID: '02:00:00:00:00:03', Band: 3, IEEE: '' },
        { BSSID: '02:00:00:00:00:04', Band: 1, IEEE: '802.11be' }
      ]
    }]
  }, {
    id: 'agent-2',
    haulTypes: []
  }],
  edges: [{ from: 'agent-1', to: 'agent-2', band: -1 }]
};
const original = structuredClone(topology);
const before = controller.topologySignature(topology);
const labels = topology.nodes[0].haulTypes[0].BSSList
  .map(bss => controller.topologyBssIEEELabel(bss));

assert.deepEqual(labels, ['802.11ax', '802.11ax', '802.11be', '802.11be']);
assert.deepEqual(topology, original, 'formatting changed the topology API model');
assert.equal(controller.topologySignature(topology), before);

const cohortStations = [
  { staMAC: '02:00:00:00:09:00', ssid: 'private_ssid' },
  { staMAC: '02:00:00:00:0a:00', ssid: 'private_ssid' },
  { staMAC: '02:00:00:00:13:00', ssid: 'iot_ssid' }
];
const cohortHauls = [
  { name: 'Fronthaul', ssid: 'private_ssid' },
  { name: 'Iot', ssid: 'iot_ssid' },
  { name: 'Backhaul', ssid: 'mesh_backhaul' }
];
const geometry = controller.topologyHaulGeometry(cohortHauls, cohortStations);
const privateBubble = geometry.find(item => item.ssid === 'private_ssid');
const iotBubble = geometry.find(item => item.ssid === 'iot_ssid');
assert.ok(privateBubble.radius >= 110 && iotBubble.radius >= 110,
  'client SSID bubbles were not enlarged');
assert.notDeepEqual(privateBubble.offset, iotBubble.offset,
  'private and IoT bubbles share the same center');
assert.ok(Math.hypot(
  privateBubble.offset.x - iotBubble.offset.x,
  privateBubble.offset.y - iotBubble.offset.y
) >= privateBubble.radius + iotBubble.radius + 12,
  'private and IoT bubbles overlap or lack a readable gap');
for (const station of cohortStations) {
  const placement = controller.topologySTAPlacement(
    station, cohortStations, geometry, 'agent-1'
  );
  const bubble = geometry.find(item => item.ssid === station.ssid);
  const distance = Math.hypot(
    placement.to.x - bubble.offset.x,
    placement.to.y - bubble.offset.y
  );
  assert.ok(Math.abs(distance - placement.edgeRadius) < 0.001,
    `${station.staMAC} was not placed on the ${station.ssid} perimeter`);
  assert.ok(distance + placement.iconSize / 2 + 4 <= bubble.radius + 0.001,
    `${station.staMAC} signal ring extends outside ${station.ssid}`);
}

controller.staPositionCache.set('02:00:00:00:09:00', {
  ownerId: 'agent-1', ssid: 'private_ssid',
  x: privateBubble.offset.x + privateBubble.radius + 120,
  y: privateBubble.offset.y + 75
});
const draggedPlacement = controller.topologySTAPlacement(
  cohortStations[0], cohortStations, geometry, 'agent-1'
);
assert.equal(draggedPlacement.to.x,
  privateBubble.offset.x + privateBubble.radius + 120,
  'manual client X position did not survive a topology redraw');
assert.equal(draggedPlacement.to.y, privateBubble.offset.y + 75,
  'manual client Y position did not survive a topology redraw');
assert.ok(draggedPlacement.to.x > privateBubble.offset.x + privateBubble.radius,
  'manual client position was incorrectly constrained to the SSID bubble');
const reassociatedPlacement = controller.topologySTAPlacement(
  cohortStations[0], cohortStations, geometry, 'agent-2'
);
assert.notEqual(reassociatedPlacement.to.x, draggedPlacement.to.x,
  'manual client position survived an AP owner change');
assert.equal(controller.staPositionCache.has('02:00:00:00:09:00'), false,
  'stale client drag position was not discarded after reassociation');
assert.ok(controller.topologyNodeExtent({
  haulTypes: cohortHauls,
  STAList: cohortStations
}) > 240, 'expanded SSID groups did not increase D3 collision spacing');

const metricsUpdated = new Date().toISOString();
controller.clients = [{
  mac: '02:00:00:00:09:00',
  client_metrics: {
    rssi_dbm: -41,
    rcpi: 138,
    last_updated: metricsUpdated,
    association_uptime_seconds: 10
  }
}];
const liveSignal = controller.topologySignalForSTA({
  staMAC: '02:00:00:00:09:00',
  band: 1
});
assert.equal(liveSignal.available, true);
assert.equal(liveSignal.rssi, -41);
assert.equal(liveSignal.rcpi, 138);
assert.equal(liveSignal.quality, 'strong');
assert.equal(liveSignal.band, '5G');

const uptimeOnlyChange = structuredClone(controller.clients);
uptimeOnlyChange[0].client_metrics.association_uptime_seconds = 12;
assert.equal(
  controller.topologyClientMetricsSignature(controller.clients),
  controller.topologyClientMetricsSignature(uptimeOnlyChange),
  'association uptime would redraw the topology every two seconds'
);
const signalChange = structuredClone(controller.clients);
signalChange[0].client_metrics.rssi_dbm = -72;
assert.notEqual(
  controller.topologyClientMetricsSignature(controller.clients),
  controller.topologyClientMetricsSignature(signalChange),
  'an RSSI change would not redraw the topology'
);

controller.clients = [{
  mac: '02:00:00:00:13:00',
  client_metrics: {
    rssi_dbm: 0,
    rcpi: 100,
    last_updated: metricsUpdated
  }
}];
const rcpiFallback = controller.topologySignalForSTA({
  staMAC: '02:00:00:00:13:00',
  band: 3
});
assert.equal(rcpiFallback.rssi, -60);
assert.equal(rcpiFallback.quality, 'good');
assert.equal(rcpiFallback.band, '6G');

controller.clients[0].client_metrics.last_updated = '2000-01-01T00:00:00Z';
const staleSignal = controller.topologySignalForSTA({
  staMAC: '02:00:00:00:13:00',
  band: 3
});
assert.equal(staleSignal.available, false);
assert.equal(staleSignal.stale, true);
assert.equal(staleSignal.label, 'stale');
const visualizationSource = controller.updateTopologyVisualization.toString();
assert.match(visualizationSource, /sta-signal-ring/,
  'topology does not render the signal-quality ring');
assert.doesNotMatch(visualizationSource, /sta-signal-label/,
  'topology still renders signal text outside the client hover details');
assert.match(visualizationSource, /Signal:.*signalInfo/,
  'client hover details do not contain the signal strength');
assert.match(visualizationSource, /topologyBandLabel\(d\.band\).*ch/,
  'backhaul labels do not show both band and channel');
assert.match(controller.refreshTopologyData.toString(), /apiCall\('\/clients'\)/,
  'topology refresh does not acquire the live client metrics snapshot');
assert.match(visualizationSource, /staDragStarted/,
  'topology clients do not install a D3 drag interaction');
assert.match(visualizationSource, /sta-steer-pulse/,
  'topology does not render the post-steer client pulse');
assert.match(visualizationSource, /sta-steering-trail/,
  'topology does not render the fading steering trail');

const associationSTA = {
  staMAC: '02:00:00:00:09:00', ssid: 'private_ssid'
};
controller.staMoveEffects.clear();
controller.recordTopologyAssociationChanges({
  nodes: [{ id: 'agent-1', name: 'Agent-1', STAList: [associationSTA] }]
}, {
  nodes: [{ id: 'agent-2', name: 'Extender-1', STAList: [associationSTA] }]
});
const moveEffect = controller.topologyMoveEffectForSTA(associationSTA, 'agent-2');
assert.equal(moveEffect.fromOwnerId, 'agent-1');
assert.equal(moveEffect.toOwnerId, 'agent-2');
assert.ok(moveEffect.remainingMs > 0,
  'new association move effect was already expired');

const renderTopology = controller.topologyRenderSnapshot(topology);
renderTopology.nodes[0].x = 123;
renderTopology.nodes[0].fx = 123;
renderTopology.edges[0].source = renderTopology.nodes[0];
renderTopology.edges[0]._midpoint = [10, 20];
assert.deepEqual(topology, original, 'D3 render state changed the topology API model');
assert.equal(controller.topologySignature(topology), before);

const simulation = { nodes: () => renderTopology.nodes };
assert.strictEqual(controller.topologySimulationNodes(simulation), renderTopology.nodes);
assert.deepEqual(controller.topologySimulationNodes(null), []);
assert.match(controller.optimizeTopologyLayout.toString(), /topologySimulationNodes\(simulation\)/,
  'Optimize Layout does not operate on the D3 render-node set');
assert.deepEqual(topology, original, 'selecting simulation nodes changed the API model');

let layoutEnd;
let fitted = false;
const layoutEvents = [];
const layoutNodes = structuredClone(renderTopology.nodes);
layoutNodes.forEach(node => { node.fx = node.x ?? 0; node.fy = node.y ?? 0; });
const fakeSimulation = {
  nodes: () => layoutNodes,
  on(name, handler) {
    assert.equal(name, 'end.autoLayout');
    layoutEnd = handler;
    return this;
  },
  alpha(value) { assert.equal(value, 1); return this; },
  alphaTarget(value) { assert.equal(value, 0); return this; },
  restart() {
    assert.ok(layoutNodes.every(node => node.fx === null && node.fy === null),
      'Optimize Layout did not release every rendered node');
    layoutNodes.forEach((node, index) => {
      node.x = 300 + index * 400;
      node.y = 200 + index * 250;
    });
    controller.topologyRenderPending = true;
    layoutEnd();
    return this;
  }
};
controller.topologySimulation = fakeSimulation;
controller.nodePositionCache = new Map();
controller.staPositionCache.set('manual-client', {
  ownerId: 'agent-1', ssid: 'private_ssid', x: 100, y: 200
});
controller.topologyLayoutGeneration = 0;
controller.topologyRenderPending = false;
controller.showNotification = () => {};
controller.fitTopologyToView = () => { fitted = true; layoutEvents.push('fit'); };
controller.updateTopologyVisualization = () => { layoutEvents.push('redraw'); };
controller.optimizeTopologyLayout();
assert.equal(controller.nodePositionCache.size, layoutNodes.length);
assert.equal(controller.staPositionCache.size, 0,
  'Optimize Layout did not reset manual client positions');
assert.ok(layoutNodes.every(node => node.fx === node.x && node.fy === node.y),
  'optimized render positions were not fixed and cached');
assert.equal(fitted, true, 'optimized graph was not fitted to the viewport');
assert.deepEqual(layoutEvents, ['fit', 'redraw'],
  'a deferred two-second redraw ran before the completed layout was fitted');
assert.deepEqual(topology, original, 'Optimize Layout changed the API model');

let redraws = 0;
controller.topology = topology;
controller.updateTopologyVisualization = () => { redraws += 1; };
assert.equal(controller.applyTopologyRefresh(structuredClone(topology)), false);
assert.equal(redraws, 0, 'an unchanged two-second refresh redrew the graph');

console.log('PASS: topology layout, live signal, STA dragging and steering cues preserve the API model');
