import assert from 'node:assert/strict';
import test from 'node:test';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Visitors use the app's server key: the browser must never read it. */
const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const files = readdirSync(src).filter(f => f.endsWith('.ts'));

test('frontend reads only allowlisted public env vars', () => {
  const allowed = new Set([
    'VITE_API_ORIGIN', 'VITE_SUPABASE_URL', 'VITE_SUPABASE_PUBLISHABLE_KEY',
    'VITE_ENGINE_URL',
    'DEV', 'MODE', 'PROD',
  ]);
  for (const f of files) {
    const body = readFileSync(join(src, f), 'utf-8');
    for (const m of body.matchAll(/import\.meta\.env\.([A-Za-z0-9_]+)/g)) {
      assert.ok(allowed.has(m[1]), `${f} reads non-allowlisted env ${m[1]}`);
    }
    assert.ok(!/process\.env/.test(body), `${f} must not touch process.env`);
  }
});

test('frontend never wires server-side model credentials', () => {
  for (const f of files) {
    const body = readFileSync(join(src, f), 'utf-8');
    assert.ok(!/import\.meta\.env\.(MODEL_API_KEY|SECOND_SOURCE_)/.test(body),
      `${f} references a server-side model credential`);
  }
});
