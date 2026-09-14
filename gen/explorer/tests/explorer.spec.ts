import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
import { entries, revision } from '../app/system';

const explorerPath = '/meta-cmf-bananapi-vcpe/explorer/';

test('all component relationships and pinned source references resolve', () => {
  const repository = fileURLToPath(new URL('../../..', import.meta.url));
  for (const entry of Object.values(entries)) {
    for (const related of entry.related) expect(entries[related]).toBeDefined();
    for (const reference of entry.sources) {
      const path = reference.startsWith('gen/')
        ? reference
        : `doc/easymesh/${reference}`;
      expect(() =>
        execFileSync('git', ['cat-file', '-e', `${revision}:${path}`], {
          cwd: repository,
        }),
      ).not.toThrow();
    }
  }
});

for (const prefix of ['', '/meta-cmf-bananapi-vcpe', '/another-project']) {
  test(`static assets and fonts work without a backend at ${prefix || '/'} /explorer/`, async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    const requests: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('requestfailed', (failed) => errors.push(failed.url()));
    page.on('response', (response) => {
      if (response.status() >= 400) errors.push(response.url());
    });
    page.on('request', (requested) => requests.push(requested.url()));
    await page.goto(`${prefix}/explorer`);
    await expect(page).toHaveURL(new RegExp(`${prefix}/explorer/$`));
    await expect(
      page.getByRole('heading', { name: 'A whole mesh. Under the hood.' }),
    ).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    expect(
      await page.evaluate(() => document.fonts.check('16px "Geist Variable"')),
    ).toBe(true);
    await page.reload();
    await expect(
      page.getByRole('tab', { name: 'Architecture', exact: true }),
    ).toHaveAttribute('aria-selected', 'true');
    await page.goto(`${prefix}/explorer/index.html`);
    await expect(
      page.getByRole('heading', { name: 'A whole mesh. Under the hood.' }),
    ).toBeVisible();
    expect(
      requests.every((address) => {
        const resource = new URL(address);
        return (
          resource.origin === 'http://127.0.0.1:4178' &&
          resource.pathname.startsWith(`${prefix}/explorer`)
        );
      }),
    ).toBe(true);
    expect(requests.some((address) => address.endsWith('.woff2'))).toBe(true);
    expect(errors).toEqual([]);
    expect(
      (await request.get(`${prefix}/explorer/missing-page`)).status(),
    ).toBe(404);
  });
}

