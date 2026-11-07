import { defineConfig } from '@playwright/test';
const production = process.env.TEST_PRODUCTION === '1';
const port = production ? 4173 : 5173;
export default defineConfig({
  testDir: './tests', testMatch: '*.spec.ts', timeout: 60000, workers: 1,
  use: { baseURL: `http://127.0.0.1:${port}`, viewport: { width: 1440, height: 1000 }, launchOptions: { args: ['--enable-unsafe-swiftshader'] } },
  webServer: [
    { command: 'npm start', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: !process.env.CI },
    { command: `npm run ${production ? 'preview' : 'dev:web'} -- --port ${port} --strictPort`, url: `http://127.0.0.1:${port}`, reuseExistingServer: !process.env.CI },
  ],
  reporter: 'list',
});
