"use client";

/**
 * Registers the app-shell cache.
 *
 * The service worker is what makes the field app open at all on a dead
 * connection; the IndexedDB queue then handles what the farmer does once it is
 * open. Registration failures are swallowed on purpose -- an unavailable cache
 * degrades the app, it does not break it.
 */

import { useEffect } from "react";

export function ServiceWorker() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    if (window.location.protocol !== "https:" && window.location.hostname !== "localhost") {
      return;
    }
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* No offline shell; the queue still works. */
    });
  }, []);

  return null;
}
