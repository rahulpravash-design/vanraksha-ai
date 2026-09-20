"use client";

/**
 * Field reporting.
 *
 * This screen is the one that has to work in the worst conditions the platform
 * will meet: one hand, bright sun, a patchy signal, and a farmer who is not
 * going to fill in fifteen fields. So:
 *
 * * Symptoms are tapped from the same vocabulary the scorer uses, fetched from
 *   the API so the picker and the engine can never drift apart.
 * * Free text and voice both go through the same normaliser, and anything it
 *   does not recognise is kept rather than dropped.
 * * Nothing about the form depends on being online. A submission that cannot
 *   reach the server is queued, and the farmer is told plainly which happened.
 * * The triage verdict is shown immediately when it is available, because the
 *   farmer is still standing next to the animal at that moment.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { submitOrQueue } from "@/lib/offline";
import { newClientUuid } from "@/lib/format";
import { explanationRows, isBandFloor, syndromeLabel } from "@/lib/bands";
import {
  BandBadge, Button, Card, EmptyState, Field, Notice, Spinner,
  inputClass, inputStyle,
} from "@/components/ui";
import type { Animal, Farm, HealthReport, SymptomTerm } from "@/lib/types";

const SPECIES = ["cattle", "buffalo", "goat", "sheep", "pig", "poultry"] as const;

type Outcome =
  | { kind: "delivered"; report: HealthReport }
  | { kind: "queued" }
  | null;

export default function ReportPage() {
  const [taxonomy, setTaxonomy] = useState<SymptomTerm[] | null>(null);
  const [farms, setFarms] = useState<Farm[]>([]);
  const [animals, setAnimals] = useState<Animal[]>([]);

  const [species, setSpecies] = useState<string>("cattle");
  const [selected, setSelected] = useState<string[]>([]);
  const [freeText, setFreeText] = useState("");
  const [farmId, setFarmId] = useState("");
  const [animalId, setAnimalId] = useState("");
  const [temperature, setTemperature] = useState("");
  const [duration, setDuration] = useState("");
  const [affected, setAffected] = useState("1");
  const [deaths, setDeaths] = useState("0");
  const [position, setPosition] = useState<{ lat: number; lon: number } | null>(null);

  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    api.taxonomy().then((data) => setTaxonomy(data.symptoms)).catch(() => setTaxonomy([]));
    api.listFarms().then(setFarms).catch(() => setFarms([]));
  }, []);

  useEffect(() => {
    if (!farmId) {
      setAnimals([]);
      return;
    }
    api.listAnimals(farmId).then(setAnimals).catch(() => setAnimals([]));
  }, [farmId]);

  // A coordinate is worth asking for once, quietly. Refusal is not an error --
  // the report still works, it just cannot take part in cluster detection.
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => undefined,
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 600_000 },
    );
  }, []);

  const grouped = useMemo(() => {
    if (!taxonomy) return [];
    const relevant = taxonomy.filter(
      (term) => species !== "poultry" || !term.syndromes.includes("udder"),
    );
    const buckets = new Map<string, SymptomTerm[]>();
    for (const term of relevant) {
      const key = term.syndromes[0] ?? "other";
      buckets.set(key, [...(buckets.get(key) ?? []), term]);
    }
    return [...buckets.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [taxonomy, species]);

  function toggle(code: string) {
    setSelected((current) =>
      current.includes(code) ? current.filter((c) => c !== code) : [...current, code],
    );
  }

  function reset() {
    setSelected([]);
    setFreeText("");
    setTemperature("");
    setDuration("");
    setAffected("1");
    setDeaths("0");
    setAnimalId("");
    setOutcome(null);
    setFieldErrors({});
    setFormError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFieldErrors({});
    setFormError(null);

    const draft = {
      client_uuid: newClientUuid(),
      species,
      symptoms: selected,
      symptoms_text: freeText.trim(),
      farm_id: farmId || null,
      animal_id: animalId || null,
      temperature_c: temperature ? Number(temperature) : null,
      duration_hours: duration ? Number(duration) : null,
      affected_count: Number(affected) || 1,
      deaths_count: Number(deaths) || 0,
      latitude: position?.lat ?? null,
      longitude: position?.lon ?? null,
    };

    try {
      const result = await submitOrQueue(draft);
      setOutcome(result.delivered ? { kind: "delivered", report: result.report } : { kind: "queued" });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (cause) {
      if (cause instanceof ApiError && cause.fieldErrors.length) {
        setFieldErrors(
          Object.fromEntries(cause.fieldErrors.map((e) => [e.field, e.message])),
        );
        setFormError("Some details need attention before this can be sent.");
      } else {
        setFormError(
          cause instanceof ApiError ? cause.message : "Could not save the report.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  if (outcome) {
    return <OutcomeView outcome={outcome} onAnother={reset} />;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold tracking-tight">Report a health problem</h1>
      <p className="mt-1.5 text-sm text-ink-secondary">
        Tell us what you can see. You do not need to know what it is, and you do not need
        a connection — anything saved here is sent as soon as there is one.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-5">
        <Card>
          <Field label="Which animal?" hint="Choose a species. The rest is optional.">
            <div className="flex flex-wrap gap-2">
              {SPECIES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setSpecies(option)}
                  aria-pressed={species === option}
                  className="min-h-[44px] rounded-lg border px-4 text-sm capitalize"
                  style={{
                    borderColor: species === option ? "var(--series-1)" : "var(--border)",
                    background: species === option ? "var(--series-1)" : "transparent",
                    color: species === option ? "#fff" : "var(--text-secondary)",
                  }}
                >
                  {option}
                </button>
              ))}
            </div>
          </Field>

          {farms.length > 0 ? (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field label="Farm" hint="Fills in the location and herd size">
                <select
                  value={farmId} onChange={(e) => setFarmId(e.target.value)}
                  className={inputClass} style={inputStyle}
                >
                  <option value="">Not specified</option>
                  {farms.map((farm) => (
                    <option key={farm.id} value={farm.id}>{farm.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Animal" hint="Links this to the animal's history">
                <select
                  value={animalId} onChange={(e) => setAnimalId(e.target.value)}
                  className={inputClass} style={inputStyle}
                  disabled={!animals.length}
                >
                  <option value="">Not specified</option>
                  {animals.map((animal) => (
                    <option key={animal.id} value={animal.id}>
                      {animal.tag} &middot; {animal.species}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          ) : null}
        </Card>

        <Card>
          <h2 className="text-sm font-semibold text-ink">What do you see?</h2>
          <p className="mt-1 text-xs text-ink-muted">
            Tap everything that applies. Selecting nothing is fine if you describe it below.
          </p>

          {taxonomy === null ? (
            <Spinner label="Loading the symptom list" />
          ) : (
            <div className="mt-4 space-y-4">
              {grouped.map(([syndrome, terms]) => (
                <fieldset key={syndrome}>
                  <legend className="mb-2 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                    {syndromeLabel(syndrome)}
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {terms.map((term) => {
                      const active = selected.includes(term.code);
                      return (
                        <button
                          key={term.code}
                          type="button"
                          onClick={() => toggle(term.code)}
                          aria-pressed={active}
                          className="min-h-[44px] rounded-lg border px-3.5 text-sm"
                          style={{
                            borderColor: active ? "var(--series-1)" : "var(--border)",
                            background: active
                              ? "color-mix(in srgb, var(--series-1) 14%, transparent)"
                              : "transparent",
                            color: active ? "var(--text-primary)" : "var(--text-secondary)",
                            fontWeight: active ? 600 : 400,
                          }}
                        >
                          {term.label}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
              ))}
            </div>
          )}

          <div className="mt-5">
            <Field
              label="Anything else, in your own words"
              hint="Type or speak. Nothing you write is thrown away, even if the system does not recognise it."
              error={fieldErrors["symptoms_text"]}
            >
              <div className="flex gap-2">
                <textarea
                  value={freeText}
                  onChange={(event) => setFreeText(event.target.value)}
                  rows={3}
                  className={`${inputClass} min-h-[84px] py-2.5`}
                  style={inputStyle}
                  placeholder="e.g. not eating since yesterday, breathing fast"
                />
                <VoiceInput onText={(text) => setFreeText((current) => `${current} ${text}`.trim())} />
              </div>
            </Field>
          </div>
        </Card>

        <Card>
          <h2 className="text-sm font-semibold text-ink">How bad, and how many?</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field
              label="Animals affected"
              error={fieldErrors["affected_count"]}
            >
              <input
                type="number" min="1" inputMode="numeric" value={affected}
                onChange={(e) => setAffected(e.target.value)}
                className={inputClass} style={inputStyle}
              />
            </Field>
            <Field
              label="Deaths"
              hint="Leave at zero if none"
              error={fieldErrors["deaths_count"]}
            >
              <input
                type="number" min="0" inputMode="numeric" value={deaths}
                onChange={(e) => setDeaths(e.target.value)}
                className={inputClass} style={inputStyle}
              />
            </Field>
            <Field
              label="Temperature (°C)"
              hint="Only if you measured it"
              error={fieldErrors["temperature_c"]}
            >
              <input
                type="number" step="0.1" min="25" max="46" inputMode="decimal"
                value={temperature} onChange={(e) => setTemperature(e.target.value)}
                className={inputClass} style={inputStyle}
                placeholder="e.g. 40.2"
              />
            </Field>
            <Field label="How long has it been going on?">
              <select
                value={duration} onChange={(e) => setDuration(e.target.value)}
                className={inputClass} style={inputStyle}
              >
                <option value="">Not sure</option>
                <option value="3">A few hours</option>
                <option value="12">Since this morning</option>
                <option value="24">About a day</option>
                <option value="72">About three days</option>
                <option value="168">A week or more</option>
              </select>
            </Field>
          </div>

          <p className="mt-4 text-[11px] text-ink-muted">
            {position
              ? "Location captured — this lets the report be compared with others nearby."
              : "No location yet. The report still works; it just will not take part in cluster detection."}
          </p>
        </Card>

        {formError ? <Notice tone="critical" title={formError} /> : null}

        <div className="flex gap-3 pb-4">
          <Button type="submit" disabled={busy} full>
            {busy ? "Saving…" : "Send report"}
          </Button>
        </div>
      </form>
    </div>
  );
}

/**
 * Speech input, where the browser offers it.
 *
 * Typing on a phone in a field is the single biggest barrier to a report being
 * filed at all. Where the API is missing the button simply does not render --
 * there is nothing useful to say about an unavailable capability.
 */
