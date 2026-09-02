#!/usr/bin/env node

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';

// CI validates a freshly generated feed in output/ before anything is
// published, so the feed path is overridable; it defaults to the published one.
function argValue(flag, fallback) {
    const index = process.argv.indexOf(flag);
    if (index === -1) return fallback;
    const value = process.argv[index + 1];
    if (!value || value.startsWith('--')) {
        throw new Error(`${flag} requires a path`);
    }
    return pathToFileURL(resolve(value));
}

const indexUrl = argValue('--index', new URL('../docs/index.html', import.meta.url));
const feedUrl = argValue('--feed', new URL('../docs/events.json', import.meta.url));
const html = readFileSync(indexUrl, 'utf8');
const feed = JSON.parse(readFileSync(feedUrl, 'utf8'));
const helperStart = html.indexOf('const resolvedWeekdayNumbers');
const helperEnd = html.indexOf('// Generate all events for a month', helperStart);
assert.ok(helperStart >= 0 && helperEnd > helperStart, 'resolved schedule helpers must be present');

const context = vm.createContext({});
vm.runInContext(`${html.slice(helperStart, helperEnd)}
    globalThis.scheduleTestApi = { localDateFromIso, resolvedScheduleDates };`, context);
const { localDateFromIso, resolvedScheduleDates } = context.scheduleTestApi;

function datesOf(schedule, year = 2026, month = 7) {
    return Array.from(resolvedScheduleDates(schedule, year, month), occurrence => {
        const date = occurrence.date;
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    });
}

const fosterNightRide = {
    type: 'recurring',
    frequency: 'weekly',
    interval: 2,
    weekdays: ['TU'],
    month_weeks: [],
    anchor_date: '2026-08-04',
    until_date: '2026-08-31',
    start_time: '19:00',
    end_time: '20:00',
    end_day_offset: 0
};
assert.deepEqual(datesOf(fosterNightRide), ['2026-08-04', '2026-08-18']);

const greshamMusic = {
    ...fosterNightRide,
    weekdays: ['WE'],
    anchor_date: '2026-07-01'
};
assert.deepEqual(datesOf(greshamMusic), ['2026-08-12', '2026-08-26']);

const greshamMovies = {
    ...fosterNightRide,
    frequency: 'monthly',
    interval: 1,
    weekdays: ['MO'],
    month_weeks: [1, 3],
    anchor_date: '2026-08-01'
};
assert.deepEqual(datesOf(greshamMovies), ['2026-08-03', '2026-08-17']);

const lastMonday = {
    ...greshamMovies,
    month_weeks: [-1]
};
assert.deepEqual(datesOf(lastMonday), ['2026-08-31']);

const inclusiveBounds = {
    ...fosterNightRide,
    interval: 1,
    weekdays: ['MO'],
    anchor_date: '2026-08-10',
    until_date: '2026-08-24'
};
assert.deepEqual(datesOf(inclusiveBounds), ['2026-08-10', '2026-08-17', '2026-08-24']);

const fixed = {
    type: 'fixed',
    occurrences: [
        { start_date: '2026-08-15', end_date: '2026-08-16', all_day: true },
        {
            start_date: '2026-08-29', end_date: '2026-08-29', all_day: false,
            start_time: '20:00', end_time: '00:30', end_day_offset: 1
        },
        { start_date: '2026-09-05', end_date: '2026-09-05', all_day: true }
    ]
};
const fixedAugust = Array.from(resolvedScheduleDates(fixed, 2026, 7));
assert.deepEqual(datesOf(fixed), ['2026-08-15', '2026-08-16', '2026-08-29']);
assert.equal(fixedAugust[0].allDay, true);
assert.equal(fixedAugust[2].startTime, '20:00');
assert.equal(fixedAugust[2].endDayOffset, 1);

assert.equal(localDateFromIso('2026-02-29'), null, 'invalid civil dates must fail closed');
assert.doesNotMatch(html, /function\s+parseSchedule\s*\(/);
assert.doesNotMatch(html, /function\s+parseFixedDate\s*\(/);
assert.doesNotMatch(html, /function\s+isMonthInSeasonalRange\s*\(/);
assert.doesNotMatch(html, /\bgetScheduleDates\s*\(/);
assert.doesNotMatch(html, /if\s*\(entry\.dates\s*\|\|\s*entry\.date\)\s*continue/,
    'entry-level dates must not hide independently scheduled child programs');

function programSchedule(entryId, programName) {
    const entry = feed.events.find(item => item.id === entryId);
    assert.ok(entry, `missing feed entry ${entryId}`);
    const program = entry.programs.find(item => item.name === programName);
    assert.ok(program, `missing ${entryId} program ${programName}`);
    return program.resolved_schedule;
}

assert.equal(feed.schedule_schema_version, 1);
assert.deepEqual(
    datesOf(programSchedule('shift-to-bikes', 'Foster Night Ride')),
    ['2026-08-04', '2026-08-18']
);
assert.deepEqual(
    datesOf(programSchedule('gresham-senior-center', 'Movie Madness')),
    ['2026-08-03', '2026-08-17']
);

console.log(`web schedule parity: 23 assertions passed against ${feedUrl.pathname}`);
