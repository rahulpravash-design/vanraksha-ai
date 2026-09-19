import Link from "next/link";

const STAGES = [
  {
    step: "01",
    title: "A farmer reports what they can see",
    body: "In their own words, by voice or by tapping symptoms, with or without a signal. Free text is normalised against a clinical vocabulary, so “loose motion” and “diarrhoea” become the same fact.",
  },
  {
    step: "02",
    title: "The report is triaged, with its reasons",
    body: "A score between 0 and 100 and a response deadline, built from named rules. Every point traces to one of them, so a veterinarian who disagrees knows exactly which rule to argue with.",
  },
  {
    step: "03",
    title: "Nearby reports are checked against each other",
    body: "Reports that are close in distance, close in time, and similar in presentation form a cluster. That is the signal a single report can never carry: something is happening here.",
  },
  {
    step: "04",
    title: "The right people are told, and the work is tracked",
    body: "A queue ordered by urgency and time-to-deadline, routed by role and geography, followed through to a recorded outcome — which is also what makes the system measurable.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <span className="flex items-center gap-2.5">
          <svg width="28" height="28" viewBox="0 0 64 64" aria-hidden="true">
            <path
              d="M32 12 L50 20 V33 C50 43 42 50 32 53 C22 50 14 43 14 33 V20 Z"
              fill="none" stroke="var(--series-1)" strokeWidth="3.5" strokeLinejoin="round"
            />
            <circle cx="32" cy="31" r="4.5" fill="var(--series-1)" />
          </svg>
          <span className="text-sm font-semibold tracking-tight">VANRAKSHA AI</span>
        </span>
        <Link
          href="/login"
          className="rounded-lg px-4 py-2 text-sm font-medium text-white"
          style={{ background: "var(--series-1)" }}
        >
          Sign in
        </Link>
      </header>

      <main className="mx-auto max-w-5xl px-6">
        <section className="py-16 sm:py-24">
          <p className="text-xs font-medium uppercase tracking-widest text-ink-muted">
            Livestock health surveillance
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            From one farmer&rsquo;s observation to a coordinated veterinary response.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-relaxed text-ink-secondary">
            Most livestock disease intelligence begins after the information has already
            been collected. The harder problem sits earlier: a farmer notices something,
            and days pass before anyone who could act knows about it. VANRAKSHA AI is the
            layer that closes that gap — capture, triage, cluster detection, and response,
            built for intermittent connectivity and incomplete records.
          </p>

          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="rounded-lg px-5 py-3 text-sm font-medium text-white"
              style={{ background: "var(--series-1)" }}
            >
              Open the platform
            </Link>
            <Link
              href="/report"
              className="rounded-lg border px-5 py-3 text-sm font-medium"
              style={{ borderColor: "var(--border)" }}
            >
              File a report
            </Link>
          </div>
        </section>

        <section className="border-t py-14" style={{ borderColor: "var(--border)" }}>
          <h2 className="text-lg font-semibold tracking-tight">How a report becomes a response</h2>
          <ol className="mt-8 grid gap-8 sm:grid-cols-2">
            {STAGES.map((stage) => (
              <li key={stage.step}>
                <p
                  className="tabular text-xs font-semibold"
                  style={{ color: "var(--series-1)" }}
                >
                  {stage.step}
                </p>
                <h3 className="mt-2 text-sm font-semibold text-ink">{stage.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-secondary">{stage.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t py-14" style={{ borderColor: "var(--border)" }}>
          <h2 className="text-lg font-semibold tracking-tight">What this system does not do</h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-3">
            <Boundary
              title="It does not diagnose"
              body="A field report cannot establish which pathogen is responsible. The platform describes syndromic patterns and says plainly that confirmation needs a veterinarian and, for most of what matters here, a laboratory."
            />
            <Boundary
              title="It does not prescribe"
              body="No medicine, no dose, no route — not from a rule and not from a language model. Dosing depends on weight, pregnancy, lactation and withdrawal periods that a veterinarian has to weigh up."
            />
            <Boundary
              title="It does not hide its reasoning"
              body="Every score is a sum of named rules with written evidence. Clusters state why they were grouped. An alert nobody can interrogate is an alert nobody should act on."
            />
          </div>
        </section>

        <footer className="border-t py-10" style={{ borderColor: "var(--border)" }}>
          <p className="text-xs leading-relaxed text-ink-muted">
            Built as an open project. The demonstration dataset is synthetic and carries no
            claim about real-world disease prevalence.
          </p>
        </footer>
      </main>
    </div>
  );
}

function Boundary({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-ink-secondary">{body}</p>
    </div>
  );
}
