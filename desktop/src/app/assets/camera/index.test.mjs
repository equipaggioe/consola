// Run with `node --test camara/index.test.mjs`; `tests/test_camara.py` runs it under pytest.

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync } from 'node:fs';
import { connect } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';

import { checkSupported, combinations, parseArgs, reply, SCENARIO_PATH, shotPath, startFakeServer } from './index.mjs';

const supported = {
	panel: { themes: ['dark'], languages: ['es'] },
	app: { themes: ['dark', 'light'], languages: ['es', 'en'], mobile: true }
};
const argv = (extra = []) => ['--apps', 'panel', '--themes', 'dark', '--languages', 'es', '--output', '/raw', '--kit', '/k.mjs', ...extra];

test('lee el contrato', () => {
	const args = parseArgs(argv(), supported);
	assert.deepEqual(args, { apps: ['panel'], themes: ['dark'], languages: ['es'], output: '/raw', kit: '/k.mjs', device: '' });
	const movil = parseArgs(['--apps', 'app', '--themes', 'dark,light', '--languages', 'es,en', '--output', '/raw', '--kit', '/k', '--device', 'emulator-5554'], supported);
	assert.deepEqual(combinations(movil), [
		{ theme: 'dark', language: 'es' },
		{ theme: 'dark', language: 'en' },
		{ theme: 'light', language: 'es' },
		{ theme: 'light', language: 'en' }
	]);
});

test('lo que la cámara no soporta es error, no se salta', () => {
	assert.throws(() => parseArgs(['--apps', 'panel', '--themes', 'light', '--languages', 'es', '--output', '/r', '--kit', '/k'], supported), /panel: no tiene el tema light/);
	assert.throws(() => parseArgs(['--apps', 'panel', '--themes', 'dark', '--languages', 'en', '--output', '/r', '--kit', '/k'], supported), /panel: no tiene el idioma en/);
	assert.throws(() => parseArgs(['--apps', 'landing', '--themes', 'dark', '--languages', 'es', '--output', '/r', '--kit', '/k'], supported), /landing: esta cámara no la captura/);
	assert.throws(() => parseArgs(['--apps', 'app', '--themes', 'dark', '--languages', 'es', '--output', '/r', '--kit', '/k'], supported), /falta --device/);
	assert.throws(() => parseArgs(argv(['--pantalla', 'chat']), supported), /Argumento desconocido: --pantalla/);
	assert.throws(() => parseArgs(['--apps', 'panel', '--themes', 'dark', '--languages', 'es', '--kit', '/k'], supported), /Falta --output/);
});

test('con --supported imprime lo que captura y termina (ADR-0054)', () => {
	const kit = pathToFileURL(join(import.meta.dirname, 'index.mjs')).href;
	const camera = `const kit = await import(${JSON.stringify(kit)});
		kit.parseArgs(process.argv.slice(1), ${JSON.stringify(supported)});
		console.log('no debería llegar aquí');`;
	const out = execFileSync(process.execPath, ['--input-type=module', '-e', camera, '--', '--supported', '--kit', '/k.mjs'], { encoding: 'utf8' });
	assert.deepEqual(JSON.parse(out), supported);
});

test('lo que declara la cámara se revisa antes de usarlo', () => {
	assert.equal(checkSupported(supported), supported);
	assert.throws(() => checkSupported({}), /no declara ninguna app/);
	assert.throws(() => checkSupported({ panel: { themes: ['sepia'], languages: ['es'] } }), /panel: sepia no es un tema del contrato/);
	assert.throws(() => checkSupported({ panel: { themes: ['dark'], languages: [] } }), /panel: falta languages/);
	assert.throws(() => checkSupported({ panel: { themes: ['dark'], languages: ['es'], movil: true } }), /clave desconocida movil/);
	assert.throws(() => parseArgs(argv(), { panel: { themes: ['dark'] } }), /panel: falta languages/);
});

test('el nombre del crudo es el del contrato', () => {
	const output = mkdtempSync(join(tmpdir(), 'camara-'));
	const path = shotPath(output, 'panel', 'chat', 'dark', 'es');
	assert.equal(path, join(output, 'panel', 'chat.dark.es.png'));
	assert.ok(existsSync(join(output, 'panel')));
	assert.throws(() => shotPath(output, 'panel', 'chat.v2', 'dark', 'es'), /Nombre de pantalla/);
});

const withServer = async (options, fn) => {
	const server = await startFakeServer({ port: 0, routes: [], scenario: {}, ...options });
	try {
		await fn(server);
	} finally {
		await server.close();
	}
};

