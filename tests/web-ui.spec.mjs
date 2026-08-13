import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const FIXED_NOW = new Date('2026-08-13T12:00:00-07:00');
const WCAG_21_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function installFixedClock(page) {
    const timestamp = FIXED_NOW.getTime();
    await page.addInitScript(({ now }) => {
        const NativeDate = Date;
        class FixedDate extends NativeDate {
            constructor(...args) {
                super(...(args.length ? args : [now]));
            }
            static now() { return now; }
        }
        FixedDate.parse = NativeDate.parse;
        FixedDate.UTC = NativeDate.UTC;
        Object.setPrototypeOf(FixedDate, NativeDate);
        window.Date = FixedDate;
    }, { now: timestamp });
}

async function installDeterministicServices(page) {
    await page.route('https://api.open-meteo.com/**', route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
            current: {
                temperature_2m: 63,
                weather_code: 61,
                cloud_cover: 80,
                is_day: 1
            },
            daily: {
                sunrise: ['2026-08-13T06:08'],
                sunset: ['2026-08-13T20:19']
            }
        })
    }));

    await page.route('https://cdnjs.cloudflare.com/**', route => route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: 'window.THREE = {};'
    }));

    await page.route('https://cdn.jsdelivr.net/**', route => route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: `
            window.__vantaOptions = [];
            window.VANTA = {
                CLOUDS: function(options) {
                    var state = Object.assign({}, options);
                    window.__vantaOptions.push(Object.assign({}, state));
                    return {
                        req: null,
                        setOptions: function(next) {
                            Object.assign(state, next);
                            window.__vantaOptions.push(Object.assign({}, state));
                        },
                        destroy: function() {}
                    };
                }
            };
        `
    }));
}

async function openCalendar(page, viewport) {
    await page.setViewportSize(viewport);
    await installFixedClock(page);
    await installDeterministicServices(page);
    await page.goto('/index.html');
    await expect(page.locator('.loading-indicator')).toHaveCount(0);
    await expect(page.locator('#month-label')).toHaveText('August 2026');
    await expect(page.locator('.grid-day.has-events').first()).toBeVisible();
}

async function expectWcag21AA(page, state) {
    const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA_TAGS).analyze();
    const summary = results.violations.map(violation => ({
        id: violation.id,
        impact: violation.impact,
        targets: violation.nodes.map(node => node.target)
    }));
    expect(results.violations, `${state}: ${JSON.stringify(summary, null, 2)}`).toEqual([]);
}

test('desktop tabs, panels, dialogs, and accessibility work in a rendered browser', async ({ page }) => {
    await openCalendar(page, { width: 1280, height: 900 });

    const calendarTab = page.getByRole('tab', { name: 'Calendar' });
    const listTab = page.getByRole('tab', { name: 'List' });
    const resourcesTab = page.getByRole('tab', { name: 'Resources' });

    await calendarTab.click();
    await calendarTab.press('ArrowRight');
    await expect(listTab).toBeFocused();
    await expect(listTab).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('[role="tabpanel"]:not([hidden])')).toHaveCount(1);

    await listTab.press('End');
    await expect(resourcesTab).toBeFocused();
    await expect(resourcesTab).toHaveAttribute('aria-selected', 'true');
    await resourcesTab.press('Home');
    await expect(calendarTab).toBeFocused();
    await expect(calendarTab).toHaveAttribute('aria-selected', 'true');

    await expectWcag21AA(page, 'desktop calendar');

    const aboutButton = page.getByRole('button', { name: 'About this site' });
    await aboutButton.click();
    const aboutOverlay = page.locator('#about-modal-overlay');
    await expect(aboutOverlay).toHaveClass(/active/);
    await expect(aboutOverlay.locator('.event-modal-close')).toBeFocused();
    await expect(page.locator('#page-content')).toHaveAttribute('aria-hidden', 'true');
    await expectWcag21AA(page, 'about dialog');
    await page.keyboard.press('Escape');
    await expect(aboutOverlay).not.toHaveClass(/active/);
    await expect(aboutButton).toBeFocused();

    await page.getByRole('tab', { name: 'Seasonal' }).click();
    const seasonalCard = page.locator('#seasonal-view .seasonal-event-card').first();
    await seasonalCard.click();
    const seasonalOverlay = page.locator('body > .event-modal-overlay.active').last();
    const seasonalClose = seasonalOverlay.locator('.event-modal-close');
    await expect(seasonalOverlay.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    await expect(seasonalClose).toBeFocused();
    await expect(page.locator('#page-content')).toHaveAttribute('inert', '');
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(seasonalClose).toBeFocused();
    await expectWcag21AA(page, 'seasonal event dialog');
    await page.keyboard.press('Escape');
    await expect(seasonalOverlay).toHaveCount(0);
    await expect(seasonalCard).toBeFocused();
});

