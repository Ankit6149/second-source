/** Tab-local notes only; these are not an assistant conversation or cloud evidence. */
const prefix = 'ss-notes:';
const validId = (id: string) => /^[A-Za-z0-9_-]{1,80}$/.test(id);
const keyFor = (owner: string, investigation: string) => {
  if (!validId(owner) || !validId(investigation)) throw new Error('Invalid note owner or investigation');
  return `${prefix}${owner}:${investigation}`;
};

export function loadNotes(store: Storage, owner: string, investigation: string): string[] {
  try {
    const raw = store.getItem(keyFor(owner, investigation));
    if (!raw || raw.length > 200_000) return [];
    const notes: unknown = JSON.parse(raw);
    return Array.isArray(notes) && notes.length <= 100 && notes.every(n => typeof n === 'string' && n.length <= 4000) ? notes : [];
  } catch { return []; }
}

export function saveNotes(store: Storage, owner: string, investigation: string, notes: string[]): boolean {
  try {
    if (notes.length > 100 || notes.some(n => n.length > 4000)) return false;
    const raw = JSON.stringify(notes); if (raw.length > 200_000) return false;
    store.setItem(keyFor(owner, investigation), raw); return true;
  } catch { return false; }
}

export function clearOwnerNotes(store: Storage, owner: string): void {
  if (!validId(owner)) return;
  try {
    for (let i = store.length - 1; i >= 0; i--) {
      const key = store.key(i); if (key?.startsWith(`${prefix}${owner}:`)) store.removeItem(key);
    }
  } catch { /* Session may be unavailable; the UI must remain usable. */ }
}
