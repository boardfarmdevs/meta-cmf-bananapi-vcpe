'use strict';
const assert = require('assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const base = new URL(process.argv[2]);

async function run() {
  const environment = {...process.env};
  delete environment.DISPLAY;
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, env: environment,
    args: ['--no-sandbox', '--ozone-platform=headless', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [], forbidden = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.includes('/api/') || !['GET', 'HEAD'].includes(request.method()) ||
          /^https?:/.test(url.protocol) && url.origin !== base.origin) forbidden.push(request.url());
    });
    await page.goto(new URL('viewer/', base).href);
    await page.waitForFunction(() => window.__viewer && !document.getElementById('worldmeta').textContent.includes('Loading'));
    assert.equal(await page.locator('#interactionBadge').textContent(), 'NO CONNECT');
    assert.match(await page.locator('#roomConvergence').textContent(), /PREVIEW ONLY/);
    const rooms = await page.locator('#world option').evaluateAll(options => options.map(option => option.value));
    assert.equal(rooms.length, 25);
    for (const room of rooms) {
      const response = page.waitForResponse(result => new URL(result.url()).pathname.endsWith('/golden/' + room + '.world.json'));
      await page.locator('#world').selectOption(room);
      const world = await (await response).json();
      await page.waitForFunction(name => document.getElementById('roomName').title === name, world.name);
      await page.evaluate(() => window.__viewer.setTime(0));
      await page.locator('#play').click();
      await page.waitForFunction(() => document.getElementById('tnow').textContent !== '0.0 s');
      await page.locator('#play').click();
      await page.evaluate(() => window.__viewer.setTime(0));
      assert.equal(await page.locator('#play').textContent(), 'Play');
      assert.match(await page.locator('#roomConvergence').textContent(), /PREVIEW ONLY/);
    }
    await page.locator('#openRoomGuide').click();
    assert.equal(await page.locator('#roomGuideList button').count(), rooms.length);
    await page.keyboard.press('Escape');
    await page.locator('#roomFullscreen').click();
    await page.waitForFunction(() => document.fullscreenElement?.id === 'roomView');
    assert.equal(await page.locator('#roomName').isVisible(), true);
    assert.equal(await page.locator('#roomConvergence').isVisible(), true);
    await page.evaluate(() => document.exitFullscreen());
    assert.deepEqual(errors, []);
    assert.deepEqual(forbidden, []);
    console.log('PASS: all ' + rooms.length + ' public rooms load/play, guide/fullscreen work; no backend, private-host or write requests');
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