test('portrait mobile exposes complete day agendas and restores focus', async ({ page }) => {
    await openCalendar(page, { width: 390, height: 844 });

    const layout = await page.evaluate(() => ({
        overflowY: getComputedStyle(document.body).overflowY,
        scrollHeight: document.documentElement.scrollHeight,
        innerHeight,
        orientationBlockers: document.querySelectorAll('.landscape-overlay, .orientation-overlay').length
    }));
    expect(layout.overflowY).not.toBe('hidden');
    expect(layout.scrollHeight).toBeGreaterThan(layout.innerHeight);
    expect(layout.orientationBlockers).toBe(0);

    const dayTrigger = page.locator('.mobile-day-trigger:visible').first();
    await expect(dayTrigger).toHaveAccessibleName(/View all \d+ events? on (Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday), August \d+, 2026/);
    await dayTrigger.click();

    const popup = page.locator('.day-popup');
    await expect(popup).toBeVisible();
    await expect(popup.locator('.day-popup-close')).toBeFocused();
    await expectWcag21AA(page, 'mobile day agenda');
    await page.keyboard.press('Escape');
    await expect(popup).toHaveCount(0);
    await expect(dayTrigger).toBeFocused();

    await dayTrigger.click();
    await popup.locator('.day-popup-event').first().click();
    const eventOverlay = page.locator('#event-modal-overlay');
    await expect(eventOverlay).toHaveClass(/active/);
    await expect(eventOverlay.locator('#modal-close')).toBeFocused();
    await expect(page.locator('#page-content')).toHaveAttribute('inert', '');
    await expectWcag21AA(page, 'mobile event dialog');
    await page.keyboard.press('Escape');
    await expect(eventOverlay).not.toHaveClass(/active/);
    await expect(dayTrigger).toBeFocused();

    const undersizedControls = await page.locator(
        '.month-nav > button:visible, .view-tab:visible, .filter-btn:visible, .print-btn:visible'
    ).evaluateAll(elements => elements
        .map(element => {
            const rect = element.getBoundingClientRect();
            return { label: element.getAttribute('aria-label') || element.textContent.trim(), width: rect.width, height: rect.height };
        })
        .filter(control => control.width < 43.5 || control.height < 43.5));
    expect(undersizedControls).toEqual([]);

    await page.locator('.contact-section').scrollIntoViewIfNeeded();
    await expect(page.locator('.contact-section')).toBeVisible();
});

for (const viewport of [
    { width: 1280, height: 560, label: 'wide short' },
    { width: 1024, height: 600, label: 'height breakpoint' }
]) {
    test(`${viewport.label} landscape uses normal document flow instead of clipping content`, async ({ page }) => {
        await openCalendar(page, { width: viewport.width, height: viewport.height });

        const layout = await page.evaluate(() => ({
            mainDisplay: getComputedStyle(document.querySelector('.main-content')).display,
            overflowY: getComputedStyle(document.body).overflowY,
            scrollHeight: document.documentElement.scrollHeight,
            innerHeight
        }));
        expect(layout.mainDisplay).toBe('flex');
        expect(layout.overflowY).not.toBe('hidden');
        expect(layout.scrollHeight).toBeGreaterThan(layout.innerHeight);

        await page.locator('.contact-section').scrollIntoViewIfNeeded();
        await expect(page.locator('.contact-section')).toBeVisible();
        await expectWcag21AA(page, `${viewport.label} landscape calendar`);
    });
}

