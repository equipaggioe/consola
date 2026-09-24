// Camera kit: the plumbing every repo camera shares (ADR-0051).
//
// A repo camera imports this file from the path Consola passes in `--kit`:
//
//   const kitPath = process.argv[process.argv.indexOf('--kit') + 1];
//   const kit = await import(pathToFileURL(kitPath).href);
//
// It has no dependencies of its own: it lives outside the repo, so it cannot
// resolve the repo's `node_modules`. Whatever needs Playwright receives the
// browser from the camera.
//
// Data never goes into a database (ADR-0050): the clients talk to a fake
// server that answers from the repo's scenario, and a route the fake server
// does not map fails the run.

import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { createServer } from 'node:http';
import { join } from 'node:path';

// --- Contract with Consola (ADR-0049) -----------------------------------------

/** The contract's themes, as the browser's `prefers-color-scheme` names them. */
export const COLOR_SCHEMES = { claro: 'light', oscuro: 'dark' };

const LIST_FLAGS = ['apps', 'themes', 'languages'];
const VALUE_FLAGS = ['output', 'device', 'kit'];

/**
 * Reads the arguments Consola passes and checks them against what the camera
 * can take.
 *
 * `supported` maps each app to the themes and languages it can be shot in, and
 * `mobile: true` for the ones that need `--device`:
 *
 *   { panel: { themes: ['oscuro'], languages: ['es'] },
 *     app: { themes: ['oscuro'], languages: ['es'], mobile: true } }
 *
 * Anything asked for that is not supported is an error, never skipped.
 */
export const parseArgs = (argv, supported) => {
	const args = { device: '' };
	for (let i = 0; i < argv.length; i += 2) {
		const flag = argv[i].replace(/^--/, '');
		const value = argv[i + 1];
		if (!argv[i].startsWith('--') || ![...LIST_FLAGS, ...VALUE_FLAGS].includes(flag)) {
			throw new Error(`Argumento desconocido: ${argv[i]}`);
		}
		if (value === undefined || value.startsWith('--')) throw new Error(`Falta el valor de --${flag}.`);
		args[flag] = LIST_FLAGS.includes(flag) ? value.split(',').filter(Boolean) : value;
	}
	for (const flag of [...LIST_FLAGS, 'output', 'kit']) {
		if (!args[flag] || args[flag].length === 0) throw new Error(`Falta --${flag}.`);
	}

	const problems = [];
	for (const app of args.apps) {
		const spec = supported[app];
		if (!spec) {
			problems.push(`${app}: esta cámara no la captura (sabe: ${Object.keys(supported).join(', ')})`);
			continue;
		}
		for (const theme of args.themes) {
			if (!(theme in COLOR_SCHEMES)) problems.push(`${theme}: no es un tema del contrato`);
			else if (!spec.themes.includes(theme)) problems.push(`${app}: no tiene el tema ${theme}`);
		}
		for (const language of args.languages) {
			if (!spec.languages.includes(language)) problems.push(`${app}: no tiene el idioma ${language}`);
		}
		if (spec.mobile && !args.device) problems.push(`${app}: es una app móvil y falta --device`);
	}
	if (problems.length) throw new Error(`No se puede capturar lo pedido:\n  ${[...new Set(problems)].join('\n  ')}`);
	return args;
};

/** Every theme × language pair asked for, in a stable order. */
export const combinations = (args) =>
	args.themes.flatMap((theme) => args.languages.map((language) => ({ theme, language })));

/** Where a raw shot goes: `<output>/<app>/<screen>.<theme>.<language>.png`. */
export const shotPath = (output, app, screen, theme, language) => {
	if (/[.\\/]/.test(screen)) throw new Error(`Nombre de pantalla inválido: "${screen}" (sin puntos ni barras).`);
	const dir = join(output, app);
	mkdirSync(dir, { recursive: true });
	return join(dir, `${screen}.${theme}.${language}.png`);
};

/** Runs the camera and turns any error into a message and a non-zero exit. */
export const main = async (camera) => {
	try {
		await camera();
	} catch (error) {
		console.error(error instanceof Error ? error.message : String(error));
		if (process.env.CAMARA_STACK) console.error(error);
		process.exit(1);
	}
};

// --- Processes ----------------------------------------------------------------

