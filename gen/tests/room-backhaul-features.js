'use strict';

const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const {execFile} = require('child_process');
const {promisify} = require('util');
const execute = promisify(execFile);
const rooms = ['backhaul-branch-formation', 'backhaul-parent-handover', 'backhaul-isolation-recovery'];
const containers = {gateway: 'bpibroadband', extender_1: 'bpiap', extender_2: 'bpiap-001', extender_3: 'bpiap-002', extender_4: 'bpiap-003'};
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function interfaceState(raw) {
  const apInfo = raw.split(/Connected to|Not connected/)[0];
  return {apBssid: apInfo.match(/\baddr ([0-9a-f:]{17})/i)?.[1]?.toLowerCase(),
    apOperating: /\bssid mesh_backhaul\b/.test(apInfo) && /\bchannel 36 \(5180 MHz\)/.test(apInfo),
    fronthaulAps: Number(raw.match(/FRONTHAUL_APS=(\d+)/)?.[1] ?? NaN),
    parentBssid: raw.match(/Connected to ([0-9a-f:]{17})/i)?.[1]?.toLowerCase() || null,
    pingOk: /PROBE_EXIT=0\b/.test(raw)};
}

function summarizeNative(samples, room) {
  const parents = samples.map(sample => sample.native?.parents || {});
  const isolated = samples.some(sample => sample.native?.parents.extender_4 === null && sample.native?.nodes.extender_4?.pingOk === false);
  return room === 'backhaul-branch-formation'
    ? {branchObserved: parents.some(value => value.extender_3 === 'extender_1' && value.extender_4 === 'extender_2')}
    : room === 'backhaul-parent-handover'
      ? {lowerRelayObserved: parents.some(value => value.extender_3 === 'extender_2')}
      : {upstreamOutageObserved: isolated};
}

