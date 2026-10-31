import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { Window } from 'happy-dom';

const html = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8');
const assets = new URL('../dist/assets/', import.meta.url);
const script = (await readdir(assets)).find(name => name.endsWith('.js'));
assert.ok(script, 'production bundle exists');
const bundle = await readFile(new URL(script, assets), 'utf8');

function workspace(path = '/') {
  const window = new Window({ url: `https://preview.example${path}`, settings: {
    disableJavaScriptFileLoading: true, disableCSSFileLoading: true,
  } });
  window.document.write(html);
  window.eval(bundle);
  return window;
}

test('composer stays outside history and sending creates a local note without a fake result', () => {
  const window = workspace();
  try {
    const doc = window.document;
    const composer = doc.querySelector('#composer');
    const input = doc.querySelector('#promptInput');
    assert.ok(composer && input);
    assert.equal(doc.querySelector('#scrollArea').contains(composer), false);
    input.value = 'Investigate a workflow';
    input.dispatchEvent(new window.Event('input', { bubbles: true }));
    composer.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    assert.match(doc.querySelector('#content').textContent, /Investigate a workflow/);
    assert.match(doc.querySelector('#content').textContent, /does not yet save conversations or answer follow-up questions/);
    assert.equal(doc.querySelector('#promptInput'), input);
    assert.equal(input.value, '');
  } finally { window.happyDOM.abort(); }
});

test('unconfigured sign-in and target selection explain their unavailable state', () => {
  const window = workspace();
  try {
    const doc = window.document;
    doc.querySelector('[data-action="account"]').click();
    assert.equal(doc.querySelector('dialog').open, true);
    assert.match(doc.querySelector('dialog').textContent, /not configured/i);
    assert.doesNotMatch(doc.querySelector('dialog').textContent, /signed in/i);
    doc.querySelector('[data-action="close-dialog"]').click();
    doc.querySelector('[data-action="select-target"]').click();
    assert.equal(doc.querySelector('dialog').open, true);
    assert.match(doc.querySelector('dialog').textContent, /not configured/i);
  } finally { window.happyDOM.abort(); }
});

test('suggestion populates the composer and keyboard submission preserves it', () => {
  const window = workspace();
  try {
    const doc = window.document;
    doc.querySelector('[data-suggestion]').click();
    const input = doc.querySelector('#promptInput');
    assert.match(input.value, /owned ledger/);
    assert.equal(doc.activeElement, input);
    input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true }));
    assert.match(input.value, /owned ledger/);
    input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    assert.equal(doc.querySelector('#promptInput'), input);
    assert.equal(input.value, '');
    assert.match(doc.querySelector('#content').textContent, /owned ledger/);
  } finally { window.happyDOM.abort(); }
});

test('showroom actions remain separate from investigation results', () => {
  const window = workspace('/?screen=system');
  try {
    const doc = window.document;
    assert.match(doc.querySelector('#content').textContent, /component showroom/i);
    assert.match(doc.querySelector('#content').textContent, /not investigation results/i);
    doc.querySelector('[data-action="sample-dialog"]').click();
    assert.equal(doc.querySelector('dialog').open, true);
    assert.match(doc.querySelector('dialog').textContent, /component example/i);
  } finally { window.happyDOM.abort(); }
});
