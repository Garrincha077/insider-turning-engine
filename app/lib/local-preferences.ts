import { useState, type Dispatch, type SetStateAction } from 'react';
import { storagePrefix } from './research';

// Storage can be disabled or corrupted; neither may prevent reading public data.
export function usePreference<T>(key: string, initial: T, valid: (value: unknown) => value is T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try { const saved: unknown = JSON.parse(localStorage.getItem(storagePrefix + key) ?? 'null'); return valid(saved) ? saved : initial; }
    catch { return initial; }
  });
  const update: Dispatch<SetStateAction<T>> = (next) => setValue((previous) => {
    const result = typeof next === 'function' ? (next as (v: T) => T)(previous) : next;
    try { localStorage.setItem(storagePrefix + key, JSON.stringify(result)); } catch { /* Memory-only fallback. */ }
    return result;
  });
  return [value, update];
}

export const isString = (value: unknown): value is string => typeof value === 'string';
export const isBoolean = (value: unknown): value is boolean => typeof value === 'boolean';
export const isCikList = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === 'string' && /^\d{10}$/.test(item));
export const isTimezone = (value: unknown): value is string => typeof value === 'string' && ['UTC', 'Europe/Zagreb', 'America/New_York'].includes(value);

export function resetPreferences() {
  try { Object.keys(localStorage).filter((key) => key.startsWith(storagePrefix)).forEach((key) => localStorage.removeItem(key)); } catch { /* Storage unavailable. */ }
  window.location.reload();
}
