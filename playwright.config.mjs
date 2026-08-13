import { defineConfig } from '@playwright/test';

export default defineConfig({
    testDir: './tests',
    fullyParallel: false,
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    timeout: 45_000,
    expect: { timeout: 10_000 },
    reporter: process.env.CI ? 'github' : 'list',
    use: {
        baseURL: 'http://127.0.0.1:4173',
        locale: 'en-US',
        timezoneId: 'America/Los_Angeles',
        trace: 'retain-on-failure'
    },
    webServer: {
        command: 'python3 -m http.server 4173 --directory docs',
        url: 'http://127.0.0.1:4173/index.html',
        reuseExistingServer: !process.env.CI,
        timeout: 15_000
    }
});
