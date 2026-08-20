#!/usr/bin/env node

'use strict';

const assert = require('assert').strict;
const path = require('path');

if (process.argv.length !== 3) {
  console.error(`Usage: ${path.basename(process.argv[1])} SCRIPT_JS`);
  process.exit(2);
}

global.document = { addEventListener() {} };
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

const renderTopology = controller.topologyRenderSnapshot(topology);
renderTopology.nodes[0].x = 123;
renderTopology.nodes[0].fx = 123;
renderTopology.edges[0].source = renderTopology.nodes[0];
renderTopology.edges[0]._midpoint = [10, 20];
assert.deepEqual(topology, original, 'D3 render state changed the topology API model');
assert.equal(controller.topologySignature(topology), before);

let redraws = 0;
controller.topology = topology;
controller.updateTopologyVisualization = () => { redraws += 1; };
assert.equal(controller.applyTopologyRefresh(structuredClone(topology)), false);
assert.equal(redraws, 0, 'an unchanged two-second refresh redrew the graph');

console.log('PASS: formatting and D3 rendering leave the polled topology model unchanged');