test('el servidor ficticio contesta sus rutas, lecturas y escrituras', () =>
	withServer(
		{
			routes: [
				['GET', '/rooms', (url) => [{ offset: url.searchParams.get('offset') }]],
				['GET', /^\/rooms\/([^/]+)$/, (_, m) => ({ id: m[1] })],
				['GET', '/resolve', () => reply(404, { detail: 'no' })],
				['POST', '/rooms', (_, __, ___, body) => ({ created: body.title })],
				['DELETE', /^\/rooms\/[^/]+$/, () => reply(204)]
			]
		},
		async (server) => {
			assert.deepEqual(await (await fetch(`${server.url}/rooms?offset=2`)).json(), [{ offset: '2' }]);
			assert.deepEqual(await (await fetch(`${server.url}/rooms/abc`)).json(), { id: 'abc' });
			assert.equal((await fetch(`${server.url}/resolve`)).status, 404);
			const created = await fetch(`${server.url}/rooms`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ title: 'sala' })
			});
			assert.deepEqual(await created.json(), { created: 'sala' });
			const deleted = await fetch(`${server.url}/rooms/abc`, { method: 'DELETE' });
			assert.equal(deleted.status, 204);
			assert.equal(await deleted.text(), '');
			assert.equal((await fetch(`${server.url}/rooms`, { method: 'OPTIONS' })).status, 204);
			server.assertComplete();
		}
	));

test('una ruta sin mapear contesta 500 y hace fallar la corrida (ADR-0050)', () =>
	withServer({}, async (server) => {
		assert.equal((await fetch(`${server.url}/organizations`)).status, 500);
		await fetch(`${server.url}/organizations`);
		assert.throws(() => server.assertComplete(), /GET \/organizations \(2\)/);
	}));

test('una escritura sin mapear también hace fallar la corrida (ADR-0053)', () =>
	withServer({ routes: [['GET', '/preferences', () => ({})]] }, async (server) => {
		assert.equal((await fetch(`${server.url}/preferences`, { method: 'PUT', body: '{}' })).status, 500);
		assert.throws(() => server.assertComplete(), /PUT \/preferences \(1\)/);
	}));

test('un handler roto hace fallar la corrida, no el proceso', () =>
	withServer({ routes: [['POST', '/read', () => undefined]] }, async (server) => {
		assert.equal((await fetch(`${server.url}/read`, { method: 'POST' })).status, 500);
		assert.throws(() => server.assertComplete(), /POST \/read: el handler no devolvió nada/);
	}));

test('entrega el escenario y avisa después', async () => {
	let avisado = false;
	await withServer({ scenario: { ahora: 'x' }, onScenario: () => (avisado = true) }, async (server) => {
		assert.deepEqual(await (await fetch(server.url + SCENARIO_PATH)).json(), { ahora: 'x' });
		assert.ok(avisado);
	});
});

/** A raw WebSocket client: handshake, one masked text frame, first frame back. */
const wsExchange = (url, path, text) =>
	new Promise((resolve, reject) => {
		const { port } = new URL(url);
		const socket = connect(Number(port), '127.0.0.1');
		const key = Buffer.from('0123456789abcdef').toString('base64');
		let buffer = Buffer.alloc(0);
		let upgraded = false;
		socket.on('error', reject);
		socket.on('close', () => !upgraded && resolve(null));
		socket.on('data', (chunk) => {
			buffer = Buffer.concat([buffer, chunk]);
			if (!upgraded) {
				const end = buffer.indexOf('\r\n\r\n');
				if (end < 0) return;
				const head = buffer.subarray(0, end).toString();
				const accept = createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
				assert.match(head, new RegExp(`Sec-WebSocket-Accept: ${accept.replace(/[+/]/g, '\\$&')}`));
				upgraded = true;
				buffer = buffer.subarray(end + 4);
				const data = Buffer.from(text);
				const mask = Buffer.from([1, 2, 3, 4]);
				socket.write(Buffer.concat([Buffer.from([0x81, 0x80 | data.length]), mask, data.map((b, i) => b ^ mask[i % 4])]));
			}
			if (upgraded && buffer.length >= 2 && buffer.length >= 2 + buffer[1]) {
				resolve(buffer.subarray(2, 2 + buffer[1]).toString());
				socket.destroy();
			}
		});
		socket.write(
			`GET ${path} HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n` +
				`Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`
		);
	});

test('WebSocket: el protocolo de la app va por el repo, el marco por el kit', () =>
	withServer(
		{ websockets: { '/ws': (socket) => socket.onText((text) => socket.send(`eco:${text}`)) } },
		async (server) => {
			assert.equal(await wsExchange(server.url, '/ws', 'hola'), 'eco:hola');
			assert.equal(await wsExchange(server.url, '/otro', 'hola'), null);
			assert.throws(() => server.assertComplete(), /WebSocket \/otro/);
		}
	));
