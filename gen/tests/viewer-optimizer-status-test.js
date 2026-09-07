'use strict';
const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const html = fs.readFileSync(path.resolve(__dirname, '../wmediumd/configurator/worlds/viewer/index.html'), 'utf8');
const elements = {};
const context = {
  optimizerState: {}, networkState: {mesh: {nodes: []}}, healthState: {healthy: true}, selected: 'client',
  liveMode: true, liveClock: {serverMs: Date.parse('2026-09-07T03:00:00Z'), receivedMs: 0},
  performance: {now: () => 0}, displayRole: role => role,
  $: selector => elements[selector] || (elements[selector] = {}),
};
vm.createContext(context);
for (const name of ['esc', 'phaseClass', 'optimizerBadgeClasses', 'optimizerReason', 'renderOptimizerStatus']) {
  vm.runInContext(html.match(new RegExp('  function ' + name + '\\([\\s\\S]*?\\n  \\}'))[0], context);
}
context.optimizerState = {fleet: {converged: true}, evaluated_at: '2026-09-07T02:59:55Z'};
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /Converged: all clients checked/);
context.optimizerState.progress = {kind: 'optimizer.progress', phase: 'candidate_queries', completed_queries: 2, total_queries: 5, selected_clients: 4, total_clients: 20};
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /2 \/ 5 queries completed/);
assert.doesNotMatch(elements['#optimizerStatus'].innerHTML, /Converged:/);
context.optimizerState.status = 'unavailable';
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /Retrying: measuring AP alternatives/);
delete context.optimizerState.status;
context.optimizerState.progress = {kind: 'optimizer.measurement.waiting', reason: 'movement_active'};
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /Waiting for device movement/);
context.optimizerState.status = 'unavailable';
context.optimizerState.progress = {kind: 'optimizer.measurement.waiting', reason: 'backhaul_reconciling'};
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /Settling mesh backhaul before measuring client APs/);
assert.match(html, /BACKHAUL SETTLING/);
assert.ok(html.indexOf("optimizerState.progress.reason === 'backhaul_reconciling'") < html.indexOf("optimizerState.status === 'unavailable'"));
context.optimizerState = {client_decisions: [{role: 'client', reason: 'minimum_dwell_not_met', association_uptime_seconds: 0,
  wait_remaining_seconds: 20, current_rcpi: 76, source_role: 'extender_3'}]};
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /1 clients waiting or blocked/);
assert.match(elements['#optimizerClientRows'].innerHTML, /association age 0 s/);
assert.match(elements['#optimizerStatus'].innerHTML, /20 s remaining at evaluation/);
context.optimizerState = {fleet: {converged: true}, evaluated_at: '2026-09-07T02:58:00Z'};
context.renderOptimizerStatus();
assert.match(elements['#optimizerStatus'].innerHTML, /Last result is old/);
assert.doesNotMatch(elements['#optimizerStatus'].innerHTML, /Converged:/);
assert.match(html, /optimizerState\.client_decisions = \[\]/);
context.optimizerState = {};
context.liveClock = null;
assert.doesNotThrow(() => context.renderOptimizerStatus());
context.liveClock = {serverMs: Date.parse('2026-09-07T03:00:00Z'), receivedMs: 0};
context.optimizerState = {evaluated_at: '2026-09-07T02:59:55Z', automatic_actuation: true,
  automatic_actuation_ready: true, actions_used: 0, maximum_actions: 100,
  decision: {reason: 'candidate_gain_too_small'}};
assert.equal(context.optimizerBadgeClasses('stable').phase, 'healthy');
assert.equal(context.optimizerBadgeClasses('stable').mode, 'healthy');
context.optimizerState.progress = {kind: 'optimizer.progress'};
assert.equal(context.optimizerBadgeClasses('stable').mode, 'healthy');
context.optimizerState.decision.reason = 'minimum_dwell_not_met';
assert.equal(context.optimizerBadgeClasses('stable').phase, 'waiting');
context.optimizerState.actions_used = 100;
assert.equal(context.optimizerBadgeClasses('stable').mode, 'waiting');
context.optimizerState.actions_used = 0;
context.optimizerState.automatic_actuation_ready = false;
assert.equal(context.optimizerBadgeClasses('stable').mode, 'waiting');
context.optimizerState.automatic_actuation_ready = true;
context.healthState.healthy = false;
assert.equal(context.optimizerBadgeClasses('stable').mode, 'waiting');
context.healthState.healthy = true;
context.optimizerState.progress = {kind: 'optimizer.environment.changed'};
assert.equal(context.optimizerBadgeClasses('stable').phase, 'unknown');
assert.equal(context.optimizerBadgeClasses('stable').mode, 'unknown');
delete context.optimizerState.progress;
context.optimizerState.evaluated_at = '2026-09-07T02:58:00Z';
assert.equal(context.optimizerBadgeClasses('stable').phase, 'unknown');
assert.equal(context.optimizerBadgeClasses('stable').mode, 'unknown');
context.optimizerState.evaluated_at = 'invalid';
assert.equal(context.optimizerBadgeClasses('stable').mode, 'unknown');
context.optimizerState.evaluated_at = '2026-09-07T02:59:55Z';
context.optimizerState.status = 'unavailable';
assert.equal(context.optimizerBadgeClasses('stable').mode, 'unknown');
delete context.optimizerState.status;
context.optimizerState.automatic_actuation = false;
assert.equal(context.optimizerBadgeClasses('stable').mode, '');
assert.equal(context.optimizerBadgeClasses('steering').phase, 'steering');
assert.equal(context.optimizerBadgeClasses('failed').phase, 'failed');
context.liveClock = null;
assert.equal(context.optimizerBadgeClasses('stable').phase, 'unknown');
assert.match(html, /\.phase\.healthy \{ color: #fff; background: #176b48;/);
assert.match(html, /badges\.phase/);
assert.match(html, /badges\.mode/);
context.networkState = null;
context.storyState = 'Waiting for backhaul';
context.renderRecentEvents = () => {};
context.optimizerState = {status: 'unavailable', progress: {kind: 'optimizer.measurement.waiting', reason: 'backhaul_reconciling'}};
vm.runInContext(html.match(/  function renderLivePanels\([\s\S]*?\n  \}/)[0], context);
context.renderLivePanels();
assert.match(elements['#optimizerMetrics'].innerHTML, /BACKHAUL SETTLING/);
assert.doesNotMatch(elements['#optimizerMetrics'].innerHTML, /MEASUREMENTS UNAVAILABLE/);
console.log('PASS: optimizer progress, decision reasons, green healthy badges, waiting/unknown/error states and RF invalidation');