/** Resolves when the process exits with 0; rejects with its name otherwise. */
const waitForExit = (child, name) =>
	new Promise((resolve, reject) => {
		child.on('exit', (code) => (code === 0 ? resolve() : reject(new Error(`${name} terminó con código ${code}.`))));
		child.on('error', reject);
	});

/** Polls `url` until it answers 2xx, or fails after `seconds`. */
const waitForUrl = async (url, seconds = 60) => {
	for (let i = 0; i < seconds * 2; i++) {
		try {
			if ((await fetch(url)).ok) return;
		} catch {
			// Not up yet.
		}
		await new Promise((r) => setTimeout(r, 500));
	}
	throw new Error(`No respondió ${url} en ${seconds} s.`);
};

// --- Fake server (ADR-0050) -----------------------------------------------------

/** A handler's answer with a status other than 200. */
export const reply = (status, body) => ({ [REPLY]: true, status, body });
const REPLY = Symbol('reply');

/** The path the mobile test downloads the expanded scenario from. */
export const SCENARIO_PATH = '/__demo/scenario';

const sendJson = (res, status, body) => {
	res.writeHead(status, { 'Content-Type': 'application/json' });
	res.end(JSON.stringify(body));
};

/**
 * Starts the fake API server.
 *
 * - `routes`: `[pattern, handler]` pairs. `pattern` is an exact pathname or a
 *   RegExp; `handler(url, match, req)` returns the JSON body, or `reply()`.
 *   Only GET goes through them: writes are answered 204 and dropped.
 * - `scenario`: served at `SCENARIO_PATH` for the mobile test, which cannot
 *   take it by `--dart-define` (Windows caps the command line). `onScenario`
 *   is called after serving it: the app is up, and the device can be touched.
 * - `websockets`: `{ pathname: (socket, req) => {} }`; `socket` has
 *   `send(text)` and `onText(fn)`.
 *
 * A GET or an upgrade no route matches answers 500 and is recorded;
 * `assertComplete()` then fails naming them.
 */
export const startFakeServer = ({ port, routes, scenario, onScenario = () => {}, websockets = {} }) => {
	const unmapped = new Map();
	const miss = (what) => {
		if (!unmapped.has(what)) console.error(`[servidor ficticio] sin mapear: ${what}`);
		unmapped.set(what, (unmapped.get(what) ?? 0) + 1);
	};

	const server = createServer((req, res) => {
		// Browser clients call from the dev server's origin.
		res.setHeader('Access-Control-Allow-Origin', '*');
		res.setHeader('Access-Control-Allow-Headers', '*');
		res.setHeader('Access-Control-Allow-Methods', '*');
		if (req.method !== 'GET') {
			res.writeHead(204);
			res.end();
			return;
		}
		const url = new URL(req.url, 'http://localhost');
		if (url.pathname === SCENARIO_PATH) {
			sendJson(res, 200, scenario);
			onScenario();
			return;
		}
		for (const [pattern, handler] of routes) {
			const match = typeof pattern === 'string' ? (url.pathname === pattern ? [url.pathname] : null) : url.pathname.match(pattern);
			if (!match) continue;
			const answer = handler(url, match, req);
			if (answer?.[REPLY]) return sendJson(res, answer.status, answer.body);
			return sendJson(res, 200, answer);
		}
		miss(`GET ${url.pathname}`);
		sendJson(res, 500, { detail: `Ruta sin mapear en el servidor ficticio: ${url.pathname}` });
	});

	// Upgraded sockets leave the HTTP server's bookkeeping: `close` drops them itself.
	const upgraded = new Set();
	server.on('upgrade', (req, socket) => {
		upgraded.add(socket);
		socket.on('close', () => upgraded.delete(socket));
		const { pathname } = new URL(req.url, 'http://localhost');
		const handler = websockets[pathname];
		if (!handler) {
			miss(`WebSocket ${pathname}`);
			socket.destroy();
			return;
		}
		handler(acceptWebSocket(req, socket), req);
	});

	return new Promise((resolve, reject) => {
		server.on('error', reject);
		server.listen(port, '127.0.0.1', () =>
			resolve({
				url: `http://127.0.0.1:${server.address().port}`,
				/** Fails naming every request no route answered. */
				assertComplete() {
					if (unmapped.size === 0) return;
					const list = [...unmapped].map(([what, n]) => `${what} (${n})`).join('\n  ');
					throw new Error(`El servidor ficticio recibió pedidos que no tiene mapeados (ADR-0050):\n  ${list}`);
				},
				/** Stops listening and drops open connections: a WebSocket would keep it waiting. */
				close() {
					server.closeAllConnections();
					for (const socket of upgraded) socket.destroy();
					return new Promise((done) => server.close(() => done()));
				}
			})
		);
	});
};

