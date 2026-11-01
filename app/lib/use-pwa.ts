import { useCallback, useEffect, useRef, useState } from 'react';

type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

type PwaState = {
  online: boolean;
  installAvailable: boolean;
  updateReady: boolean;
  installed: boolean;
};

/**
 * Opt-in updates: never silently replace the app during a source-linked review.
 * PWA support is disabled on Vite's fixture dev server so test data cannot be
 * cached across unit/browser test cases.
 */
export function usePwa() {
  const [state, setState] = useState<PwaState>(() => ({
    online: navigator.onLine,
    installAvailable: false,
    updateReady: false,
    installed: window.matchMedia('(display-mode: standalone)').matches,
  }));
  const promptRef = useRef<InstallPrompt | null>(null);
  const registrationRef = useRef<ServiceWorkerRegistration | null>(null);
  const upgradeRequested = useRef(false);

  useEffect(() => {
    let alive = true;
    const updateOnline = () => setState((previous) => ({
      ...previous, online: navigator.onLine,
    }));
    const installed = () => {
      promptRef.current = null;
      setState((previous) => ({
        ...previous, installed: true, installAvailable: false,
      }));
    };
    const canInstall = (event: Event) => {
      event.preventDefault();
      promptRef.current = event as InstallPrompt;
      setState((previous) => ({ ...previous, installAvailable: true }));
    };
    const controllerChanged = () => {
      if (upgradeRequested.current) window.location.reload();
    };
    window.addEventListener('online', updateOnline);
    window.addEventListener('offline', updateOnline);
    window.addEventListener('appinstalled', installed);
    window.addEventListener('beforeinstallprompt', canInstall);
    if (import.meta.env.PROD && 'serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('controllerchange', controllerChanged);
      void navigator.serviceWorker.register(
        import.meta.env.BASE_URL + 'service-worker.js',
        { scope: import.meta.env.BASE_URL, updateViaCache: 'none' },
      ).then((registration) => {
        if (!alive) return;
        registrationRef.current = registration;
        const check = () => {
          if (registration.waiting && navigator.serviceWorker.controller && alive) {
            setState((previous) => ({ ...previous, updateReady: true }));
          }
        };
        check();
        registration.addEventListener('updatefound', () => {
          const installing = registration.installing;
          installing?.addEventListener('statechange', () => {
            if (installing.state === 'installed') check();
          });
        });
        // Best-effort update detection on app resume, not a background poll.
        const refresh = () => {
          if (document.visibilityState === 'visible' && navigator.onLine) {
            void registration.update().catch(() => {});
          }
        };
        document.addEventListener('visibilitychange', refresh);
        cleanupUpdates = () => document.removeEventListener('visibilitychange', refresh);
      }).catch(() => {
        // The dashboard still works online when browser PWA APIs are unavailable.
      });
    }
    let cleanupUpdates: (() => void) | null = null;
    return () => {
      alive = false;
      cleanupUpdates?.();
      window.removeEventListener('online', updateOnline);
      window.removeEventListener('offline', updateOnline);
      window.removeEventListener('appinstalled', installed);
      window.removeEventListener('beforeinstallprompt', canInstall);
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.removeEventListener('controllerchange', controllerChanged);
      }
    };
  }, []);

  const install = useCallback(async () => {
    const prompt = promptRef.current;
    if (!prompt) return;
    promptRef.current = null;
    setState((previous) => ({ ...previous, installAvailable: false }));
    try {
      await prompt.prompt();
      await prompt.userChoice;
    } catch {
      // A dismissed/unsupported browser prompt does not affect data loading.
    }
  }, []);

  const applyUpdate = useCallback(() => {
    const worker = registrationRef.current?.waiting;
    if (!worker) return;
    upgradeRequested.current = true;
    worker.postMessage({ type: 'SKIP_WAITING' });
  }, []);

  return { ...state, install, applyUpdate };
}
