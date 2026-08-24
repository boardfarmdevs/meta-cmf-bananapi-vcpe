'use strict';

const assert = require('node:assert/strict');
const graph = require('./graph-layout.js');

const stations = [];
for (let index = 0; index < 5; index += 1) stations.push({ mac: `42:00:00:00:0${index}:00`, label: index ? `extender-${index}` : 'agent-1', role: index ? 'extender' : 'controller-agent' });
for (let index = 5; index < 25; index += 1) stations.push({ mac: `42:00:00:00:${index.toString(16).padStart(2, '0')}:00`, label: index < 15 ? `sta-${index.toString(16).padStart(2, '0')}` : `iot-${index.toString(16).padStart(2, '0')}`, role: index < 15 ? 'wlan-client' : 'iot-client' });

const positions = graph.layoutStations(stations, stations[0].mac);
assert.equal(positions.size, 25);
for (const station of stations) {
  const position = positions.get(station.mac);
  assert.ok(position.x - position.radius >= 0 && position.x + position.radius <= 1000);
  assert.ok(position.y - position.radius >= 0 && position.y + position.radius <= 560);
  assert.ok(graph.labelFontSize(station.label, position.radius) >= 7);
}

const obstaclePositions = new Map([
  ['a', { x: 100, y: 100, radius: 30 }],
  ['obstacle', { x: 200, y: 100, radius: 30 }],
  ['b', { x: 300, y: 100, radius: 30 }],
]);
const route = graph.edgeRoute(obstaclePositions, { source: 'a', destination: 'b' }, 400, 240);
assert.equal(route.kind, 'curve');
assert.match(route.path, / Q /);
assert.ok(graph.quadraticCollisionFree(route.start, route.control, route.end, obstaclePositions, 'a', 'b', 400, 240));
assert.notDeepEqual(route.start, obstaclePositions.get('a'));
assert.notDeepEqual(route.end, obstaclePositions.get('b'));