// --- WebSocket ------------------------------------------------------------------
//
// The least of RFC 6455 a fake server needs: the handshake, unmasked text
// frames out, masked frames in, pong to ping and close. What goes inside the
// text frames is the app's protocol, and stays in the repo.

const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

const textFrame = (text) => {
	const data = Buffer.from(text);
	const n = data.length;
	let header;
	if (n < 126) header = Buffer.from([0x81, n]);
	else if (n < 65536) header = Buffer.from([0x81, 126, n >> 8, n & 0xff]);
	else {
		header = Buffer.alloc(10);
		header[0] = 0x81;
		header[1] = 127;
		header.writeBigUInt64BE(BigInt(n), 2);
	}
	return Buffer.concat([header, data]);
};

/** Complete frames in `buffer`, and what is left of an incomplete one. */
const readFrames = (buffer) => {
	const frames = [];
	let i = 0;
	while (buffer.length - i >= 2) {
		const opcode = buffer[i] & 0x0f;
		let length = buffer[i + 1] & 0x7f;
		let cursor = i + 2;
		if (length === 126) {
			if (buffer.length < cursor + 2) break;
			length = buffer.readUInt16BE(cursor);
			cursor += 2;
		} else if (length === 127) {
			if (buffer.length < cursor + 8) break;
			length = Number(buffer.readBigUInt64BE(cursor));
			cursor += 8;
		}
		if (buffer.length < cursor + 4 + length) break;
		const mask = buffer.subarray(cursor, cursor + 4);
		const data = Buffer.from(buffer.subarray(cursor + 4, cursor + 4 + length));
		for (let j = 0; j < data.length; j++) data[j] ^= mask[j % 4];
		frames.push({ opcode, data });
		i = cursor + 4 + length;
	}
	return { frames, rest: buffer.subarray(i) };
};

/** Completes the handshake; returns `{ send(text), onText(fn) }`. */
const acceptWebSocket = (req, socket) => {
	const key = req.headers['sec-websocket-key'];
	if (!key) {
		socket.destroy();
		throw new Error('Pedido de WebSocket sin Sec-WebSocket-Key.');
	}
	const accept = createHash('sha1').update(key + WS_GUID).digest('base64');
	socket.write(
		'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n' +
			`Sec-WebSocket-Accept: ${accept}\r\n\r\n`
	);

	const listeners = [];
	let pending = Buffer.alloc(0);
	socket.on('data', (chunk) => {
		const { frames, rest } = readFrames(Buffer.concat([pending, chunk]));
		pending = rest;
		for (const { opcode, data } of frames) {
			if (opcode === 0x8) return socket.end();
			if (opcode === 0x9) {
				socket.write(Buffer.concat([Buffer.from([0x8a, data.length]), data]));
				continue;
			}
			if (opcode === 0x1) for (const fn of listeners) fn(data.toString('utf8'));
		}
	});
	socket.on('error', () => socket.destroy());
	return {
		send: (text) => socket.write(textFrame(text)),
		onText: (fn) => listeners.push(fn)
	};
};

// --- Web ------------------------------------------------------------------------

/**
 * Starts the repo's Vite dev server for one app and waits for `readyPath`.
 *
 * Vite runs with this same Node and without `npx` or a shell, so `stop()`
 * reaches it and not a middleman that leaves it holding the port. It does not
 * inherit `VSCODE_CWD`: with it, UnoCSS's icon preset believes it runs inside
 * the editor and loads no local collection.
 */
export const startVite = async ({ appDir, port, env = {}, readyPath = '/' }) => {
	const { VSCODE_CWD: _, ...inherited } = process.env;
	const vite = spawn(
		process.execPath,
		[join(appDir, 'node_modules', 'vite', 'bin', 'vite.js'), 'dev', '--port', String(port), '--strictPort'],
		{ cwd: appDir, env: { ...inherited, ...env }, stdio: 'ignore' }
	);
	const origin = `http://localhost:${port}`;
	try {
		await waitForUrl(origin + readyPath, 60);
	} catch (error) {
		vite.kill();
		throw error;
	}
	return { origin, stop: () => vite.kill() };
};

