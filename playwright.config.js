const { defineConfig } = require('@playwright/test');
const python = process.env.ECHOSENSE_PYTHON || 'python';

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['line'],
    ['html', { outputFolder: 'artifacts/guardian/playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `PYTHONPATH=src ${python} -m uvicorn echosense.product_app:app --host 127.0.0.1 --port 8765`,
    url: 'http://127.0.0.1:8765/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