async function run(options) {
  for (const key of ['host', 'vm']) assert.match(options[key], /^[a-zA-Z0-9_.-]+$/);
  assert.equal(options['yes-act'], 'true', 'Explicit --yes-act true is required; these rooms change live RF and can interrupt service');
  const selectedRooms = options.room ? [options.room] : rooms;
  assert.ok(selectedRooms.every(id => rooms.includes(id)), 'Unknown geometry room');
  const directory = path.resolve(options.output);
  assert.ok(!fs.existsSync(directory), 'Use a new output directory');
  fs.mkdirSync(directory, {recursive: true});
  const save = (name, value) => fs.writeFileSync(path.join(directory, name), JSON.stringify(value, null, 2) + '\n');
  const report = {started: new Date().toISOString(), scope: 'RDK geometry-room features; bounded native observations, not a soak or native-policy qualification',
    rooms: [], errors: [], featureChecksPassed: false, recoveryPassed: false};
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
  const environment = {...process.env};
  delete environment.DISPLAY;
  const browser = await chromium.launch({headless: true, env: environment, executablePath: process.env.CHROMIUM_PATH,
    args: ['--no-sandbox', '--ozone-platform=headless', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']});
  const context = await browser.newContext({viewport: {width: 1280, height: 900}});
  const roomPage = await context.newPage();
  const topologyPage = await context.newPage();
  const base = options['room-url'].replace(/\/$/, '');
  let leaseToken = null;
  let changed = false;
  let baseline = null;
  let currentRoom = null;
  const request = async endpoint => {
    const response = await context.request.get(base + endpoint, {timeout: 15000});
    if (!response.ok()) throw new Error(endpoint + ': HTTP ' + response.status());
    return response.json();
  };
  roomPage.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/api/demo/world/apply')) {
      leaseToken = request.postDataJSON()?.token || leaseToken;
    }
  });
  for (const page of [roomPage, topologyPage]) page.on('pageerror', error => report.errors.push(error.message));

  async function native() {
    const readings = await Promise.all(Object.entries(containers).map(async ([role, container]) => {
      const script = 'iw dev wifi1.1 info; iw dev wifi1.3 link 2>/dev/null; ping -I brlan0 -q -c 1 -W 1 10.0.0.1 >/dev/null 2>&1; printf "\\nPROBE_EXIT=%s\\n" "$?"; printf "FRONTHAUL_APS=%s\\n" "$(iw dev | grep -Ec \"ssid (private_ssid|iot_ssid)$\")"';
      try {
        const result = await execute('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', options.host,
          'lxc exec ' + options.vm + ' -- lxc exec ' + container + " -- sh -c '" + script + "'"],
        {timeout: 12000, maxBuffer: 65536});
        return [role, {...interfaceState(result.stdout), raw: result.stdout}];
      } catch (error) { return [role, {error: error.message, pingOk: null}]; }
    }));
    const nodes = Object.fromEntries(readings);
    const owners = Object.fromEntries(readings.filter(([, value]) => value.apBssid).map(([role, value]) => [value.apBssid, role]));
    return {nodes, parents: Object.fromEntries(readings.filter(([role]) => role !== 'gateway')
      .map(([role, value]) => [role, owners[value.parentBssid] || null]))};
  }

  async function sample(label, includeNative = false) {
    const [state, interactions, topology, visible] = await Promise.all([
      request('/api/demo/current'), request('/api/demo/interactions'),
      topologyPage.evaluate(() => {
        const instance = window.EasyMeshController;
        return {nodes: (instance?.topology?.nodes || []).map(node => ({id: node.id, name: node.name})),
          edges: (instance?.topology?.edges || []).map(edge => ({from: String(edge.from), to: String(edge.to)})),
          stations: [...document.querySelectorAll('#topology-visualization .sta-node')].map(element => ({
            mac: element.__data__?.sta?.staMAC, bssid: element.__data__?.sta?.bssid}))};
      }),
      roomPage.evaluate(() => ({policy: document.getElementById('backhaulPolicyTitle').textContent,
        clock: document.getElementById('tnow').textContent, meta: document.getElementById('worldmeta').textContent,
        optimizer: document.getElementById('optimizerStatus').textContent})),
    ]);
    const result = {at: new Date().toISOString(), label, interactions, visible, topology,
      health: state.health, mesh: state.network?.mesh, clients: state.network?.clients, optimizer: state.optimizer,
      native: includeNative ? await native() : undefined};
    if (currentRoom) currentRoom.samples.push(result);
    return result;
  }

  async function load(id) {
    changed = true;
    const applied = roomPage.waitForResponse(response => response.url().endsWith('/api/demo/world/apply') && response.request().method() === 'POST', {timeout: 60000});
    if (id === 'default') await roomPage.locator('#defaultWorld').click();
    else await roomPage.locator('#world').selectOption(id);
    const response = await applied;
    const result = await response.json();
    assert.ok(response.ok(), JSON.stringify(result));
    assert.equal(result.backhaul_rf_verified, true);
    await roomPage.waitForFunction(() => !document.getElementById('world').disabled, null, {timeout: 60000});
    return result;
  }

  async function playTo(time) {
    await roomPage.locator('#play').click();
    const deadline = Date.now() + 35000;
    while (Date.now() < deadline) {
      const state = await request('/api/demo/interactions');
      if (state.playback.time_ms === time && state.playback.status !== 'playing') return state;
      assert.ok(!state.fault, 'Room fault: ' + state.fault);
      await delay(500);
    }
    throw new Error('Playback did not reach ' + time + ' within the short-test deadline');
  }

  try {
    const before = await request('/api/demo/current');
    baseline = await request('/api/demo/interactions');
    assert.equal(before.health.healthy, true, 'Start with a healthy default lab');
    assert.equal(before.health.api_active, 20);
    assert.equal(baseline.backhaul_policy, 'fixed-startup-mesh');
    assert.equal(baseline.lease.held, false, 'Do not take another operator’s lease');
    save('baseline.json', {health: before.health, mesh: before.network.mesh, backhaul: baseline.backhaul_links, daemon: baseline.daemon});
    const catalog = await request('/api/demo/worlds');
    for (const id of rooms) assert.equal(catalog.worlds.find(entry => entry.id === id)?.backhaul_rf, 'geometry');
    await roomPage.goto(base + '/');
    await roomPage.waitForFunction(() => window.__viewer && !document.getElementById('world').disabled, null, {timeout: 60000});
    await topologyPage.goto(options['topology-url']);
    await topologyPage.locator('[data-tab="topology"]').click();
    await topologyPage.waitForSelector('.sta-node', {timeout: 30000});
    for (const id of selectedRooms) {
      currentRoom = {id, samples: []};
      report.rooms.push(currentRoom);
      console.log(id + ': loading geometry RF');
      currentRoom.load = await load(id);
      let loaded = await sample('loaded', true);
      if (id === 'backhaul-branch-formation') {
        const deadline = Date.now() + 60000;
        while ((!loaded.health?.healthy || loaded.health.api_active !== 10 ||
                loaded.optimizer?.fleet?.converged !== true) && Date.now() < deadline) {
          await delay(1000);
          loaded = await sample('initial-client-convergence', true);
        }
        assert.equal(loaded.optimizer?.fleet?.converged, true,
          'The loaded ten-client room must converge before testing its movement');
        currentRoom.initialConvergenceVerified = true;
      }
      if (id === 'backhaul-isolation-recovery') {
        const deadline = Date.now() + 15000;
        while (loaded.native.nodes.extender_4.pingOk !== true && Date.now() < deadline) {
          await delay(1000);
          loaded = await sample('initial-reachability', true);
        }
        assert.equal(loaded.native.nodes.extender_4.pingOk, true, 'Isolation requires a verified working upstream link before movement');
        currentRoom.initialUpstreamVerified = true;
      }
      assert.ok(Object.values(loaded.native.nodes).every(node => !node.error), 'Missing out-of-band native observations');
      assert.ok(Object.values(loaded.native.nodes).every(node => node.apOperating && node.fronthaulAps === 6),
        'Geometry rooms require operating backhaul and client-facing APs, not only configured BSS records');
      assert.equal(loaded.interactions.backhaul_policy, 'modeled');
      assert.equal(loaded.interactions.backhaul_authority, 'native');
      assert.equal(loaded.interactions.expected_online_clients, 10);
      assert.match(loaded.visible.policy, /Geometry-driven backhaul · native parent selection/);
      assert.equal(loaded.interactions.daemon.instance_id, baseline.daemon.instance_id);
      currentRoom.midpoint = await playTo(12000);
      assert.notDeepEqual(currentRoom.midpoint.backhaul_links, loaded.interactions.backhaul_links);
      for (let index = 0; index < 3; index++) {
        const observation = await sample('midpoint-' + index, true);
        assert.ok(Object.values(observation.native.nodes).every(node => !node.error), 'Missing native midpoint observations');
        if (index < 2) await delay(1500);
      }
      if (id === 'backhaul-isolation-recovery') {
        const links = currentRoom.midpoint.backhaul_links.filter(link => [link.source_role, link.destination_role].includes('extender_4'));
        assert.ok(links.length > 0 && links.every(link => link.snr_db === -20), 'Isolation must affect real mesh RF');
        assert.equal(currentRoom.midpoint.roles.extender_4.present, true, 'This must not be a fronthaul-disable shortcut');
      }
      currentRoom.nativeOutcome = summarizeNative(currentRoom.samples.filter(entry => entry.label.startsWith('midpoint')), id);
      if (id === 'backhaul-branch-formation') {
        const deadline = Date.now() + 60000;
        let observation = currentRoom.samples.at(-1);
        const converged = entry => summarizeNative([entry], id).branchObserved &&
          Object.values(entry.native.nodes).every(node => node.pingOk && node.fronthaulAps === 6) &&
          entry.health?.healthy && entry.health.topology_nodes === 6 && entry.health.api_active === 10 &&
          entry.optimizer?.fleet?.converged === true && entry.topology.nodes.length === 6 &&
          new Set(entry.topology.stations.map(station => station.mac)).size === 10 &&
          entry.mesh?.backhaul_edges?.some(edge => edge.child_role === 'extender_3' && edge.parent_role === 'extender_1') &&
          entry.mesh?.backhaul_edges?.some(edge => edge.child_role === 'extender_4' && edge.parent_role === 'extender_2');
        while (!converged(observation) && Date.now() < deadline) {
          await delay(1000);
          observation = await sample('midpoint-branch-convergence', true);
        }
        currentRoom.nativeOutcome = {...summarizeNative([observation], id), convergenceVerified: converged(observation)};
        assert.equal(currentRoom.nativeOutcome.convergenceVerified, true,
          'Branch must recover native uplinks, traffic, both topology views and all ten client decisions');
      }
      currentRoom.relayApOperating = Object.fromEntries(Object.entries(currentRoom.samples.at(-1).native.nodes)
        .filter(([role]) => role !== 'gateway').map(([role, value]) => [role, value.apOperating]));
      await Promise.all([roomPage.screenshot({path: path.join(directory, id + '-room.png')}),
        topologyPage.screenshot({path: path.join(directory, id + '-topology.png')})]);
      currentRoom.finish = await playTo(24000);
      assert.deepEqual(currentRoom.finish.backhaul_links, loaded.interactions.backhaul_links);
      currentRoom.returnObservation = await sample('returned', true);
      if (id === 'backhaul-isolation-recovery') {
        const deadline = Date.now() + 20000;
        while (currentRoom.returnObservation.native.nodes.extender_4.pingOk !== true && Date.now() < deadline) {
          await delay(1000);
          currentRoom.returnObservation = await sample('return-recovery', true);
        }
        currentRoom.nativeOutcome.returnRecoveryObserved = currentRoom.returnObservation.native.nodes.extender_4.pingOk === true &&
          currentRoom.returnObservation.native.parents.extender_4 !== null;
      }
      currentRoom.featureChecksPassed = true;
      save(id + '.json', currentRoom);
      console.log(JSON.stringify({room: id, featureChecksPassed: true, native: currentRoom.nativeOutcome}));
    }
    report.featureChecksPassed = report.rooms.every(entry => entry.featureChecksPassed) && report.errors.length === 0;
  } catch (error) {
    report.failure = error.stack;
    console.error(error.message);
  } finally {
    if (changed && baseline) {
      try {
        console.log('Restoring default RF and checking native recovery (at most 60 s)');
        await load('default');
        currentRoom = null;
        const restored = await request('/api/demo/interactions');
        assert.equal(restored.backhaul_policy, 'fixed-startup-mesh');
        assert.deepEqual(restored.backhaul_links, baseline.backhaul_links);
        const deadline = Date.now() + 60000;
        while (Date.now() < deadline) {
          const recovery = await sample('default-recovery', true);
          report.recovery = recovery;
          if (recovery.health?.healthy && recovery.health.api_active === 20 && recovery.health.topology_nodes === 6 &&
              Object.values(recovery.native.nodes).every(node => node.pingOk === true)) {
            report.recoveryPassed = true;
            break;
          }
          await delay(1500);
        }
        if (!report.recoveryPassed) report.recoveryFailure = 'Fixed RF restored, but native recovery not verified within 60 seconds; no forced parent changes or native restarts attempted';
      } catch (error) { report.recoveryFailure = error.stack; }
    }
    if (leaseToken) {
      try { await context.request.delete(base + '/api/demo/interactions/lease', {data: {token: leaseToken, command_id: 'backhaul-short-release-' + Date.now()}}); }
      catch (error) { report.errors.push('Lease release: ' + error.message); }
    }
    report.finished = new Date().toISOString();
    report.featureChecksPassed = report.featureChecksPassed && report.errors.length === 0;
    save('report.json', report);
    await browser.close();
  }
  return report;
}

module.exports = {summarizeNative, interfaceState};
if (require.main === module) {
  const options = {};
  for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
  run(options).then(report => {
    console.log(JSON.stringify({featureChecksPassed: report.featureChecksPassed, recoveryPassed: report.recoveryPassed, output: options.output}));
    process.exitCode = report.featureChecksPassed && report.recoveryPassed ? 0 : 1;
  }).catch(error => { console.error(error); process.exitCode = 2; });
}