/**
 * A page for one theme and language: color scheme, locale, time zone and a
 * clock that starts at `now` and runs from there.
 */
export const openPage = async (browser, { theme, language, timezoneId, now, viewport, deviceScaleFactor = 2 }) => {
	const context = await browser.newContext({
		viewport,
		deviceScaleFactor,
		colorScheme: COLOR_SCHEMES[theme],
		locale: language,
		timezoneId
	});
	const page = await context.newPage();
	if (now) await page.clock.install({ time: now });
	page.on('pageerror', (error) => console.warn(`  [página] ${error.message}`));
	return page;
};

const isReload = (error) => /context was destroyed|navigat/i.test(String(error));

/**
 * Runs `fn(page)` again if the page reloaded under it. Cold, Vite optimizes
 * dependencies and reloads the page mid-load.
 */
export const retryOnReload = async (page, fn, attempts = 3) => {
	for (let attempt = 1; ; attempt++) {
		await page.waitForLoadState('networkidle');
		try {
			return await fn(page);
		} catch (error) {
			if (attempt >= attempts || !isReload(error)) throw error;
		}
	}
};

/**
 * Goes to `url` and waits for `ready(page)`. If it does not come, loads the
 * page once more: a cold Vite can reload it mid-load and leave it empty.
 */
export const visit = async (page, url, ready, attempts = 2) => {
	for (let attempt = 1; ; attempt++) {
		await page.goto(url);
		try {
			await ready(page);
			return;
		} catch (error) {
			if (attempt >= attempts) throw error;
		}
	}
};

/** Leaves the page `settleMs` (fonts, local data, map tiles) and saves it. */
export const shoot = async (page, path, settleMs = 4000) => {
	await page.waitForTimeout(settleMs);
	await page.screenshot({ path });
	console.log(`  ${path}`);
};

// --- Android --------------------------------------------------------------------

const pad = (n) => String(n).padStart(2, '0');

/**
 * `adb` on one device. The clock needs root (`adb root`), which emulators
 * without Play Store grant.
 */
export const android = (device) => {
	const adb = (...args) => execFileSync('adb', ['-s', device, ...args], { encoding: 'utf8' });
	return {
		adb,
		setTimezone: (timezone) => adb('shell', 'service', 'call', 'alarm', '3', 's16', timezone),
		root() {
			adb('root');
			adb('wait-for-device');
		},
		/**
		 * Stops automatic time and sets the clock. Call it once the app is up
		 * (`onScenario`): a jump before confuses `flutter drive`, which looks
		 * for the VM port in logcat by time.
		 */
		setClock(at) {
			adb('shell', 'settings', 'put', 'global', 'auto_time', '0');
			adb('shell', 'date', `${pad(at.getMonth() + 1)}${pad(at.getDate())}${pad(at.getHours())}${pad(at.getMinutes())}${at.getFullYear()}.00`);
		},
		restoreClock: () => adb('shell', 'settings', 'put', 'global', 'auto_time', '1')
	};
};

/**
 * Runs an integration test with `flutter drive` for one theme and language.
 *
 * The test gets `SHOTS_THEME` and `SHOTS_LANGUAGE` as `--dart-define`. The
 * host-side driver gets `SHOTS_DIR` and `SHOTS_SUFFIX` in its environment and
 * saves each screenshot as `<SHOTS_DIR>/<name>.<SHOTS_SUFFIX>.png`, which is
 * the contract's name.
 */
export const flutterDrive = ({ appDir, device, driver, target, output, app, theme, language, defines = {} }) => {
	const dir = join(output, app);
	mkdirSync(dir, { recursive: true });
	const allDefines = { ...defines, SHOTS_THEME: theme, SHOTS_LANGUAGE: language };
	return waitForExit(
		spawn(
			'flutter',
			[
				'drive',
				...(process.env.CAMARA_VERBOSE ? ['-v'] : []),
				`--driver=${driver}`,
				`--target=${target}`,
				'-d',
				device,
				...Object.entries(allDefines).map(([k, v]) => `--dart-define=${k}=${v}`)
			],
			{
				cwd: appDir,
				stdio: 'inherit',
				shell: process.platform === 'win32',
				env: { ...process.env, SHOTS_DIR: dir, SHOTS_SUFFIX: `${theme}.${language}` }
			}
		),
		'flutter drive'
	);
};