function VoiceInput({ onText }: { onText: (text: string) => void }) {
  const [listening, setListening] = useState(false);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    const w = window as unknown as Record<string, unknown>;
    setAvailable(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, []);

  if (!available) return null;

  function start() {
    const w = window as unknown as Record<string, unknown>;
    const Recognition = (w.SpeechRecognition || w.webkitSpeechRecognition) as
      | (new () => {
          lang: string;
          interimResults: boolean;
          onresult: (event: { results: { 0: { 0: { transcript: string } } } }) => void;
          onerror: () => void;
          onend: () => void;
          start: () => void;
        })
      | undefined;
    if (!Recognition) return;

    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-IN";
    recognition.interimResults = false;
    recognition.onresult = (event) => onText(event.results[0][0].transcript);
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognition.start();
    setListening(true);
  }

  return (
    <button
      type="button"
      onClick={start}
      className="min-h-[44px] shrink-0 rounded-lg border px-3 text-sm"
      style={{
        borderColor: listening ? "var(--status-critical)" : "var(--border)",
        color: listening ? "var(--status-critical)" : "var(--text-secondary)",
      }}
      aria-label={listening ? "Listening" : "Speak instead of typing"}
    >
      {listening ? "●" : "\u{1F3A4}"}
    </button>
  );
}

