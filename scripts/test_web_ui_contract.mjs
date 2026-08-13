#!/usr/bin/env node

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../docs/index.html', import.meta.url), 'utf8');
const events = JSON.parse(readFileSync(new URL('../docs/events.json', import.meta.url), 'utf8'));
const generator = readFileSync(new URL('./generate_calendar.py', import.meta.url), 'utf8');

const categoryToCssToken = {
    peer_support: 'peer-support',
    fitness_wellness: 'fitness',
    events: 'events',
    arts_culture: 'arts',
    parks_nature: 'parks',
    food_farms: 'food',
    social_activities: 'social',
    discount_programs: 'discounts',
    transportation: 'transportation',
};

function relativeLuminance(hex) {
    const channels = hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255);
    const linear = channels.map(value => value <= 0.04045
        ? value / 12.92
        : ((value + 0.055) / 1.055) ** 2.4);
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(first, second) {
    const a = relativeLuminance(first);
    const b = relativeLuminance(second);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function cssToken(name) {
    const match = html.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`, 'i'));
    assert.ok(match, `Missing CSS token --${name}`);
    return match[1].toUpperCase();
}

function pythonPalette() {
    const block = generator.match(/CATEGORY_COLORS\s*=\s*\{([\s\S]*?)^\}/m);
    assert.ok(block, 'Missing CATEGORY_COLORS in generator');
    return Object.fromEntries(Array.from(
        block[1].matchAll(/"([a-z_]+)":\s*"(#[0-9A-Fa-f]{6})"/g),
        match => [match[1], match[2].toUpperCase()],
    ));
}

function extractFunction(name) {
    const match = html.match(new RegExp(`^        function ${name}\\([\\s\\S]*?^        \\}`, 'm'));
    assert.ok(match, `Missing function ${name}`);
    return match[0].replace(/^ {8}/gm, '');
}

test('accent and category palettes meet AA and stay in sync', () => {
    assert.ok(contrastRatio(cssToken('accent'), '#FFFFFF') >= 4.5);
    assert.ok(contrastRatio(cssToken('success'), '#FFFFFF') >= 4.5);
    const sourcePalette = pythonPalette();
    for (const [category, token] of Object.entries(categoryToCssToken)) {
        const color = cssToken(token);
        assert.ok(contrastRatio(color, '#FFFFFF') >= 4.5, `${category} fails 4.5:1`);
        assert.equal(events.colors[category].toUpperCase(), color, `${category} JSON color drift`);
        assert.equal(sourcePalette[category], color, `${category} generator color drift`);
    }
});

test('responsive shell never blocks an orientation or document scrolling', () => {
    assert.doesNotMatch(html, /landscape-overlay|rotate your device/i);
    assert.doesNotMatch(html, /^\s*height:\s*100vh/m);
    assert.doesNotMatch(html, /\.left-panel\s*\{[^}]*overflow-y:\s*hidden/s);
    assert.match(html, /@media \(max-width: 1000px\), \(max-height: 600px\)/);
});

test('document and view semantics expose complete keyboard patterns', () => {
    assert.equal((html.match(/<h1\b/g) || []).length, 1);
    assert.match(html, /id="grid-tab"[^>]*aria-selected="true"[^>]*tabindex="0"/);
    assert.match(html, /id="list-tab"[^>]*tabindex="-1"/);
    assert.match(html, /\['ArrowLeft', 'ArrowRight', 'Home', 'End'\]/);
    assert.match(html, /id="filter-btn"[^>]*aria-expanded="false"[^>]*aria-controls="filter-panel"/);
    assert.doesNotMatch(html, /role="application"|role="grid"|role="gridcell"|role="columnheader"/);
});

test('interactive event surfaces use native controls', () => {
    assert.match(html, /<button type="button" class="event-item"/);
    assert.match(html, /<button type="button" class="day-popup-event"/);
    assert.match(html, /<button type="button" class="seasonal-event-card"/);
    assert.match(html, /<button type="button" class="mobile-day-trigger"/);
    assert.match(html, /aria-label="View all \$\{dayEvents\.length\}[\s\S]*\$\{weekday\}/);
    assert.match(html, /popup\.setAttribute\('role', 'dialog'\)/);
    assert.match(html, /popup\.querySelector\('\.day-popup-close'\)\.focus\(\)/);
    assert.doesNotMatch(html, /\.filter-pill input\s*\{\s*display:\s*none/);
});

test('resource formatting is human-readable and phone actions stay independent', () => {
    const context = {};
    vm.runInNewContext([
        extractFunction('humanizeFieldKey'),
        extractFunction('formatHours'),
        extractFunction('phoneHref'),
    ].join('\n'), context);

    assert.equal(context.formatHours({ crisis_line: '24/7', walk_in: '8am-5pm' }), 'Crisis line: 24/7; Walk in: 8am-5pm');
    assert.equal(context.formatHours(['Weekdays', 'Weekends']), 'Weekdays; Weekends');
    assert.equal(context.formatHours(null), '');
    assert.equal(context.phoneHref('(503) 655-8585'), 'tel:5036558585');
    assert.equal(context.phoneHref('+1 503 555 0100 ext. 42'), 'tel:+15035550100;ext=42');

    assert.match(html, /<article class="resource-card">/);
    assert.match(html, /class="resource-phone" href=/);
    assert.doesNotMatch(html, /class="resource-card"[^>]*role="button"/);
});

test('copy and modal contracts preserve labels and isolate the background', () => {
    assert.match(html, /this\.textContent = 'Copy Calendar Link'/);
    assert.doesNotMatch(html, /this\.textContent = 'Subscribe'/);
    assert.match(html, /pageContent\.inert = hasOpenModal/);
    assert.match(html, /openModalOverlays\.size > 0/);
    assert.match(html, /setModalState\(modal, true\)/);
    assert.match(html, /restoreFocus\(eventModalTrigger, 'grid-tab'\)/);
});