test('architecture inspectors, related components, and keyboard controls', async ({
  page,
}, testInfo) => {
  await page.goto(explorerPath);
  const blocks = page.locator('.inner-block');
  const count = await blocks.count();
  expect(count).toBeGreaterThan(20);
  for (let index = 0; index < count; index += 1) {
    await blocks.nth(index).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole('heading', { name: 'Inside this block' }),
    ).toBeVisible();
    await expect(dialog.locator('.detail-source').first()).toHaveAttribute(
      'href',
      new RegExp(`/blob/${revision}/`),
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  }
  await page.getByRole('button', { name: 'EM CLI / WebUI' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'EasyMesh controller', exact: true })
    .click();
  await expect(
    page
      .getByRole('dialog')
      .getByRole('heading', { name: 'EasyMesh controller', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('tab', { name: 'Architecture', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('tab', { name: 'Network topology', exact: true }),
  ).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('tab', { name: 'Architecture', exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath('architecture-desktop.png'),
    fullPage: true,
  });
});

test('topology shapes and example client inspection remain interactive', async ({
  page,
}, testInfo) => {
  await page.goto(explorerPath);
  await page
    .getByRole('tab', { name: 'Network topology', exact: true })
    .click();
  await expect(page.locator('.top-client')).toHaveCount(20);
  for (const [shape, parent] of [
    ['Star', 'Agent-1'],
    ['Chain', 'Extender-3'],
    ['Branch', 'Extender-3'],
  ]) {
    await page.getByRole('tab', { name: shape, exact: true }).click();
    await page.getByRole('button', { name: /Extender-4.*3 radios/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(
      dialog
        .locator('dl div')
        .filter({ has: page.locator('dt', { hasText: /^Example parent$/ }) }),
    ).toContainText(parent);
    await expect(dialog).toContainText(shape.toLowerCase());
    await page.keyboard.press('Escape');
  }
  await page.locator('.top-client').first().click();
  await expect(page.getByRole('dialog')).toContainText(
    'Illustrative assignment; no live metrics',
  );
  await page.keyboard.press('Escape');
  await page.screenshot({
    path: testInfo.outputPath('topology-desktop.png'),
    fullPage: true,
  });
});

test('all protocol journeys and the qualification view work', async ({
  page,
}, testInfo) => {
  await page.goto(explorerPath);
  await page.getByRole('tab', { name: 'Protocol paths', exact: true }).click();
  for (const journey of [
    'Client traffic',
    'Commanded steering',
    'Band steering',
    'Mesh onboarding',
    'RF feedback loop',
  ]) {
    await page.getByRole('tab', { name: journey, exact: true }).click();
    await expect(
      page.getByRole('button', { name: 'Previous', exact: true }),
    ).toBeDisabled();
    for (let step = 1; step <= 5; step += 1) {
      await expect(page.locator('.step-detail .eyebrow')).toContainText(
        `${step} / 5`,
      );
      await page.locator('.path-block').first().click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await page.keyboard.press('Escape');
      await page
        .getByRole('button', {
          name: step === 5 ? 'Start again' : 'Next boundary',
          exact: true,
        })
        .click();
    }
    await expect(page.locator('.step-detail .eyebrow')).toContainText('1 / 5');
  }
  await page.screenshot({
    path: testInfo.outputPath('protocol-paths-desktop.png'),
    fullPage: true,
  });
  await page.getByRole('tab', { name: 'Current state', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'The system this page describes' }),
  ).toBeVisible();
  await expect(page.locator('.state-view')).toContainText(
    'No live lab is connected',
  );
  await expect(page.locator('.state-view')).toContainText(
    '17/17 rooms pass on each stack',
  );
  await expect(page.locator('.state-view')).toContainText(
    'AP-registration-loss trigger remains unreproduced',
  );
});

test('band inspector describes native measurements and bounded qualification', async ({
  page,
}) => {
  await page.goto(explorerPath);
  await page.getByRole('button', { name: 'Reference optimizer' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Band steering', exact: true })
    .click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('client_nl80211_received_scan');
  await expect(dialog).toContainText('12 required band transitions per stack');
  await expect(dialog).toContainText('not vendor-autonomous optimization');
  await expect(
    dialog.getByRole('link', {
      name: 'band-steering.md',
      exact: true,
    }),
  ).toHaveAttribute(
    'href',
    new RegExp(
      `/blob/${revision}/doc/easymesh/reference/optimizer/band-steering.md$`,
    ),
  );
});

test('new band rooms remain disconnected static previews and the manual explains them', async ({
  page,
}) => {
  const requests: string[] = [];
  const errors: string[] = [];
  page.on('request', (requested) => requests.push(requested.url()));
  page.on('pageerror', (error) => errors.push(error.message));
  for (const room of [
    'band-upgrade-24-5',
    'band-upgrade-5-6',
    'band-ap-counter-roam',
  ]) {
    await page.goto(`/meta-cmf-bananapi-vcpe/viewer/?world=${room}`);
    await expect(page.locator('#worldmeta')).toContainText(room);
    await expect(page.locator('#world option')).toHaveCount(17);
    await expect(page.locator('meta[name="room-viewer-mode"]')).toHaveAttribute(
      'content',
      'no-connect',
    );
    await expect(page.locator('#err')).toBeHidden();
    await page.locator('#play').click();
    await expect(page.locator('#play')).toHaveText('Pause');
    await page.locator('#play').click();
    await expect(page.locator('#play')).toHaveText('Play');
  }
  await page.goto('/meta-cmf-bananapi-vcpe/viewer/manual.html#band-steering');
  await expect(
    page.getByRole('heading', { name: 'Dedicated band-steering rooms' }),
  ).toBeVisible();
  await expect(page.locator('#optimizer')).toContainText(
    'Public Pages is a disconnected preview.',
  );
  await page.locator('#manualSearch').fill('band-upgrade');
  await expect(page.locator('#optimizer')).toBeVisible();
  await expect(page.locator('#quick-start')).toBeHidden();
  expect(
    requests.every(
      (address) => new URL(address).origin === 'http://127.0.0.1:4178',
    ),
  ).toBe(true);
  expect(
    requests.some((address) => new URL(address).pathname.startsWith('/api/')),
  ).toBe(false);
  expect(errors).toEqual([]);
});

test('landing and explorer navigation preserve sibling viewer and manual URLs', async ({
  page,
}) => {
  await page.goto('/meta-cmf-bananapi-vcpe/');
  await expect(page.getByRole('link', { name: /Room viewer/ })).toHaveAttribute(
    'href',
    'viewer/?world=home-a-private-client-room-walk',
  );
  await expect(page.getByRole('link', { name: /Manual/ })).toHaveAttribute(
    'href',
    'viewer/manual.html',
  );
  await page.getByRole('link', { name: /System explorer/ }).click();
  await expect(page).toHaveURL(new RegExp(explorerPath));
  const navigation = page.getByRole('navigation', {
    name: 'Lab documentation',
  });
  await expect(
    navigation.getByRole('link', { name: 'Room viewer', exact: true }),
  ).toHaveJSProperty(
    'href',
    'http://127.0.0.1:4178/meta-cmf-bananapi-vcpe/viewer/',
  );
  await expect(
    navigation.getByRole('link', { name: 'Manual', exact: true }),
  ).toHaveJSProperty(
    'href',
    'http://127.0.0.1:4178/meta-cmf-bananapi-vcpe/viewer/manual.html',
  );
});

test('mobile layout keeps page navigation and inspectors usable', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(explorerPath);
  for (const tab of [
    'Architecture',
    'Network topology',
    'Protocol paths',
    'Current state',
  ]) {
    await page.getByRole('tab', { name: tab, exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  }
  await page.getByRole('tab', { name: 'Architecture', exact: true }).click();
  await page.locator('.inner-block').first().click();
  await expect
    .poll(async () => {
      const position = await page.getByRole('dialog').boundingBox();
      return position ? position.x + position.width : Infinity;
    })
    .toBeLessThanOrEqual(391);
  const bounds = await page.getByRole('dialog').boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(391);
  await page.screenshot({
    path: testInfo.outputPath('inspector-mobile.png'),
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(
    page.getByRole('navigation', { name: 'Lab documentation' }),
  ).toBeVisible();
});
