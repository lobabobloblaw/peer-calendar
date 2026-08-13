import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const SkyEffect = require('../docs/sky-effect.js');

function createMotionQuery(initialMatches) {
    const listeners = new Set();

    return {
        matches: initialMatches,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener(type, listener) {
            if (type === 'change') listeners.add(listener);
        },
        removeEventListener(type, listener) {
            if (type === 'change') listeners.delete(listener);
        },
        setMatches(matches) {
            this.matches = matches;
            for (const listener of listeners) {
                listener({ matches, media: this.media });
            }
        },
        listenerCount() {
            return listeners.size;
        }
    };
}

function installBrowserMocks(motionQuery) {
    let nextAnimationId = 1;
    const activeAnimations = new Set();
    const documentListeners = new Map();
    const context = { clearRect() {} };

    function createElement(tagName) {
        const element = {
            tagName: tagName.toUpperCase(),
            className: '',
            classList: { add() {} },
            style: {},
            parentNode: null,
            appendChild(child) {
                child.parentNode = this;
            },
            removeChild(child) {
                child.parentNode = null;
            }
        };
        if (tagName === 'canvas') {
            element.getContext = () => context;
        }
        return element;
    }

    const documentMock = {
        hidden: false,
        head: { appendChild() {} },
        createElement,
        getElementById() { return null; },
        querySelector() { return null; },
        addEventListener(type, listener) {
            documentListeners.set(type, listener);
        },
        removeEventListener(type, listener) {
            if (documentListeners.get(type) === listener) documentListeners.delete(type);
        }
    };

    const windowMock = {
        innerWidth: 1024,
        innerHeight: 768,
        matchMedia() { return motionQuery; },
        addEventListener() {},
        removeEventListener() {}
    };

    globalThis.document = documentMock;
    globalThis.window = windowMock;
    globalThis.requestAnimationFrame = () => {
        const id = nextAnimationId++;
        activeAnimations.add(id);
        return id;
    };
    globalThis.cancelAnimationFrame = id => activeAnimations.delete(id);

    return { activeAnimations, documentMock, windowMock };
}

function createContainer() {
    return {
        offsetWidth: 1024,
        offsetHeight: 768,
        children: [],
        appendChild(child) {
            child.parentNode = this;
            this.children.push(child);
        },
        removeChild(child) {
            child.parentNode = null;
            this.children = this.children.filter(candidate => candidate !== child);
        }
    };
}

test('reduced-motion prevents initial particles and responds to live preference changes', async () => {
    const motionQuery = createMotionQuery(true);
    const { activeAnimations, documentMock, windowMock } = installBrowserMocks(motionQuery);
    const vantaSpeeds = [];

    windowMock.VANTA = globalThis.VANTA = { CLOUDS() {} };

    const sky = new SkyEffect(createContainer(), {
        autoFetchWeather: false,
        autoLoadDeps: false,
        enableFog: false,
        updateThemeColor: false,
        respectReducedMotion: true
    });

    await sky.init();
    sky._vantaEffect = {
        setOptions(options) {
            if (Object.hasOwn(options, 'speed')) vantaSpeeds.push(options.speed);
        },
        destroy() {}
    };

    sky.setWeather({ weatherCode: 61, cloudCover: 80 });
    assert.equal(activeAnimations.size, 0, 'initial rain animation is suppressed');
    assert.equal(sky._particles.length, 0, 'no initial particles are created');
    assert.equal(vantaSpeeds.at(-1), 0, 'Vanta receives a zero speed');
    assert.equal(motionQuery.listenerCount(), 1, 'the live preference listener is attached');

    motionQuery.setMatches(false);
    assert.equal(activeAnimations.size, 1, 'particles start when motion reduction is removed');
    assert.equal(sky._currentParticleType, 'rain');
    assert.ok(vantaSpeeds.at(-1) > 0, 'Vanta resumes at the calculated speed');

    motionQuery.setMatches(true);
    assert.equal(activeAnimations.size, 0, 'particles stop when motion reduction is requested');
    assert.equal(sky._particles.length, 0, 'stopped particles are cleared');
    assert.equal(vantaSpeeds.at(-1), 0, 'Vanta stops on a live preference change');

    motionQuery.setMatches(false);
    assert.equal(activeAnimations.size, 1, 'particles can resume after another live change');

    documentMock.hidden = true;
    sky._onVisibilityChange();
    assert.equal(activeAnimations.size, 0, 'particles stop while the page is hidden');

    documentMock.hidden = false;
    sky._onVisibilityChange();
    assert.equal(activeAnimations.size, 1, 'particles resume when the page becomes visible');

    sky.destroy();
    assert.equal(activeAnimations.size, 0);
    assert.equal(motionQuery.listenerCount(), 0, 'the preference listener is removed on destroy');
});
