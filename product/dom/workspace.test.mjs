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
    assert.match(doc.querySelector('#content').textContent, /Sign in, then tell me what you would like to investigate\./);
    assert.doesNotMatch(doc.querySelector('#content').textContent, /Scope [a-f0-9]{6}|genuine backend events|does not yet save conversations/);
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
    assert.match(doc.querySelector('dialog').textContent, /not available/i);
    assert.equal(doc.querySelector('dialog').classList.contains('dialog-signin'), true);
    assert.doesNotMatch(doc.querySelector('dialog').textContent, /signed in/i);
    doc.querySelector('[data-action="close-dialog"]').click();
    doc.querySelector('[data-action="select-target"]').click();
    assert.equal(doc.querySelector('dialog').open, true);
    assert.match(doc.querySelector('dialog').textContent, /not available/i);
  } finally { window.happyDOM.abort(); }
});

test('suggestion populates the composer and keyboard submission preserves it', () => {
  const window = workspace();
  try {
    const doc = window.document;
    assert.match(doc.querySelector('h1').textContent, /Understand how software really works/);
    assert.deepEqual([...doc.querySelectorAll('[data-suggestion]')].map(button => button.textContent.trim()),
      ['Understand behavior', 'Compare versions', 'Reconstruct a workflow']);
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

test('excessively long notes are rejected without losing the draft', () => {
  const window = workspace();
  try {
    const doc = window.document;
    const input = doc.querySelector('#promptInput');
    input.value = 'x'.repeat(4001);
    input.dispatchEvent(new window.Event('input', { bubbles: true }));
    doc.querySelector('#composer').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    assert.match(doc.querySelector('#content').textContent, /within 4,000 characters/);
    assert.equal(input.value.length, 4001);
    assert.equal(doc.activeElement, input);
  } finally { window.happyDOM.abort(); }
});

test('signed-out home shows what it does, the REAL_MODEL evidence, and one research action', () => {
  const window = workspace();
  try {
    const doc = window.document;
    const home = doc.querySelector('.empty-home');
    assert.match(home.textContent, /observes software you own or are authorized to study/i);
    assert.match(home.textContent, /REAL_MODEL/);
    assert.match(home.textContent, /14\/25/);
    assert.match(home.textContent, /never merged/i);
    assert.match(home.textContent, /Signed out:/);
    const cta = home.querySelector('[data-action="research"]');
    assert.ok(cta, 'research record is the clear signed-out action');
    cta.click();
    assert.equal(doc.querySelector('dialog').open, true);
    assert.match(doc.querySelector('dialog').textContent, /14 passed/);
  } finally { window.happyDOM.abort(); }
});

test('navigation is slim and the retired showroom route lands home', () => {
  const window = workspace('/?screen=system');
  try {
    const doc = window.document;
    const nav = [...doc.querySelectorAll('.side-nav .nav-item')].map(n => n.textContent.trim());
    assert.deepEqual(nav, ['Your work', 'Reports & exports', 'Settings']);
    assert.doesNotMatch(doc.querySelector('#content').textContent, /component showroom/i);
    assert.match(doc.querySelector('#content').textContent, /Understand how software/);
  } finally { window.happyDOM.abort(); }
});

test('historical research is explicitly separated from live and NON_AI results', () => {
  const window = workspace();
  try {
    const doc = window.document;
    doc.querySelector('[data-action="research"]').click();
    const dialog = doc.querySelector('dialog');
    assert.equal(dialog.open, true);
    assert.match(dialog.textContent, /not an investigation run from this application/i);
    assert.match(dialog.textContent, /14 passed/);
    assert.match(dialog.textContent, /11 failed/);
    assert.match(dialog.textContent, /22 passed, 3 failed/);
    assert.match(dialog.textContent, /offline replay reproduced the score/i);
    assert.match(dialog.textContent, /provider signature and the ephemeral broker signature could not be verified/i);
    assert.match(dialog.textContent, /not a fair performance comparison/i);
    assert.equal(dialog.querySelector('a').href, 'https://github.com/Ankit6149/second-source/issues/25#issuecomment-6547391799');
  } finally { window.happyDOM.abort(); }
});
