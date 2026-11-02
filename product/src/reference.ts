export interface ReferenceHint { label: string; description: string }

/** A hint only: parsing text never visits, authorizes, or verifies a target. */
export function detectReference(text: string): ReferenceHint | null {
  const url = text.match(/\bhttps?:\/\/[^\s<>"']+/i)?.[0];
  if (url) return { label: url.slice(0, 160), description: 'User-supplied URL · not visited or authorized' };
  const domain = text.match(/\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b/i)?.[0];
  if (domain) return { label: domain.slice(0, 160), description: 'Possible website · not verified or visited' };
  if (/\b(?:ledger|fixture)\b/i.test(text)) return { label: 'Owned ledger fixture', description: 'Select a supported target after signing in' };
  return null;
}
