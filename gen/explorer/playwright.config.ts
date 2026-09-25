import { defineConfig } from '@playwright/test';

const browserEnvironment = { ...process.env };
delete browserEnvironment.DISPLAY;

export default defineConfig({
  testDir: './tests',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  // In CI, failures also become GitHub annotations (readable without the logs).
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4178',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      env: browserEnvironment,
      executablePath: process.env.CHROMIUM_PATH,
      args: [
        '--num-raster-threads=2',
        '--ozone-platform=headless',
        '--enable-unsafe-swiftshader',
        '--use-gl=angle',
        '--use-angle=swiftshader',
      ],
    },
  },
  webServer: {
    command: 'python3 tests/serve-pages.py',
    url: 'http://127.0.0.1:4178/meta-cmf-bananapi-vcpe/explorer/',
    reuseExistingServer: false,
    timeout: 15000,
  },
});