function OutcomeView({ outcome, onAnother }: { outcome: NonNullable<Outcome>; onAnother: () => void }) {
  if (outcome.kind === "queued") {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <Notice tone="warning" title="Saved on this device">
          There was no connection, so the report is stored here and will be sent
          automatically as soon as there is one. You do not need to do anything, and you do
          not need to file it again.
        </Notice>
        <Button onClick={onAnother} variant="secondary">Report another animal</Button>
      </div>
    );
  }

  const { report } = outcome;
  const assessment = report.assessment;

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Report received</h1>
            <p className="mt-1 text-sm text-ink-secondary">
              {assessment
                ? "Here is how it has been assessed, and why."
                : "It has been recorded."}
            </p>
          </div>
          {assessment ? <BandBadge band={assessment.band} /> : null}
        </div>

        {assessment ? (
          <>
            <p className="mt-5 text-sm leading-relaxed text-ink">
              {assessment.recommended_action}
            </p>

            {assessment.cautions.length > 0 ? (
              <div className="mt-5 space-y-3">
                {assessment.cautions.map((caution) => (
                  <Notice key={caution.caution_id} tone="critical" title={caution.title}>
                    <p className="mb-2">{caution.rationale}</p>
                    <ul className="space-y-1.5">
                      {caution.actions.map((action) => (
                        <li key={action} className="flex gap-2">
                          <span aria-hidden="true">&middot;</span>
                          <span>{action}</span>
                        </li>
                      ))}
                    </ul>
                    {caution.zoonotic ? (
                      <p className="mt-2 font-medium">
                        This pattern can affect people as well as animals.
                      </p>
                    ) : null}
                  </Notice>
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </Card>

      {assessment ? (
        <Card>
          <h2 className="text-sm font-semibold text-ink">
            Why it scored {Math.round(assessment.score)}
          </h2>
          <p className="mt-1 text-xs text-ink-muted">
            Every point comes from a named rule. Nothing here is a guess.
          </p>
          <ul className="mt-4 space-y-2.5">
            {explanationRows(assessment.contributions)
              .map((contribution) => (
                <li key={contribution.rule_id} className="flex gap-3">
                  <span
                    className="tabular w-12 shrink-0 text-right text-xs font-semibold"
                    style={{
                      color: isBandFloor(contribution)
                        ? "var(--status-critical)"
                        : contribution.points > 0
                          ? "var(--text-primary)"
                          : "var(--success-text)",
                    }}
                  >
                    {isBandFloor(contribution) ? (
                      "Floor"
                    ) : (
                      <>
                        {contribution.points > 0 ? "+" : ""}
                        {contribution.points}
                      </>
                    )}
                  </span>
                  <span className="text-xs leading-relaxed">
                    <span className="font-medium text-ink">{contribution.factor}</span>
                    <span className="text-ink-secondary"> &mdash; {contribution.evidence}</span>
                  </span>
                </li>
              ))}
          </ul>
          <p className="mt-4 border-t pt-3 text-[11px] text-ink-muted" style={{ borderColor: "var(--border)" }}>
            Assessed by {assessment.engine_version}. This is decision support, not a
            diagnosis.
          </p>
        </Card>
      ) : null}

      {report.unmatched_terms.length > 0 ? (
        <Card>
          <h2 className="text-sm font-semibold text-ink">Kept for a person to read</h2>
          <p className="mt-1 text-xs text-ink-secondary">
            These words were not recognised, so they were not scored — but they were not
            thrown away either. A reviewer will see them.
          </p>
          <ul className="mt-3 space-y-1">
            {report.unmatched_terms.map((term) => (
              <li key={term} className="text-xs italic text-ink-muted">&ldquo;{term}&rdquo;</li>
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="flex flex-wrap gap-3 pb-4">
        <Button onClick={onAnother} variant="secondary">Report another animal</Button>
        <Link
          href="/dashboard"
          className="inline-flex min-h-[44px] items-center rounded-lg px-4 text-sm text-ink-secondary"
        >
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
