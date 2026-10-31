import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clearOwnerNotes, loadNotes, saveNotes } from '../src/notes.ts';

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

test('tab notes restore for the same owner and investigation only', () => {
  const storage = new MemoryStorage();
  assert.equal(saveNotes(storage, 'owner-a', 'inv-a', ['First note', 'Follow-up']), true);
  assert.deepEqual(loadNotes(storage, 'owner-a', 'inv-a'), ['First note', 'Follow-up']);
  assert.deepEqual(loadNotes(storage, 'owner-b', 'inv-a'), []);
  assert.deepEqual(loadNotes(storage, 'owner-a', 'inv-b'), []);
  saveNotes(storage, 'owner-b', 'inv-a', ['Other account']);
  clearOwnerNotes(storage, 'owner-a');
  assert.deepEqual(loadNotes(storage, 'owner-a', 'inv-a'), []);
  assert.deepEqual(loadNotes(storage, 'owner-b', 'inv-a'), ['Other account']);
});

test('tab notes reject invalid identities, excessive data and corrupt storage', () => {
  const storage = new MemoryStorage();
  assert.equal(saveNotes(storage, '../owner', 'inv', ['note']), false);
  assert.equal(saveNotes(storage, 'owner', 'inv', ['x'.repeat(4001)]), false);
  assert.equal(saveNotes(storage, 'owner', 'inv', Array(101).fill('x')), false);
  storage.setItem('ss-notes:owner:inv', '[{"not":"a note"}]');
  assert.deepEqual(loadNotes(storage, 'owner', 'inv'), []);
});
