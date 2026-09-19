/**
 * The offline report queue.
 *
 * This is the part of the product that decides whether it is usable in the
 * places it is meant for. A farmer standing in a field with no signal must be
 * able to finish a report, put the phone away, and have it arrive later without
 * thinking about it.
 *
 * Design notes:
 *
 * * **IndexedDB, not localStorage.** The queue holds structured records and has
 *   to survive a tab close; localStorage is a synchronous string store that
 *   blocks the main thread and is easy to blow the quota on.
 * * **The client mints the key.** `client_uuid` is generated before the report
 *   is ever queued, so a retry after a timeout is settled server-side as a
 *   duplicate rather than stored as a second report.
 * * **Rejections leave the queue.** A report the server will never accept (a
 *   farm that no longer exists, a validation failure) is moved to a `failed`
 *   state and surfaced, rather than retried forever in a loop the user cannot
 *   see or clear.
 */

import { ApiError, api } from "./api";
import type { ReportDraft } from "./types";

const DB_NAME = "vanraksha";
const DB_VERSION = 1;
const STORE = "outbox";

export type QueueState = "pending" | "failed";

export interface QueuedReport {
  client_uuid: string;
  draft: ReportDraft;
  queued_at: string;
  attempts: number;
  state: QueueState;
  last_error?: string;
}

function supported(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window;
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "client_uuid" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDatabase();
  return new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const request = work(transaction.objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => db.close();
  });
}

export async function enqueue(draft: ReportDraft): Promise<QueuedReport> {
  const entry: QueuedReport = {
    client_uuid: draft.client_uuid,
    draft: { ...draft, submitted_offline: true },
    queued_at: new Date().toISOString(),
    attempts: 0,
    state: "pending",
  };
  if (!supported()) return entry;
  await withStore("readwrite", (store) => store.put(entry));
  notify();
  return entry;
}

export async function listQueue(): Promise<QueuedReport[]> {
  if (!supported()) return [];
  try {
    const rows = await withStore<QueuedReport[]>("readonly", (store) => store.getAll());
    return rows.sort((a, b) => a.queued_at.localeCompare(b.queued_at));
  } catch {
    return [];
  }
}

export async function pendingCount(): Promise<number> {
  return (await listQueue()).filter((row) => row.state === "pending").length;
}

export async function remove(clientUuid: string): Promise<void> {
  if (!supported()) return;
  await withStore("readwrite", (store) => store.delete(clientUuid));
  notify();
}

export async function clearFailed(): Promise<void> {
  const rows = await listQueue();
  await Promise.all(rows.filter((r) => r.state === "failed").map((r) => remove(r.client_uuid)));
}

async function markFailed(entry: QueuedReport, reason: string): Promise<void> {
  if (!supported()) return;
  await withStore("readwrite", (store) =>
    store.put({ ...entry, state: "failed", attempts: entry.attempts + 1, last_error: reason }),
  );
}

async function markRetry(entry: QueuedReport, reason: string): Promise<void> {
  if (!supported()) return;
  await withStore("readwrite", (store) =>
    store.put({ ...entry, attempts: entry.attempts + 1, last_error: reason }),
  );
}

export interface FlushOutcome {
  attempted: number;
  accepted: number;
  duplicates: number;
  rejected: number;
  stillQueued: number;
  offline: boolean;
}

/**
 * Send everything pending in one batch.
 *
 * The server settles each item independently, so one malformed report does not
 * cost the farmer the rest of the week's work.
 */
export async function flush(deviceId?: string): Promise<FlushOutcome> {
  const queue = (await listQueue()).filter((row) => row.state === "pending");
  const outcome: FlushOutcome = {
    attempted: queue.length, accepted: 0, duplicates: 0,
    rejected: 0, stillQueued: queue.length, offline: false,
  };
  if (!queue.length) return outcome;

  try {
    const result = await api.syncReports(queue.map((row) => row.draft), deviceId);

    for (const item of result.results) {
      const entry = queue.find((row) => row.client_uuid === item.client_uuid);
      if (!entry) continue;

      if (item.status === "accepted" || item.status === "duplicate") {
        await remove(item.client_uuid);
      } else {
        // The server will not accept this one however many times it is sent.
        await markFailed(entry, item.detail ?? "The server rejected this report.");
      }
    }

    outcome.accepted = result.accepted;
    outcome.duplicates = result.duplicates;
    outcome.rejected = result.rejected;
  } catch (error) {
    const reason =
      error instanceof ApiError ? error.message : "Sync failed; will try again.";
    if (error instanceof ApiError && !error.isRetryable) {
      // A 401/403 means the whole batch needs attention, not a silent retry loop.
      for (const entry of queue) await markFailed(entry, reason);
      outcome.rejected = queue.length;
    } else {
      outcome.offline = true;
      for (const entry of queue) await markRetry(entry, reason);
    }
  }

  outcome.stillQueued = await pendingCount();
  notify();
  return outcome;
}

// ---------------------------------------------------------------------------
// Change notification, so any mounted indicator stays in step with the queue.
// ---------------------------------------------------------------------------

const QUEUE_EVENT = "vanraksha:queue-changed";

function notify(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(QUEUE_EVENT));
}

export function onQueueChange(handler: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(QUEUE_EVENT, handler);
  return () => window.removeEventListener(QUEUE_EVENT, handler);
}

/**
 * Try to submit now; fall back to the queue when the network is not there.
 *
 * Returns whether the report reached the server, so the caller can show the
 * triage verdict straight away when it did, and an honest "saved on this
 * device" when it did not.
 */
export async function submitOrQueue(draft: ReportDraft) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    await enqueue(draft);
    return { delivered: false as const, queued: true as const };
  }

  try {
    const report = await api.createReport(draft);
    return { delivered: true as const, report };
  } catch (error) {
    if (error instanceof ApiError && error.isRetryable) {
      await enqueue(draft);
      return { delivered: false as const, queued: true as const };
    }
    throw error;
  }
}
