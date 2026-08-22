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
  const placement = controller.topologySTAPlacement(station, cohortStations, geometry);
  const bubble = geometry.find(item => item.ssid === station.ssid);
  const distance = Math.hypot(
    placement.to.x - bubble.offset.x,
    placement.to.y - bubble.offset.y
  );
  assert.ok(distance + placement.iconSize / 2 + 28 <= bubble.radius + 0.001,
    `${station.staMAC} was placed outside ${station.ssid}`);
}
assert.ok(controller.topologyNodeExtent({
  haulTypes: cohortHauls,
  STAList: cohortStations
}) > 240, 'expanded SSID groups did not increase D3 collision spacing');

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
    layoutEnd();
    return this;
  }
};
controller.topologySimulation = fakeSimulation;
controller.nodePositionCache = new Map();
controller.topologyLayoutGeneration = 0;
controller.topologyRenderPending = false;
controller.showNotification = () => {};
controller.fitTopologyToView = () => { fitted = true; };
controller.optimizeTopologyLayout();
assert.equal(controller.nodePositionCache.size, layoutNodes.length);
assert.ok(layoutNodes.every(node => node.fx === node.x && node.fy === node.y),
  'optimized render positions were not fixed and cached');
assert.equal(fitted, true, 'optimized graph was not fitted to the viewport');
assert.deepEqual(topology, original, 'Optimize Layout changed the API model');

let redraws = 0;
controller.topology = topology;
controller.updateTopologyVisualization = () => { redraws += 1; };
assert.equal(controller.applyTopologyRefresh(structuredClone(topology)), false);
assert.equal(redraws, 0, 'an unchanged two-second refresh redrew the graph');

console.log('PASS: formatting, D3 rendering and optimization preserve the polled topology model');
