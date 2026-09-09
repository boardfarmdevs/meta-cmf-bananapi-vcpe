import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4178',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH,
      args: ['--num-raster-threads=2', '--disable-gpu'],
    },
  },
  webServer: {
    command: 'python3 tests/serve-pages.py',
    url: 'http://127.0.0.1:4178/meta-cmf-bananapi-vcpe/explorer/',
    reuseExistingServer: false,
    timeout: 15000,
  },
});