for (const viewport of [
    { width: 320, height: 568, label: 'small portrait' },
    { width: 390, height: 844, label: 'phone portrait' },
    { width: 768, height: 1024, label: 'tablet portrait' },
    { width: 844, height: 390, label: 'phone landscape' }
]) {
    test(`${viewport.label} stays in one-column flow without horizontal overflow`, async ({ page }) => {
        await openCalendar(page, { width: viewport.width, height: viewport.height });
        const layout = await page.evaluate(() => {
            const clientWidth = document.documentElement.clientWidth;
            const panels = [...document.querySelectorAll('.left-panel, .right-panel')].map(panel => {
                const rect = panel.getBoundingClientRect();
                return { left: rect.left, right: rect.right, width: rect.width };
            });
            return {
                clientWidth,
                scrollWidth: document.documentElement.scrollWidth,
                mainDisplay: getComputedStyle(document.querySelector('.main-content')).display,
                mainDirection: getComputedStyle(document.querySelector('.main-content')).flexDirection,
                panels
            };
        });

        expect(layout.mainDisplay).toBe('flex');
        expect(layout.mainDirection).toBe('column');
        expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1);
        for (const panel of layout.panels) {
            expect(panel.left).toBeGreaterThanOrEqual(-1);
            expect(panel.right).toBeLessThanOrEqual(layout.clientWidth + 1);
            expect(panel.width).toBeLessThanOrEqual(layout.clientWidth + 1);
        }
    });
}

test('resource phone actions remain independent from detail dialogs', async ({ page }) => {
    await openCalendar(page, { width: 1280, height: 900 });
    await page.getByRole('tab', { name: 'Resources' }).click();

    const detailsButton = page.getByRole('button', {
        name: 'View details for Clackamas County Crisis & Walk-In Mental Health Center'
    });
    const crisisCard = detailsButton.locator('xpath=ancestor::article');
    const phoneLink = crisisCard.locator('.resource-phone');
    await expect(crisisCard).toContainText('Crisis line: 24/7, every day of the year; Walk in: Mon-Fri 9am-7pm');
    await expect(phoneLink).toBeVisible();
    await expect(phoneLink).toHaveAttribute('href', 'tel:5036558585');
    await expect(crisisCard.locator('button.resource-details-btn')).toHaveCount(1);
    await expect(crisisCard.locator('a.resource-phone')).toHaveCount(1);
    await phoneLink.evaluate(element => element.addEventListener('click', event => event.preventDefault(), { once: true }));
    await phoneLink.click();
    await expect(page.locator('#event-modal-overlay')).not.toHaveClass(/active/);

    await detailsButton.click();
    const eventOverlay = page.locator('#event-modal-overlay');
    await expect(eventOverlay).toHaveClass(/active/);
    await expect(eventOverlay.locator('#modal-close')).toBeFocused();
    await expectWcag21AA(page, 'resource detail dialog');
    await page.keyboard.press('Escape');
    await expect(detailsButton).toBeFocused();
});

test.describe('reduced motion', () => {
    test.use({ reducedMotion: 'reduce' });

    test('keeps Vanta frozen and rain particles clear on initial render', async ({ page }) => {
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await openCalendar(page, { width: 390, height: 844 });
        await page.waitForTimeout(200);

        const state = await page.evaluate(() => {
            const canvas = document.querySelector('.sky-effect-particles');
            const context = canvas.getContext('2d');
            const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
            let hasParticlePixel = false;
            for (let index = 3; index < pixels.length; index += 4) {
                if (pixels[index] !== 0) {
                    hasParticlePixel = true;
                    break;
                }
            }
            return {
                reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
                speeds: (window.__vantaOptions || []).map(options => options.speed),
                hasParticlePixel
            };
        });

        expect(state.reduced).toBe(true);
        expect(state.speeds.length).toBeGreaterThan(0);
        expect(state.speeds.every(speed => speed === 0)).toBe(true);
        expect(state.hasParticlePixel).toBe(false);
    });
});
