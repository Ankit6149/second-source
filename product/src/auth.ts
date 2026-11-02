import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';
import { validatedOrigin } from './api';

const projectOrigin = 'https://jpqcqqbzriizxhigvjki.supabase.co';
const authUrl = validatedOrigin(import.meta.env.VITE_SUPABASE_URL || '');
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '';

// Only the dedicated project and a publishable key are valid browser settings.
export const auth: SupabaseClient | null = authUrl === projectOrigin && /^sb_publishable_[A-Za-z0-9_-]+$/.test(key)
  ? createClient(authUrl, key, { auth: { flowType: 'pkce', persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, storage: window.sessionStorage } })
  : null;

export function observeSession(callback: (session: Session | null) => void): void {
  if (!auth) { callback(null); return; }
  auth.auth.onAuthStateChange((_event, session) => { queueMicrotask(() => callback(session)); });
}

export async function signIn(): Promise<void> {
  if (!auth) throw new Error('Sign-in is not configured yet.');
  const { error } = await auth.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin + location.pathname } });
  if (error) throw new Error('Sign-in could not be started. Check the configured provider.');
}

export async function signOut(): Promise<void> {
  if (!auth) return;
  const { error } = await auth.auth.signOut({ scope: 'local' });
  if (error) throw new Error('Sign-out could not be confirmed. Try again.');
}
