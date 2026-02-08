/**
 * SkyEffect - Weather-reactive animated sky background
 *
 * Creates a layered sky background with Vanta.js clouds, CSS gradients,
 * fog overlay, and weather particles (rain/snow). Driven by real weather
 * data from the Open-Meteo API with time-of-day color palettes.
 *
 * @example
 *   const sky = new SkyEffect('#sky-container');
 *   await sky.init();
 *
 * @license MIT
 */
(function (root, factory) {
    if (typeof exports === 'object' && typeof module !== 'undefined') {
        module.exports = factory();
    } else if (typeof define === 'function' && define.amd) {
        define(factory);
    } else {
        root.SkyEffect = factory();
    }
}(typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // ========================================================================
    // Module-scoped utilities (not exported)
    // ========================================================================

    function darkenColor(hex, amount) {
        const r = Math.max(0, ((hex >> 16) & 0xff) * (1 - amount));
        const g = Math.max(0, ((hex >> 8) & 0xff) * (1 - amount));
        const b = Math.max(0, (hex & 0xff) * (1 - amount));
        return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b);
    }

    function lightenColor(hex, amount) {
        const r = Math.min(255, ((hex >> 16) & 0xff) + (255 - ((hex >> 16) & 0xff)) * amount);
        const g = Math.min(255, ((hex >> 8) & 0xff) + (255 - ((hex >> 8) & 0xff)) * amount);
        const b = Math.min(255, (hex & 0xff) + (255 - (hex & 0xff)) * amount);
        return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b);
    }

    function blendColors(color1, color2, amount) {
        const r1 = (color1 >> 16) & 0xff, g1 = (color1 >> 8) & 0xff, b1 = color1 & 0xff;
        const r2 = (color2 >> 16) & 0xff, g2 = (color2 >> 8) & 0xff, b2 = color2 & 0xff;
        const r = Math.round(r1 + (r2 - r1) * amount);
        const g = Math.round(g1 + (g2 - g1) * amount);
        const b = Math.round(b1 + (b2 - b1) * amount);
        return (r << 16) | (g << 8) | b;
    }

    function parseTimeToMins(timeStr) {
        if (!timeStr) return null;
        const [h, m] = timeStr.split(':').map(Number);
        return h * 60 + m;
    }

    // ---- Solar altitude calculation (simplified NOAA) ----

    function getSolarAltitude(lat, lon, date) {
        var dayOfYear = Math.floor((date - new Date(date.getFullYear(), 0, 0)) / 86400000);
        var hourUTC = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600;

        // Fractional year in radians
        var gamma = 2 * Math.PI / 365 * (dayOfYear - 1 + (hourUTC - 12) / 24);

        // Equation of time (minutes)
        var eqTime = 229.18 * (0.000075
            + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
            - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma));

        // Solar declination (radians)
        var decl = 0.006918
            - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma)
            - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma)
            - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);

        // True solar time (minutes)
        var timeOffset = eqTime + 4 * lon;
        var trueSolar = hourUTC * 60 + timeOffset;

        // Hour angle (degrees)
        var ha = (trueSolar / 4) - 180;
        var haRad = ha * Math.PI / 180;

        // Latitude in radians
        var latRad = lat * Math.PI / 180;

        // Solar altitude angle
        var sinAlt = Math.sin(latRad) * Math.sin(decl) + Math.cos(latRad) * Math.cos(decl) * Math.cos(haRad);
        return Math.asin(Math.max(-1, Math.min(1, sinAlt))) * 180 / Math.PI;
    }

    function getSunDirection(nowMins, sunriseMins, sunsetMins) {
        var solarNoon = (sunriseMins + sunsetMins) / 2;
        return nowMins < solarNoon ? 'morning' : 'evening';
    }

    // ---- Gradient interpolation utilities ----

    function gradientStopsToCSS(stops) {
        var parts = [];
        for (var i = 0; i < stops.length; i++) {
            var hex = '#' + ('000000' + stops[i][0].toString(16)).slice(-6);
            parts.push(hex + ' ' + stops[i][1] + '%');
        }
        return 'linear-gradient(to bottom, ' + parts.join(', ') + ')';
    }

    function blendGradientStops(stopsA, stopsB, t) {
        var result = [];
        var len = Math.min(stopsA.length, stopsB.length);
        for (var i = 0; i < len; i++) {
            var color = blendColors(stopsA[i][0], stopsB[i][0], t);
            var pos = stopsA[i][1] + (stopsB[i][1] - stopsA[i][1]) * t;
            result.push([color, Math.round(pos)]);
        }
        return result;
    }

    function blendRGB(a, b, t) {
        return [
            Math.round(a[0] + (b[0] - a[0]) * t),
            Math.round(a[1] + (b[1] - a[1]) * t),
            Math.round(a[2] + (b[2] - a[2]) * t)
        ];
    }

    function interpolateWaypoints(angle, waypoints) {
        // waypoints sorted by ascending angle
        if (angle <= waypoints[0].angle) {
            return { lower: waypoints[0], upper: waypoints[0], t: 0 };
        }
        if (angle >= waypoints[waypoints.length - 1].angle) {
            var last = waypoints[waypoints.length - 1];
            return { lower: last, upper: last, t: 0 };
        }
        for (var i = 0; i < waypoints.length - 1; i++) {
            if (angle >= waypoints[i].angle && angle < waypoints[i + 1].angle) {
                var range = waypoints[i + 1].angle - waypoints[i].angle;
                var t = range > 0 ? (angle - waypoints[i].angle) / range : 0;
                return { lower: waypoints[i], upper: waypoints[i + 1], t: t };
            }
        }
        var last = waypoints[waypoints.length - 1];
        return { lower: last, upper: last, t: 0 };
    }

    function blendWaypoints(lower, upper, t) {
        if (t === 0) return {
            phase: lower.phase,
            palette: Object.assign({}, lower.palette),
            skyGradient: { stops: lower.skyGradient.stops.slice() },
            themeColor: lower.themeColor,
            neutralPoint: lower.neutralPoint,
            hazeColor: lower.hazeColor.slice()
        };
        if (t === 1) return {
            phase: upper.phase,
            palette: Object.assign({}, upper.palette),
            skyGradient: { stops: upper.skyGradient.stops.slice() },
            themeColor: upper.themeColor,
            neutralPoint: upper.neutralPoint,
            hazeColor: upper.hazeColor.slice()
        };

        // Blend palette
        var palette = {};
        var keys = ['skyColor', 'cloudColor', 'cloudShadowColor', 'sunColor', 'sunGlareColor', 'sunlightColor'];
        for (var i = 0; i < keys.length; i++) {
            palette[keys[i]] = blendColors(lower.palette[keys[i]], upper.palette[keys[i]], t);
        }

        return {
            phase: t < 0.5 ? lower.phase : upper.phase,
            palette: palette,
            skyGradient: { stops: blendGradientStops(lower.skyGradient.stops, upper.skyGradient.stops, t) },
            themeColor: blendColors(lower.themeColor, upper.themeColor, t),
            neutralPoint: blendColors(lower.neutralPoint, upper.neutralPoint, t),
            hazeColor: blendRGB(lower.hazeColor, upper.hazeColor, t)
        };
    }

    // WMO weather code → visual modifiers (tuned for Pacific Northwest)
    function getWeatherModifiers(weatherCode, cloudCover) {
        var mods = {
            speedMult: 1.0, skyDarken: 0, cloudDarken: 0, blendToSky: 0,
            dimSun: 0, softGlow: 0,
            blur: 0, hazeOpacity: 0, colorConvergence: 0, weatherCategory: 'clear'
        };

        if (weatherCode === 0) {
            mods.speedMult = 0.4;
            mods.blendToSky = 0.88;
            mods.dimSun = 0.12;
            mods.weatherCategory = 'clear';
        } else if (weatherCode === 1) {
            mods.speedMult = 0.5;
            mods.blendToSky = 0.6;
            mods.dimSun = 0.05;
            mods.colorConvergence = 0.05;
            mods.weatherCategory = 'partly';
        } else if (weatherCode === 2) {
            mods.speedMult = 0.7;
            mods.blendToSky = 0.35;
            mods.colorConvergence = 0.1;
            mods.weatherCategory = 'partly';
        } else if (weatherCode === 3) {
            mods.speedMult = 0.8;
            mods.softGlow = 0.1;
            mods.skyDarken = 0.05;
            mods.blur = 6;
            mods.hazeOpacity = 0.35;
            mods.colorConvergence = 0.75;
            mods.weatherCategory = 'overcast';
        } else if (weatherCode >= 45 && weatherCode <= 48) {
            mods.speedMult = 0.3;
            mods.blendToSky = -0.2;
            mods.softGlow = 0.15;
            mods.skyDarken = 0.08;
            mods.blur = 12;
            mods.hazeOpacity = 0.85;
            mods.colorConvergence = 0.9;
            mods.weatherCategory = 'fog';
        } else if (weatherCode >= 51 && weatherCode <= 55) {
            mods.speedMult = 0.6;
            mods.skyDarken = 0.1;
            mods.softGlow = 0.08;
            // Light→Dense drizzle: 51=light, 53=moderate, 55=dense
            var drizzleT = (weatherCode - 51) / 4; // 0→1 across 51-55
            mods.blur = 4 + drizzleT;
            mods.hazeOpacity = 0.2 + drizzleT * 0.05;
            mods.colorConvergence = 0.55 + drizzleT * 0.05;
            mods.weatherCategory = 'drizzle';
        } else if (weatherCode >= 56 && weatherCode <= 57) {
            mods.speedMult = 0.5;
            mods.skyDarken = 0.12;
            mods.cloudDarken = 0.05;
            mods.blur = 5;
            mods.hazeOpacity = 0.25;
            mods.colorConvergence = 0.6;
            mods.weatherCategory = 'drizzle';
        } else if (weatherCode >= 61 && weatherCode <= 63) {
            mods.speedMult = 1.0;
            mods.skyDarken = 0.15;
            mods.cloudDarken = 0.1;
            // Slight→Moderate rain
            var rainT = (weatherCode - 61) / 2; // 0→1 across 61-63
            mods.blur = 3 - rainT;
            mods.hazeOpacity = 0.2 + rainT * 0.05;
            mods.colorConvergence = 0.35 + rainT * 0.1;
            mods.weatherCategory = 'rain';
        } else if (weatherCode >= 65 && weatherCode <= 67) {
            mods.speedMult = 1.3;
            mods.skyDarken = 0.25;
            mods.cloudDarken = 0.18;
            mods.blur = 2;
            mods.hazeOpacity = 0.2;
            mods.colorConvergence = 0.45;
            mods.weatherCategory = 'rain';
        } else if (weatherCode >= 71 && weatherCode <= 75) {
            mods.speedMult = 0.4;
            mods.skyDarken = 0.05;
            mods.softGlow = 0.12;
            mods.blendToSky = 0.2;
            // Slight→Heavy snow
            var snowT = (weatherCode - 71) / 4; // 0→1 across 71-75
            mods.blur = 6 + snowT;
            mods.hazeOpacity = 0.35 + snowT * 0.05;
            mods.colorConvergence = 0.65 + snowT * 0.05;
            mods.weatherCategory = 'snow';
        } else if (weatherCode === 77) {
            mods.speedMult = 0.5;
            mods.skyDarken = 0.1;
            mods.blur = 6;
            mods.hazeOpacity = 0.35;
            mods.colorConvergence = 0.65;
            mods.weatherCategory = 'snow';
        } else if (weatherCode >= 80 && weatherCode <= 82) {
            mods.speedMult = 1.2;
            mods.skyDarken = 0.18;
            mods.cloudDarken = 0.12;
            // Rain showers - keep more texture
            var showerT = (weatherCode - 80) / 2;
            mods.blur = 2 + showerT;
            mods.hazeOpacity = 0.15 + showerT * 0.1;
            mods.colorConvergence = 0.3 + showerT * 0.1;
            mods.weatherCategory = 'rain';
        } else if (weatherCode >= 85 && weatherCode <= 86) {
            mods.speedMult = 0.6;
            mods.skyDarken = 0.08;
            mods.softGlow = 0.1;
            mods.blur = 6;
            mods.hazeOpacity = 0.35;
            mods.colorConvergence = 0.65;
            mods.weatherCategory = 'snow';
        } else if (weatherCode >= 95) {
            mods.speedMult = 1.5;
            mods.skyDarken = 0.35;
            mods.cloudDarken = 0.25;
            mods.blur = 1;
            mods.hazeOpacity = 0.08;
            mods.colorConvergence = 0.15;
            mods.weatherCategory = 'storm';
        }

        // Cloud cover modulation: smooth scaling of atmospheric effects
        if (mods.weatherCategory !== 'clear' && mods.weatherCategory !== 'partly') {
            // Scale blur/haze/convergence proportionally with cloud cover
            // At 0% cloud: 30% of base values; at 100%: full values
            var cloudFactor = 0.3 + (cloudCover / 100) * 0.7;
            mods.blur *= cloudFactor;
            mods.hazeOpacity *= cloudFactor;
            mods.colorConvergence *= cloudFactor;
        }

        // Vanta color modulation from cloud cover (blendToSky, skyDarken)
        if (cloudCover < 20) {
            mods.blendToSky = Math.max(mods.blendToSky, 0.7);
        } else if (cloudCover < 40) {
            mods.blendToSky = Math.max(mods.blendToSky, 0.4);
        } else if (cloudCover > 90) {
            mods.skyDarken += 0.05;
            mods.blendToSky = Math.min(mods.blendToSky, 0.1);
        }

        // Cloud opacity: responsive to cloud cover for all weather codes
        var cloudOpacity = 1.0;
        if (weatherCode === 0 && cloudCover < 20) {
            cloudOpacity = 0.15 + (cloudCover / 20) * 0.3;
        } else if (weatherCode === 0) {
            cloudOpacity = 0.45 + (cloudCover / 100) * 0.55;
        } else if (weatherCode === 1 && cloudCover < 30) {
            cloudOpacity = 0.4 + (cloudCover / 30) * 0.4;
        } else if (weatherCode <= 2) {
            cloudOpacity = (cloudCover / 100) * 0.9 + 0.1;
        } else {
            // Overcast, fog, drizzle, rain, snow, storm
            cloudOpacity = cloudCover / 100;
        }
        mods.cloudOpacity = cloudOpacity;

        return mods;
    }

    function getWeatherParticleType(weatherCode) {
        if ((weatherCode >= 51 && weatherCode <= 67) ||
            (weatherCode >= 80 && weatherCode <= 82) ||
            (weatherCode >= 95 && weatherCode <= 99)) {
            return 'rain';
        }
        if ((weatherCode >= 71 && weatherCode <= 77) ||
            (weatherCode >= 85 && weatherCode <= 86)) {
            return 'snow';
        }
        return null;
    }

    function getWeatherParticleIntensity(weatherCode) {
        if ([51, 56, 61, 66, 71, 77, 80, 85].includes(weatherCode)) return 0.3;
        if ([53, 63, 73, 81].includes(weatherCode)) return 0.6;
        if ([55, 57, 65, 67, 75, 82, 86, 95, 96, 99].includes(weatherCode)) return 1.0;
        return 0.5;
    }

    // ========================================================================
    // WeatherParticle class (rain drops, snowflakes)
    // ========================================================================

    class WeatherParticle {
        constructor(type, intensity, canvasWidth, canvasHeight) {
            this.type = type;
            this.intensity = intensity;
            this.canvasWidth = canvasWidth;
            this.canvasHeight = canvasHeight;
            this.reset(true);
        }

        reset(initial) {
            this.x = Math.random() * this.canvasWidth;
            this.y = initial ? Math.random() * this.canvasHeight : -20;

            if (this.type === 'rain') {
                this.speed = 800 + Math.random() * 400;
                this.length = 15 + Math.random() * 12;
                this.opacity = 0.25 + Math.random() * 0.25;
                this.wind = 1.5 + Math.random() * 1.5;
                this.lineWidth = 0.75 + Math.random() * 0.5;
            } else if (this.type === 'snow') {
                this.speed = 40 + Math.random() * 60;
                this.radius = 1 + Math.random() * 2.5;
                this.opacity = 0.4 + Math.random() * 0.4;
                this.wobble = Math.random() * Math.PI * 2;
                this.wobbleSpeed = 1.5 + Math.random();
            }
        }

        update(deltaTime) {
            var dt = deltaTime / 1000;
            if (this.type === 'rain') {
                this.y += this.speed * dt;
                this.x += this.wind * 60 * dt;
            } else if (this.type === 'snow') {
                this.y += this.speed * dt;
                this.wobble += this.wobbleSpeed * dt;
                this.x += Math.sin(this.wobble) * 30 * dt;
            }
            if (this.y > this.canvasHeight + 20 || this.x > this.canvasWidth + 20 || this.x < -20) {
                this.reset(false);
            }
        }

        draw(ctx, timeOfDay) {
            if (this.type === 'rain') {
                var color = timeOfDay === 'night'
                    ? 'rgba(140, 160, 190, ' + this.opacity + ')'
                    : 'rgba(170, 190, 210, ' + this.opacity + ')';
                ctx.strokeStyle = color;
                ctx.lineWidth = this.lineWidth;
                ctx.lineCap = 'round';
                ctx.beginPath();
                ctx.moveTo(this.x, this.y);
                ctx.lineTo(this.x + this.wind * 1.5, this.y + this.length);
                ctx.stroke();
            } else if (this.type === 'snow') {
                ctx.fillStyle = 'rgba(255, 255, 255, ' + this.opacity + ')';
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    // ========================================================================
    // Dependency loading (Three.js + Vanta.js)
    // ========================================================================

    var _depLoadPromise = null;

    function loadScript(url) {
        return new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = url;
            script.onload = resolve;
            script.onerror = function () { reject(new Error('Failed to load: ' + url)); };
            document.head.appendChild(script);
        });
    }

    function loadDeps(threejsUrl, vantaUrl) {
        if (_depLoadPromise) return _depLoadPromise;
        _depLoadPromise = (async function () {
            if (!window.THREE) {
                await loadScript(threejsUrl);
            }
            if (!window.VANTA || !window.VANTA.CLOUDS) {
                await loadScript(vantaUrl);
            }
        })();
        return _depLoadPromise;
    }

    // ========================================================================
    // Default options
    // ========================================================================

    var DEFAULTS = {
        latitude: 45.52,
        longitude: -122.68,
        timezone: 'America/Los_Angeles',

        palettes: {
            night: {
                skyColor: 0x0a1628,
                cloudColor: 0x1a2a4a,
                cloudShadowColor: 0x050a14,
                sunColor: 0x8899aa,
                sunGlareColor: 0x334455,
                sunlightColor: 0x6677aa
            },
            dawn: {
                skyColor: 0x4a3a5c,
                cloudColor: 0xc09068,
                cloudShadowColor: 0x2a1a3c,
                sunColor: 0xd4a870,
                sunGlareColor: 0xc87858,
                sunlightColor: 0xd0b888
            },
            day: {
                skyColor: 0x5a9fc8,
                cloudColor: 0x88aaba,
                cloudShadowColor: 0x4a7a98,
                sunColor: 0xc8c0a8,
                sunGlareColor: 0xa89880,
                sunlightColor: 0xb8b0a0
            },
            dusk: {
                skyColor: 0x5c4a6a,
                cloudColor: 0xc88850,
                cloudShadowColor: 0x2a1a3c,
                sunColor: 0xd08050,
                sunGlareColor: 0xc05838,
                sunlightColor: 0xd09060
            }
        },

        skyGradients: {
            night: 'linear-gradient(to bottom, #0a1628 0%, #1a2a4a 50%, #2a3a5a 100%)',
            dawn: 'linear-gradient(to bottom, #ff9966 0%, #cc7a5a 30%, #4a3a5c 70%, #2a1a3c 100%)',
            day: 'linear-gradient(to bottom, #4a90c2 0%, #6eb5d9 40%, #87ceeb 100%)',
            dusk: 'linear-gradient(to bottom, #ff7744 0%, #cc6644 30%, #5c4a6a 70%, #2a1a3c 100%)'
        },

        themeColors: {
            night: '#0a1628',
            dawn: '#ff9966',
            day: '#4a90c2',
            dusk: '#ff7744'
        },

        baseSpeed: 0.4,
        mobileSpeed: 0.3,
        mobileBreakpoint: 768,
        respectReducedMotion: true,
        autoFetchWeather: true,
        weatherRefreshInterval: 0,
        flipClouds: true,
        enableParticles: true,
        enableFog: true,
        updateThemeColor: false,

        dawnWindowBefore: 45,
        dawnWindowAfter: 30,
        duskWindowBefore: 30,
        duskWindowAfter: 45,

        vantaOptions: {},
        autoLoadDeps: true,
        threejsUrl: 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js',
        vantaUrl: 'https://cdn.jsdelivr.net/npm/vanta@latest/dist/vanta.clouds.min.js',

        // Weather-adaptive sky gradients per category + time of day
        weatherGradients: {
            overcast: {
                day:   'linear-gradient(to bottom, #8a9098 0%, #979da4 40%, #a8aeb5 100%)',
                night: 'linear-gradient(to bottom, #1a1e24 0%, #252a30 50%, #303840 100%)',
                dawn:  'linear-gradient(to bottom, #9a8880 0%, #908888 40%, #8a9098 100%)',
                dusk:  'linear-gradient(to bottom, #8a7870 0%, #888080 40%, #8a9098 100%)'
            },
            fog: {
                day:   'linear-gradient(to bottom, #b0b4b8 0%, #babec2 40%, #c8ccd0 100%)',
                night: 'linear-gradient(to bottom, #202428 0%, #2a2e34 50%, #383e48 100%)',
                dawn:  'linear-gradient(to bottom, #b0a098 0%, #a8a0a0 40%, #b0b4b8 100%)',
                dusk:  'linear-gradient(to bottom, #a89890 0%, #a09898 40%, #b0b4b8 100%)'
            },
            drizzle: {
                day:   'linear-gradient(to bottom, #7a8490 0%, #8a929c 40%, #98a0a8 100%)',
                night: 'linear-gradient(to bottom, #161a20 0%, #1e2228 50%, #282e38 100%)',
                dawn:  'linear-gradient(to bottom, #907870 0%, #887878 40%, #7a8490 100%)',
                dusk:  'linear-gradient(to bottom, #806868 0%, #787070 40%, #7a8490 100%)'
            },
            rain: {
                day:   'linear-gradient(to bottom, #606870 0%, #707880 40%, #808890 100%)',
                night: 'linear-gradient(to bottom, #101418 0%, #181c22 50%, #222830 100%)',
                dawn:  'linear-gradient(to bottom, #786860 0%, #706868 40%, #606870 100%)',
                dusk:  'linear-gradient(to bottom, #685858 0%, #605858 40%, #606870 100%)'
            },
            snow: {
                day:   'linear-gradient(to bottom, #a0a8b0 0%, #b0b8c0 40%, #c0c8d0 100%)',
                night: 'linear-gradient(to bottom, #1e2230 0%, #283040 50%, #384050 100%)',
                dawn:  'linear-gradient(to bottom, #b0a0a0 0%, #a8a0a8 40%, #a0a8b0 100%)',
                dusk:  'linear-gradient(to bottom, #a09098 0%, #989098 40%, #a0a8b0 100%)'
            },
            storm: {
                day:   'linear-gradient(to bottom, #404850 0%, #505860 40%, #606870 100%)',
                night: 'linear-gradient(to bottom, #080a10 0%, #101418 50%, #1a2028 100%)',
                dawn:  'linear-gradient(to bottom, #584840 0%, #504848 40%, #404850 100%)',
                dusk:  'linear-gradient(to bottom, #483838 0%, #403838 40%, #404850 100%)'
            }
        },

        // Color convergence neutral point per time of day (hex integers)
        neutralPoints: {
            day:   0xa0a5a8,
            night: 0x1a1e25,
            dawn:  0x8a7570,
            dusk:  0x7a6a68
        },

        // Haze overlay colors per time of day [r, g, b]
        hazeColors: {
            day:   [170, 175, 180],
            night: [22, 26, 34],
            dawn:  [140, 120, 115],
            dusk:  [125, 108, 105]
        },

        // iOS meta theme-color per weather category + time of day
        weatherThemeColors: {
            overcast: { day: '#8a9098', night: '#1a1e24', dawn: '#9a8880', dusk: '#8a7870' },
            fog:      { day: '#b0b4b8', night: '#202428', dawn: '#b0a098', dusk: '#a89890' },
            drizzle:  { day: '#7a8490', night: '#161a20', dawn: '#907870', dusk: '#806868' },
            rain:     { day: '#606870', night: '#101418', dawn: '#786860', dusk: '#685858' },
            snow:     { day: '#a0a8b0', night: '#1e2230', dawn: '#b0a0a0', dusk: '#a09098' },
            storm:    { day: '#404850', night: '#080a10', dawn: '#584840', dusk: '#483838' }
        }
    };

    // ========================================================================
    // Sun-angle waypoints (PNW-tuned palettes)
    // ========================================================================

    // Morning waypoints: cooler, pink-rose tones (marine layer diffusion)
    var SUN_WAYPOINTS_MORNING = [
        {
            angle: -18, phase: 'night',
            palette: { skyColor: 0x0a1628, cloudColor: 0x1a2a4a, cloudShadowColor: 0x050a14, sunColor: 0x8899aa, sunGlareColor: 0x334455, sunlightColor: 0x6677aa },
            skyGradient: { stops: [[0x0a1628, 0], [0x111e38, 33], [0x1a2a4a, 67], [0x2a3a5a, 100]] },
            themeColor: 0x0a1628, neutralPoint: 0x1a1e25, hazeColor: [22, 26, 34]
        },
        {
            angle: -12, phase: 'night',
            palette: { skyColor: 0x0e1a30, cloudColor: 0x1e2e50, cloudShadowColor: 0x080e1a, sunColor: 0x8899aa, sunGlareColor: 0x3a4a5a, sunlightColor: 0x6a7aaa },
            skyGradient: { stops: [[0x0e1a30, 0], [0x151f3c, 33], [0x1e2e50, 67], [0x2e3e5e, 100]] },
            themeColor: 0x0e1a30, neutralPoint: 0x1c2028, hazeColor: [26, 30, 40]
        },
        {
            angle: -6, phase: 'dawn',
            palette: { skyColor: 0x2a2848, cloudColor: 0x4a4068, cloudShadowColor: 0x181430, sunColor: 0x9080a0, sunGlareColor: 0x6a5878, sunlightColor: 0x8878a0 },
            skyGradient: { stops: [[0x1a1838, 0], [0x2a2848, 33], [0x3a3558, 67], [0x5a4a6a, 100]] },
            themeColor: 0x2a2848, neutralPoint: 0x4a4058, hazeColor: [60, 55, 75]
        },
        {
            angle: -1, phase: 'dawn',
            palette: { skyColor: 0x4a3a5c, cloudColor: 0xb88878, cloudShadowColor: 0x2a1a3c, sunColor: 0xd4a080, sunGlareColor: 0xc07060, sunlightColor: 0xd0a888 },
            skyGradient: { stops: [[0xd09080, 0], [0xa87068, 33], [0x4a3a5c, 67], [0x2a1a3c, 100]] },
            themeColor: 0xd09080, neutralPoint: 0x8a7570, hazeColor: [140, 120, 115]
        },
        {
            angle: 1, phase: 'dawn',
            palette: { skyColor: 0x6a6888, cloudColor: 0xc8a088, cloudShadowColor: 0x3a3050, sunColor: 0xdab888, sunGlareColor: 0xc88868, sunlightColor: 0xd8b898 },
            skyGradient: { stops: [[0xe0a888, 0], [0xc09078, 33], [0x7a7090, 67], [0x5a5878, 100]] },
            themeColor: 0xe0a888, neutralPoint: 0x9a8878, hazeColor: [160, 138, 125]
        },
        {
            angle: 6, phase: 'day',
            palette: { skyColor: 0x5898b8, cloudColor: 0x98aab8, cloudShadowColor: 0x487090, sunColor: 0xc8b8a0, sunGlareColor: 0xb09880, sunlightColor: 0xc0b098 },
            skyGradient: { stops: [[0x5898b8, 0], [0x70a8c4, 33], [0x88bcd0, 67], [0xa0d0e0, 100]] },
            themeColor: 0x5898b8, neutralPoint: 0x98a0a4, hazeColor: [155, 162, 168]
        },
        {
            angle: 15, phase: 'day',
            palette: { skyColor: 0x5a9fc8, cloudColor: 0x88aaba, cloudShadowColor: 0x4a7a98, sunColor: 0xc8c0a8, sunGlareColor: 0xa89880, sunlightColor: 0xb8b0a0 },
            skyGradient: { stops: [[0x4a90c2, 0], [0x6eb5d9, 33], [0x7ac4e4, 67], [0x87ceeb, 100]] },
            themeColor: 0x4a90c2, neutralPoint: 0xa0a5a8, hazeColor: [170, 175, 180]
        }
    ];

    // Evening waypoints: warmer, amber-orange tones (PNW sunsets are warmer than sunrises)
    var SUN_WAYPOINTS_EVENING = [
        {
            angle: -18, phase: 'night',
            palette: { skyColor: 0x0a1628, cloudColor: 0x1a2a4a, cloudShadowColor: 0x050a14, sunColor: 0x8899aa, sunGlareColor: 0x334455, sunlightColor: 0x6677aa },
            skyGradient: { stops: [[0x0a1628, 0], [0x111e38, 33], [0x1a2a4a, 67], [0x2a3a5a, 100]] },
            themeColor: 0x0a1628, neutralPoint: 0x1a1e25, hazeColor: [22, 26, 34]
        },
        {
            angle: -12, phase: 'night',
            palette: { skyColor: 0x10182e, cloudColor: 0x202a48, cloudShadowColor: 0x0a0e18, sunColor: 0x8a8898, sunGlareColor: 0x3e4456, sunlightColor: 0x6e7498 },
            skyGradient: { stops: [[0x10182e, 0], [0x181e3a, 33], [0x202a48, 67], [0x303a56, 100]] },
            themeColor: 0x10182e, neutralPoint: 0x1e2028, hazeColor: [28, 30, 38]
        },
        {
            angle: -6, phase: 'dusk',
            palette: { skyColor: 0x302840, cloudColor: 0x584860, cloudShadowColor: 0x1a1428, sunColor: 0x987888, sunGlareColor: 0x785868, sunlightColor: 0x907090 },
            skyGradient: { stops: [[0x201830, 0], [0x302840, 33], [0x483858, 67], [0x604a68, 100]] },
            themeColor: 0x302840, neutralPoint: 0x504050, hazeColor: [65, 55, 68]
        },
        {
            angle: -1, phase: 'dusk',
            palette: { skyColor: 0x5c4a6a, cloudColor: 0xc88850, cloudShadowColor: 0x2a1a3c, sunColor: 0xd08050, sunGlareColor: 0xc05838, sunlightColor: 0xd09060 },
            skyGradient: { stops: [[0xd87848, 0], [0xb06840, 33], [0x5c4a6a, 67], [0x2a1a3c, 100]] },
            themeColor: 0xd87848, neutralPoint: 0x7a6a68, hazeColor: [125, 108, 105]
        },
        {
            angle: 1, phase: 'dusk',
            palette: { skyColor: 0x7a6880, cloudColor: 0xd09058, cloudShadowColor: 0x382848, sunColor: 0xd89058, sunGlareColor: 0xc86840, sunlightColor: 0xd8a068 },
            skyGradient: { stops: [[0xe88850, 0], [0xc87848, 33], [0x886878, 67], [0x5c5068, 100]] },
            themeColor: 0xe88850, neutralPoint: 0x887870, hazeColor: [148, 118, 108]
        },
        {
            angle: 6, phase: 'day',
            palette: { skyColor: 0x5898b8, cloudColor: 0x98a8b4, cloudShadowColor: 0x487090, sunColor: 0xc8b898, sunGlareColor: 0xb09478, sunlightColor: 0xc0ac90 },
            skyGradient: { stops: [[0x5898b8, 0], [0x70a8c4, 33], [0x88bcd0, 67], [0xa0d0e0, 100]] },
            themeColor: 0x5898b8, neutralPoint: 0x98a0a4, hazeColor: [155, 162, 168]
        },
        {
            angle: 15, phase: 'day',
            palette: { skyColor: 0x5a9fc8, cloudColor: 0x88aaba, cloudShadowColor: 0x4a7a98, sunColor: 0xc8c0a8, sunGlareColor: 0xa89880, sunlightColor: 0xb8b0a0 },
            skyGradient: { stops: [[0x4a90c2, 0], [0x6eb5d9, 33], [0x7ac4e4, 67], [0x87ceeb, 100]] },
            themeColor: 0x4a90c2, neutralPoint: 0xa0a5a8, hazeColor: [170, 175, 180]
        }
    ];

    // Maps setTimeOfDay() strings to representative angle/direction
    var TIME_OVERRIDE_ANGLES = {
        night:  { angle: -18, direction: 'evening' },
        dawn:   { angle: -1,  direction: 'morning' },
        day:    { angle: 15,  direction: 'morning' },
        dusk:   { angle: -1,  direction: 'evening' }
    };

    // Weather gradient stops as hex-int arrays for interpolation
    // Parsed from DEFAULTS.weatherGradients CSS strings
    var WEATHER_GRADIENT_STOPS = {
        overcast: {
            day:   [[0x8a9098, 0], [0x979da4, 40], [0xa8aeb5, 100]],
            night: [[0x1a1e24, 0], [0x252a30, 50], [0x303840, 100]],
            dawn:  [[0x9a8880, 0], [0x908888, 40], [0x8a9098, 100]],
            dusk:  [[0x8a7870, 0], [0x888080, 40], [0x8a9098, 100]]
        },
        fog: {
            day:   [[0xb0b4b8, 0], [0xbabec2, 40], [0xc8ccd0, 100]],
            night: [[0x202428, 0], [0x2a2e34, 50], [0x383e48, 100]],
            dawn:  [[0xb0a098, 0], [0xa8a0a0, 40], [0xb0b4b8, 100]],
            dusk:  [[0xa89890, 0], [0xa09898, 40], [0xb0b4b8, 100]]
        },
        drizzle: {
            day:   [[0x7a8490, 0], [0x8a929c, 40], [0x98a0a8, 100]],
            night: [[0x161a20, 0], [0x1e2228, 50], [0x282e38, 100]],
            dawn:  [[0x907870, 0], [0x887878, 40], [0x7a8490, 100]],
            dusk:  [[0x806868, 0], [0x787070, 40], [0x7a8490, 100]]
        },
        rain: {
            day:   [[0x606870, 0], [0x707880, 40], [0x808890, 100]],
            night: [[0x101418, 0], [0x181c22, 50], [0x222830, 100]],
            dawn:  [[0x786860, 0], [0x706868, 40], [0x606870, 100]],
            dusk:  [[0x685858, 0], [0x605858, 40], [0x606870, 100]]
        },
        snow: {
            day:   [[0xa0a8b0, 0], [0xb0b8c0, 40], [0xc0c8d0, 100]],
            night: [[0x1e2230, 0], [0x283040, 50], [0x384050, 100]],
            dawn:  [[0xb0a0a0, 0], [0xa8a0a8, 40], [0xa0a8b0, 100]],
            dusk:  [[0xa09098, 0], [0x989098, 40], [0xa0a8b0, 100]]
        },
        storm: {
            day:   [[0x404850, 0], [0x505860, 40], [0x606870, 100]],
            night: [[0x080a10, 0], [0x101418, 50], [0x1a2028, 100]],
            dawn:  [[0x584840, 0], [0x504848, 40], [0x404850, 100]],
            dusk:  [[0x483838, 0], [0x403838, 40], [0x404850, 100]]
        }
    };

    // Weather theme colors as hex-ints for interpolation
    var WEATHER_THEME_INTS = {
        overcast: { day: 0x8a9098, night: 0x1a1e24, dawn: 0x9a8880, dusk: 0x8a7870 },
        fog:      { day: 0xb0b4b8, night: 0x202428, dawn: 0xb0a098, dusk: 0xa89890 },
        drizzle:  { day: 0x7a8490, night: 0x161a20, dawn: 0x907870, dusk: 0x806868 },
        rain:     { day: 0x606870, night: 0x101418, dawn: 0x786860, dusk: 0x685858 },
        snow:     { day: 0xa0a8b0, night: 0x1e2230, dawn: 0xb0a0a0, dusk: 0xa09098 },
        storm:    { day: 0x404850, night: 0x080a10, dawn: 0x584840, dusk: 0x483838 }
    };

    // ========================================================================
    // Injected CSS (scoped by class prefix)
    // ========================================================================

    var CSS_INJECTED = false;
    var STYLE_ID = 'sky-effect-styles';

    var CSS = [
        '.sky-effect-bg {',
        '  position: absolute; top: 0; left: 0; width: 100%; height: 100%;',
        '  z-index: -2;',
        '  background-color: #4a90c2;',
        '  background-image: linear-gradient(to bottom, #4a90c2 0%, #6eb5d9 40%, #87ceeb 100%);',
        '  transition: background-color 2s ease, background-image 2s ease;',
        '}',
        '.sky-effect-clouds {',
        '  position: absolute; top: 0; left: 0; width: 100%; height: 100%;',
        '  z-index: -1;',
        '  will-change: filter, opacity, transform;',
        '  transition: opacity 0.8s ease, filter 0.8s ease;',
        '}',
        '.sky-effect-clouds.sky-effect-flipped {',
        '  transform: scaleY(-1);',
        '}',
        '.sky-effect-fog {',
        '  position: absolute; top: 0; left: 0; width: 100%; height: 100%;',
        '  z-index: 0;',
        '  background: linear-gradient(to bottom,',
        '    rgba(180, 180, 185, 0.95) 0%,',
        '    rgba(190, 190, 195, 0.9) 30%,',
        '    rgba(200, 200, 205, 0.85) 60%,',
        '    rgba(210, 210, 215, 0.8) 100%);',
        '  opacity: 0;',
        '  pointer-events: none;',
        '  transition: opacity 0.8s ease, background 0.8s ease;',
        '}',
        '.sky-effect-particles {',
        '  position: absolute; top: 0; left: 0; width: 100%; height: 100%;',
        '  z-index: 1;',
        '  pointer-events: none;',
        '  mix-blend-mode: overlay;',
        '}'
    ].join('\n');

    function injectCSS() {
        if (CSS_INJECTED) return;
        if (document.getElementById(STYLE_ID)) { CSS_INJECTED = true; return; }
        var style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
        CSS_INJECTED = true;
    }

    // ========================================================================
    // SkyEffect class
    // ========================================================================

    function SkyEffect(container, options) {
        // Resolve container element
        if (typeof container === 'string') {
            this._container = document.querySelector(container);
        } else {
            this._container = container;
        }
        if (!this._container) {
            throw new Error('SkyEffect: container element not found');
        }

        // Merge options with defaults (shallow merge per top-level key, deep merge for palettes/gradients/themeColors)
        this._options = {};
        for (var key in DEFAULTS) {
            if (DEFAULTS.hasOwnProperty(key)) {
                this._options[key] = DEFAULTS[key];
            }
        }
        if (options) {
            for (var key in options) {
                if (options.hasOwnProperty(key)) {
                    // Deep merge palette-like objects (one level)
                    if (key === 'palettes' || key === 'skyGradients' || key === 'themeColors' || key === 'vantaOptions' ||
                        key === 'neutralPoints' || key === 'hazeColors') {
                        this._options[key] = Object.assign({}, DEFAULTS[key] || {}, options[key]);
                    // Two-level deep merge for category → time-of-day maps
                    } else if (key === 'weatherGradients' || key === 'weatherThemeColors') {
                        var merged = {};
                        var def = DEFAULTS[key] || {};
                        for (var cat in def) {
                            if (def.hasOwnProperty(cat)) {
                                merged[cat] = Object.assign({}, def[cat]);
                            }
                        }
                        for (var cat in options[key]) {
                            if (options[key].hasOwnProperty(cat)) {
                                merged[cat] = Object.assign(merged[cat] || {}, options[key][cat]);
                            }
                        }
                        this._options[key] = merged;
                    } else {
                        this._options[key] = options[key];
                    }
                }
            }
        }

        // Internal state
        this._weather = null;
        this._timeOverride = null;
        this._paused = false;
        this._destroyed = false;
        this._currentTimeOfDay = null;
        this._currentSpeed = 0;
        this._listeners = {};

        // DOM elements (created on init)
        this._bgEl = null;
        this._cloudsEl = null;
        this._fogEl = null;
        this._particlesCanvas = null;
        this._particlesCtx = null;

        // Vanta instance
        this._vantaEffect = null;
        this._vantaFrozen = false;

        // Particle system state
        this._particles = [];
        this._particleAnimId = null;
        this._lastParticleFrame = 0;
        this._particlesWereRunning = false;
        this._particleTimeOfDay = 'day';
        this._currentParticleType = null;
        this._currentParticleIntensity = null;

        // Weather refresh timer
        this._weatherTimer = null;

        // Sun-angle state
        this._currentSunAltitude = null;
        this._currentSunDirection = null;
        this._sunAngleOverride = null;       // { angle, direction } for demo testing
        this._renderTimer = null;            // periodic re-render interval
        this._deferVanta = false;            // skip Vanta creation during gradient-only renders

        // Bound handlers for cleanup
        this._boundVisChange = this._onVisibilityChange.bind(this);
        this._boundResize = this._onResize.bind(this);
    }

    // ---- Event system ----

    SkyEffect.prototype.on = function (event, handler) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(handler);
        return this;
    };

    SkyEffect.prototype.off = function (event, handler) {
        if (!this._listeners[event]) return this;
        if (!handler) {
            delete this._listeners[event];
        } else {
            this._listeners[event] = this._listeners[event].filter(function (h) { return h !== handler; });
        }
        return this;
    };

    SkyEffect.prototype._emit = function (event, data) {
        var handlers = this._listeners[event];
        if (!handlers) return;
        for (var i = 0; i < handlers.length; i++) {
            try { handlers[i](data); } catch (e) { console.error('SkyEffect event handler error:', e); }
        }
    };

    // ---- Public API ----

    SkyEffect.prototype.init = async function () {
        if (this._destroyed) throw new Error('SkyEffect: cannot init a destroyed instance');

        injectCSS();
        this._createDOM();

        // Phase 1: Render gradient immediately (no Vanta, no weather yet).
        // This gives instant visual feedback while heavy assets load.
        this._render();

        // Phase 2: Load deps and fetch weather in parallel
        var depsPromise = this._options.autoLoadDeps
            ? loadDeps(this._options.threejsUrl, this._options.vantaUrl).catch(function (e) {
                console.warn('SkyEffect: dependency load failed, running in gradient-only mode.', e.message);
            })
            : Promise.resolve();

        var weatherPromise = this._options.autoFetchWeather
            ? this._fetchWeather()
            : Promise.resolve(null);

        var results = await Promise.all([depsPromise, weatherPromise]);
        if (results[1]) {
            this._weather = results[1];
        }

        // Phase 3: Re-render gradient with weather data but skip Vanta creation.
        // The gradient + haze update instantly; Vanta WebGL init is deferred below.
        this._deferVanta = true;
        this._render();
        this._deferVanta = false;

        // Attach global listeners
        document.addEventListener('visibilitychange', this._boundVisChange);
        window.addEventListener('resize', this._boundResize);

        // Weather refresh interval
        var self = this;
        if (this._options.weatherRefreshInterval > 0) {
            this._weatherTimer = setInterval(function () {
                self.refreshWeather();
            }, this._options.weatherRefreshInterval);
        }

        // Periodic re-render for sun angle progression (~0.25°/min, update every 30s)
        this._renderTimer = setInterval(function () {
            if (!self._destroyed && !self._paused && !self._timeOverride && !self._sunAngleOverride) {
                self._render();
            }
        }, 30000);

        // Phase 4: Defer heavy Vanta WebGL init. VANTA.CLOUDS() blocks the main
        // thread during shader compilation and geometry setup. By not awaiting this,
        // init() resolves immediately, controls are responsive, and the cloud layer
        // fades in once WebGL is ready.
        setTimeout(function () {
            if (!self._destroyed) {
                self._emit('vantaloading', {});
                self._render();
                self._emit('vantaready', {});
            }
        }, 80);

        return this;
    };

    SkyEffect.prototype.setWeather = function (weatherData) {
        this._weather = {
            weatherCode: weatherData.weatherCode != null ? weatherData.weatherCode : 3,
            cloudCover: weatherData.cloudCover != null ? weatherData.cloudCover : 75,
            isDay: weatherData.isDay != null ? weatherData.isDay : true,
            temperature: weatherData.temperature != null ? weatherData.temperature : 15,
            sunrise: weatherData.sunrise != null ? weatherData.sunrise : 7 * 60 + 30,
            sunset: weatherData.sunset != null ? weatherData.sunset : 17 * 60 + 30
        };
        this._render();
        this._emit('weatherupdate', Object.assign({}, this._weather));
    };

    SkyEffect.prototype.setTimeOfDay = function (tod) {
        this._timeOverride = tod; // null = auto
        this._sunAngleOverride = null; // clear angle override when using time override
        this._render();
    };

    SkyEffect.prototype.setSunAngle = function (angle, direction) {
        if (angle == null) {
            this._sunAngleOverride = null;
        } else {
            this._sunAngleOverride = { angle: angle, direction: direction || 'morning' };
            this._timeOverride = null; // clear time override when setting angle
        }
        this._render();
    };

    SkyEffect.prototype.refreshWeather = async function () {
        var weather = await this._fetchWeather();
        if (weather) {
            this._weather = weather;
            this._render();
            this._emit('weatherupdate', Object.assign({}, this._weather));
        }
        return weather;
    };

    SkyEffect.prototype.pause = function () {
        if (this._paused) return;
        this._paused = true;
        if (this._vantaEffect && !this._vantaFrozen) {
            this._vantaEffect.setOptions({ speed: 0 });
        }
        this._stopParticles();
    };

    SkyEffect.prototype.resume = function () {
        if (!this._paused) return;
        this._paused = false;
        if (this._vantaEffect) this._vantaEffect.setOptions({ speed: this._currentSpeed });
        // Re-render to restart particles if applicable
        this._render();
    };

    SkyEffect.prototype.getState = function () {
        var mods = this._weather
            ? getWeatherModifiers(this._weather.weatherCode, this._weather.cloudCover)
            : null;
        return {
            timeOfDay: this._currentTimeOfDay,
            sunAltitude: this._currentSunAltitude,
            sunDirection: this._currentSunDirection,
            weatherCode: this._weather ? this._weather.weatherCode : null,
            cloudCover: this._weather ? this._weather.cloudCover : null,
            temperature: this._weather ? this._weather.temperature : null,
            isDaytime: this._currentTimeOfDay === 'day' || this._currentTimeOfDay === 'dawn',
            paused: this._paused,
            weatherCategory: mods ? mods.weatherCategory : null,
            blur: mods ? mods.blur : 0,
            hazeOpacity: mods ? mods.hazeOpacity : 0,
            colorConvergence: mods ? mods.colorConvergence : 0
        };
    };

    SkyEffect.prototype.destroy = function () {
        if (this._destroyed) return;
        this._destroyed = true;

        // Stop particles
        this._stopParticles();

        // Destroy Vanta
        if (this._vantaEffect) {
            this._vantaEffect.destroy();
            this._vantaEffect = null;
        }

        // Remove DOM
        if (this._bgEl && this._bgEl.parentNode) this._bgEl.parentNode.removeChild(this._bgEl);
        if (this._cloudsEl && this._cloudsEl.parentNode) this._cloudsEl.parentNode.removeChild(this._cloudsEl);
        if (this._fogEl && this._fogEl.parentNode) this._fogEl.parentNode.removeChild(this._fogEl);
        if (this._particlesCanvas && this._particlesCanvas.parentNode) this._particlesCanvas.parentNode.removeChild(this._particlesCanvas);

        // Remove listeners
        document.removeEventListener('visibilitychange', this._boundVisChange);
        window.removeEventListener('resize', this._boundResize);

        // Clear weather timer
        if (this._weatherTimer) {
            clearInterval(this._weatherTimer);
            this._weatherTimer = null;
        }

        // Clear periodic render timer
        if (this._renderTimer) {
            clearInterval(this._renderTimer);
            this._renderTimer = null;
        }

        this._emit('destroy', {});
        this._listeners = {};
    };

    // ---- Private methods ----

    SkyEffect.prototype._createDOM = function () {
        // Background gradient
        this._bgEl = document.createElement('div');
        this._bgEl.className = 'sky-effect-bg';

        // Vanta clouds target
        this._cloudsEl = document.createElement('div');
        this._cloudsEl.className = 'sky-effect-clouds';
        if (this._options.flipClouds) {
            this._cloudsEl.classList.add('sky-effect-flipped');
        }

        // Fog overlay
        this._fogEl = document.createElement('div');
        this._fogEl.className = 'sky-effect-fog';

        // Particle canvas
        this._particlesCanvas = document.createElement('canvas');
        this._particlesCanvas.className = 'sky-effect-particles';
        this._particlesCtx = this._particlesCanvas.getContext('2d');

        this._container.appendChild(this._bgEl);
        this._container.appendChild(this._cloudsEl);
        this._container.appendChild(this._fogEl);
        this._container.appendChild(this._particlesCanvas);

        this._resizeCanvas();
    };

    SkyEffect.prototype._resizeCanvas = function () {
        if (!this._particlesCanvas) return;
        this._particlesCanvas.width = this._container.offsetWidth || window.innerWidth;
        this._particlesCanvas.height = this._container.offsetHeight || window.innerHeight;
    };

    SkyEffect.prototype._buildHazeGradient = function (rgbOrTimeOfDay) {
        // Accept RGB array directly, or fall back to legacy time-of-day string lookup
        var c;
        if (Array.isArray(rgbOrTimeOfDay)) {
            c = rgbOrTimeOfDay;
        } else {
            c = this._options.hazeColors[rgbOrTimeOfDay] || this._options.hazeColors.day;
        }
        return 'linear-gradient(to bottom, ' +
            'rgba(' + c[0] + ', ' + c[1] + ', ' + c[2] + ', 0.95) 0%, ' +
            'rgba(' + c[0] + ', ' + c[1] + ', ' + c[2] + ', 0.9) 30%, ' +
            'rgba(' + c[0] + ', ' + c[1] + ', ' + c[2] + ', 0.85) 60%, ' +
            'rgba(' + c[0] + ', ' + c[1] + ', ' + c[2] + ', 0.8) 100%)';
    };

    SkyEffect.prototype._calculateVantaOptions = function () {
        var now = new Date();
        var sunAlt, sunDir, waypoints;

        // Determine sun angle and direction
        if (this._sunAngleOverride) {
            sunAlt = this._sunAngleOverride.angle;
            sunDir = this._sunAngleOverride.direction;
        } else if (this._timeOverride && TIME_OVERRIDE_ANGLES[this._timeOverride]) {
            var ov = TIME_OVERRIDE_ANGLES[this._timeOverride];
            sunAlt = ov.angle;
            sunDir = ov.direction;
        } else {
            // Live sun altitude from lat/lon/time
            sunAlt = getSolarAltitude(this._options.latitude, this._options.longitude, now);
            var currentMins = now.getHours() * 60 + now.getMinutes();
            var sunriseMins = (this._weather && this._weather.sunrise) || 7 * 60 + 30;
            var sunsetMins = (this._weather && this._weather.sunset) || 17 * 60 + 30;
            sunDir = getSunDirection(currentMins, sunriseMins, sunsetMins);
        }

        // Store for getState()
        this._currentSunAltitude = sunAlt;
        this._currentSunDirection = sunDir;

        // Select waypoint set based on direction
        waypoints = sunDir === 'morning' ? SUN_WAYPOINTS_MORNING : SUN_WAYPOINTS_EVENING;

        // Interpolate between bounding waypoints
        var interp = interpolateWaypoints(sunAlt, waypoints);
        var blended = blendWaypoints(interp.lower, interp.upper, interp.t);

        // Extract interpolated values
        var timeOfDay = blended.phase; // 'night', 'dawn', 'day', or 'dusk'
        var options = Object.assign({}, blended.palette);

        // Attach interpolation context (removed before Vanta)
        options._interpolated = blended;

        var speedMult = 1.0;
        if (this._weather) {
            var mods = getWeatherModifiers(this._weather.weatherCode, this._weather.cloudCover);
            speedMult = mods.speedMult;

            if (mods.skyDarken > 0) {
                options.skyColor = darkenColor(options.skyColor, mods.skyDarken);
            }
            if (mods.cloudDarken > 0) {
                options.cloudColor = darkenColor(options.cloudColor, mods.cloudDarken);
                options.cloudShadowColor = darkenColor(options.cloudShadowColor, mods.cloudDarken);
            }
            if (mods.blendToSky > 0) {
                options.cloudColor = blendColors(options.cloudColor, options.skyColor, mods.blendToSky);
                options.cloudShadowColor = blendColors(options.cloudShadowColor, options.skyColor, mods.blendToSky * 0.5);
            } else if (mods.blendToSky < 0) {
                options.cloudColor = darkenColor(options.cloudColor, -mods.blendToSky * 0.3);
            }
            if (mods.dimSun > 0) {
                options.sunColor = darkenColor(options.sunColor, mods.dimSun);
                options.sunGlareColor = darkenColor(options.sunGlareColor, mods.dimSun * 1.5);
                options.sunlightColor = darkenColor(options.sunlightColor, mods.dimSun);
            }
            if (mods.softGlow > 0) {
                options.sunlightColor = lightenColor(options.sunlightColor, mods.softGlow);
                options.cloudColor = lightenColor(options.cloudColor, mods.softGlow * 0.5);
            }

            options.cloudOpacity = mods.cloudOpacity;

            // Color convergence: blend palette colors toward interpolated neutral point.
            // Cloud colors converge at half rate to preserve visible texture against
            // the flattened sky — otherwise clouds wash out at high convergence.
            if (mods.colorConvergence > 0) {
                var neutral = blended.neutralPoint;
                var conv = mods.colorConvergence;
                options.skyColor = blendColors(options.skyColor, neutral, conv);
                options.cloudColor = blendColors(options.cloudColor, neutral, conv * 0.5);
                options.cloudShadowColor = blendColors(options.cloudShadowColor, neutral, conv * 0.5);
                options.sunColor = blendColors(options.sunColor, neutral, conv);
                options.sunGlareColor = blendColors(options.sunGlareColor, neutral, conv);
                options.sunlightColor = blendColors(options.sunlightColor, neutral, conv);
            }

            // Pass atmospheric modifiers through (removed before Vanta)
            options.blur = mods.blur;
            options.hazeOpacity = mods.hazeOpacity;
            options.colorConvergence = mods.colorConvergence;
            options.weatherCategory = mods.weatherCategory;
        }

        var isMobile = window.innerWidth < this._options.mobileBreakpoint;
        var reducedMotion = this._options.respectReducedMotion &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Mobile gets reduced blur for performance
        if (isMobile && options.blur) {
            options.blur = options.blur * 0.6;
        }

        var base = reducedMotion ? 0 : (isMobile ? this._options.mobileSpeed : this._options.baseSpeed);
        options.speed = base * speedMult;
        options.timeOfDay = timeOfDay;
        return options;
    };

    SkyEffect.prototype._render = function () {
        if (this._destroyed) return;

        var options = this._calculateVantaOptions();
        var timeOfDay = options.timeOfDay;
        var previousTimeOfDay = this._currentTimeOfDay;
        this._currentTimeOfDay = timeOfDay;
        this._currentSpeed = options.speed;
        this._particleTimeOfDay = timeOfDay;

        // Extract interpolation data (attached by _calculateVantaOptions)
        var interpolated = options._interpolated;

        // Atmospheric modifiers
        var weatherCat = options.weatherCategory || 'clear';
        var blur = options.blur || 0;
        var hazeOpacity = options.hazeOpacity || 0;

        // Sky gradient: generate from interpolated stop arrays
        if (this._bgEl) {
            var useWeatherGradient = weatherCat !== 'clear' && weatherCat !== 'partly' &&
                WEATHER_GRADIENT_STOPS[weatherCat];

            if (useWeatherGradient) {
                // Interpolate between phases for weather gradients
                var lowerPhase = interpolated ? interpolated.phase : timeOfDay;
                var wgStops = WEATHER_GRADIENT_STOPS[weatherCat];
                var phaseStops = wgStops[lowerPhase] || wgStops.day;
                this._bgEl.style.backgroundImage = gradientStopsToCSS(phaseStops);
            } else if (interpolated) {
                this._bgEl.style.backgroundImage = gradientStopsToCSS(interpolated.skyGradient.stops);
            } else {
                this._bgEl.style.backgroundImage = this._options.skyGradients[timeOfDay];
            }

            // Background color from interpolated theme color
            if (interpolated) {
                this._bgEl.style.backgroundColor = '#' + ('000000' + interpolated.themeColor.toString(16)).slice(-6);
            } else {
                this._bgEl.style.backgroundColor = this._options.themeColors[timeOfDay];
            }
        }

        // Theme color meta tag
        if (this._options.updateThemeColor) {
            var meta = document.getElementById('theme-color-meta') ||
                       document.querySelector('meta[name="theme-color"]');
            if (meta) {
                var themeHex;
                var useWeatherTheme = weatherCat !== 'clear' && weatherCat !== 'partly' &&
                    WEATHER_THEME_INTS[weatherCat];

                if (useWeatherTheme) {
                    var lowerPhase = interpolated ? interpolated.phase : timeOfDay;
                    var wtInt = WEATHER_THEME_INTS[weatherCat][lowerPhase] || WEATHER_THEME_INTS[weatherCat].day;
                    themeHex = '#' + ('000000' + wtInt.toString(16)).slice(-6);
                } else if (interpolated) {
                    themeHex = '#' + ('000000' + interpolated.themeColor.toString(16)).slice(-6);
                } else {
                    themeHex = this._options.themeColors[timeOfDay];
                }
                meta.content = themeHex;
            }
        }

        // Cloud opacity
        var cloudOpacity = options.cloudOpacity !== undefined ? options.cloudOpacity : 1.0;

        // Vanta — freeze render loop at extreme blur to save GPU.
        // Only fog with high cloud cover reaches this threshold.
        var hideCloudCanvas = blur >= 10;

        if (window.VANTA && window.VANTA.CLOUDS && !this._deferVanta) {
            var vantaOpts = Object.assign({}, options, this._options.vantaOptions);
            // Remove non-Vanta keys
            delete vantaOpts.timeOfDay;
            delete vantaOpts.cloudOpacity;
            delete vantaOpts.blur;
            delete vantaOpts.hazeOpacity;
            delete vantaOpts.colorConvergence;
            delete vantaOpts.weatherCategory;
            delete vantaOpts._interpolated;

            if (this._vantaEffect) {
                if (hideCloudCanvas && !this._vantaFrozen) {
                    // Freeze Vanta: stop its render loop to save GPU
                    if (this._vantaEffect.req) {
                        cancelAnimationFrame(this._vantaEffect.req);
                        this._vantaEffect.req = null;
                    }
                    this._vantaFrozen = true;
                } else if (!hideCloudCanvas && this._vantaFrozen) {
                    // Unfreeze: restart Vanta by reapplying options
                    this._vantaEffect.setOptions(vantaOpts);
                    this._vantaFrozen = false;
                } else if (!hideCloudCanvas) {
                    this._vantaEffect.setOptions(vantaOpts);
                }
            } else {
                this._vantaEffect = VANTA.CLOUDS(Object.assign({
                    el: this._cloudsEl,
                    mouseControls: false,
                    touchControls: false,
                    gyroControls: false,
                    minHeight: 200,
                    minWidth: 200
                }, vantaOpts));
                this._vantaFrozen = false;
            }

            // Cloud layer opacity and blur
            if (this._paused || hideCloudCanvas) {
                this._cloudsEl.style.opacity = '0';
                this._cloudsEl.style.filter = 'none';
            } else {
                this._cloudsEl.style.opacity = String(cloudOpacity);
                this._cloudsEl.style.filter = blur > 0 ? 'blur(' + blur + 'px)' : 'none';
            }
        }

        // Atmospheric haze overlay (expanded from fog-only to all weather categories)
        if (this._options.enableFog && this._fogEl) {
            if (hazeOpacity > 0) {
                // Use interpolated haze RGB array
                var hazeRGB = interpolated ? interpolated.hazeColor : null;
                this._fogEl.style.background = this._buildHazeGradient(hazeRGB || timeOfDay);
                this._fogEl.style.opacity = String(hazeOpacity);
            } else {
                this._fogEl.style.opacity = '0';
            }
        } else if (this._fogEl) {
            this._fogEl.style.opacity = '0';
        }

        // Particles — only restart if type or intensity changed
        if (this._options.enableParticles && this._weather && !this._paused) {
            var pType = getWeatherParticleType(this._weather.weatherCode);
            var pIntensity = getWeatherParticleIntensity(this._weather.weatherCode);
            if (pType !== this._currentParticleType || pIntensity !== this._currentParticleIntensity) {
                this._startParticles(pType, pIntensity, timeOfDay);
            } else if (this._particleTimeOfDay !== timeOfDay) {
                this._particleTimeOfDay = timeOfDay;
            }
        } else {
            this._stopParticles();
        }

        // Emit events
        if (previousTimeOfDay !== timeOfDay) {
            this._emit('timechange', {
                timeOfDay: timeOfDay,
                isDaytime: timeOfDay === 'day' || timeOfDay === 'dawn',
                previousTimeOfDay: previousTimeOfDay
            });
        }

        this._emit('render', { options: options, weather: this._weather });
    };

    SkyEffect.prototype._fetchWeather = async function () {
        try {
            var url = 'https://api.open-meteo.com/v1/forecast?latitude=' +
                this._options.latitude + '&longitude=' + this._options.longitude +
                '&current=temperature_2m,weather_code,cloud_cover,is_day' +
                '&daily=sunrise,sunset&timezone=' + encodeURIComponent(this._options.timezone) +
                '&forecast_days=1';
            var response = await fetch(url);
            if (!response.ok) throw new Error('Weather API error: ' + response.status);
            var data = await response.json();

            var sunriseStr = data.daily && data.daily.sunrise && data.daily.sunrise[0]
                ? data.daily.sunrise[0].split('T')[1] : null;
            var sunsetStr = data.daily && data.daily.sunset && data.daily.sunset[0]
                ? data.daily.sunset[0].split('T')[1] : null;

            return {
                weatherCode: data.current.weather_code,
                cloudCover: data.current.cloud_cover,
                isDay: data.current.is_day === 1,
                temperature: data.current.temperature_2m,
                sunrise: parseTimeToMins(sunriseStr),
                sunset: parseTimeToMins(sunsetStr)
            };
        } catch (e) {
            console.warn('SkyEffect: weather fetch failed, using defaults.', e.message);
            this._emit('weathererror', { error: e });
            return null;
        }
    };

    SkyEffect.prototype._startParticles = function (type, intensity, timeOfDay) {
        this._stopParticles();
        if (!type || !this._particlesCanvas) return;

        this._currentParticleType = type;
        this._currentParticleIntensity = intensity;
        this._particleTimeOfDay = timeOfDay;
        var w = this._particlesCanvas.width;
        var h = this._particlesCanvas.height;
        var count = type === 'rain'
            ? Math.floor(150 + intensity * 350)
            : Math.floor(60 + intensity * 140);

        this._particles = [];
        for (var i = 0; i < count; i++) {
            this._particles.push(new WeatherParticle(type, intensity, w, h));
        }

        this._lastParticleFrame = performance.now();
        var self = this;

        function animate(currentTime) {
            var deltaTime = Math.min(currentTime - self._lastParticleFrame, 50);
            self._lastParticleFrame = currentTime;
            self._particlesCtx.clearRect(0, 0, self._particlesCanvas.width, self._particlesCanvas.height);
            for (var i = 0; i < self._particles.length; i++) {
                self._particles[i].update(deltaTime);
                self._particles[i].draw(self._particlesCtx, self._particleTimeOfDay);
            }
            self._particleAnimId = requestAnimationFrame(animate);
        }
        this._particleAnimId = requestAnimationFrame(animate);
    };

    SkyEffect.prototype._stopParticles = function () {
        if (this._particleAnimId) {
            cancelAnimationFrame(this._particleAnimId);
            this._particleAnimId = null;
        }
        this._particles = [];
        this._currentParticleType = null;
        this._currentParticleIntensity = null;
        if (this._particlesCtx && this._particlesCanvas) {
            this._particlesCtx.clearRect(0, 0, this._particlesCanvas.width, this._particlesCanvas.height);
        }
    };

    SkyEffect.prototype._onVisibilityChange = function () {
        if (document.hidden) {
            if (this._vantaEffect && !this._vantaFrozen) this._vantaEffect.setOptions({ speed: 0 });
            if (this._particleAnimId) {
                this._particlesWereRunning = true;
                cancelAnimationFrame(this._particleAnimId);
                this._particleAnimId = null;
            }
        } else if (!this._paused) {
            var reducedMotion = this._options.respectReducedMotion &&
                window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (!reducedMotion) {
                if (this._vantaEffect && !this._vantaFrozen) this._vantaEffect.setOptions({ speed: this._currentSpeed });
                if (this._particlesWereRunning && this._particles.length > 0) {
                    this._lastParticleFrame = performance.now();
                    var self = this;
                    function animate(currentTime) {
                        var deltaTime = Math.min(currentTime - self._lastParticleFrame, 50);
                        self._lastParticleFrame = currentTime;
                        self._particlesCtx.clearRect(0, 0, self._particlesCanvas.width, self._particlesCanvas.height);
                        for (var i = 0; i < self._particles.length; i++) {
                            self._particles[i].update(deltaTime);
                            self._particles[i].draw(self._particlesCtx, self._particleTimeOfDay);
                        }
                        self._particleAnimId = requestAnimationFrame(animate);
                    }
                    self._particleAnimId = requestAnimationFrame(animate);
                }
            }
            this._particlesWereRunning = false;
        }
    };

    SkyEffect.prototype._onResize = function () {
        this._resizeCanvas();
    };

    return SkyEffect;
}));
