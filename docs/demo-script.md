# Demo script

A run sheet for the live demonstration. Every number below was taken from a
freshly seeded database on a running stack, not estimated. If a number on your
screen differs by a few, see [When the numbers drift](#when-the-numbers-drift).

The demo is five minutes and has one job: show that a report becomes a
*routed, explained, deadlined piece of veterinary work* — not a chart.

---

## Before you start

### The night before

Run this on the **actual machine you will demo from**, not on a different one:

```bash
./scripts/setup.sh
./scripts/dev.sh
```

Then open <http://localhost:3000/login>, sign in as any account, and click
through every tab once. You are looking for one thing: does anything fail to
load. Fix it tonight, not in the room.

Stop with `Ctrl+C` when you are done.

### The morning of — reset to a clean state

This matters. **The cluster reveal only works once per database.** Once the
sweep has run, the cluster is stored, and `/clusters` will show it immediately
instead of revealing it live. Rehearsing burns the reveal.

So before the real demo:

```bash
rm -f vanraksha.db vanraksha.db-shm vanraksha.db-wal
./scripts/dev.sh          # re-seeds automatically
```

Seeding takes a few seconds. Seed on the morning of the demo, not the night
before — the dataset is positioned relative to "now", so the 30-day counts
shift slightly if it sits overnight.

### Ten minutes before

1. `./scripts/dev.sh` running, left running.
2. Browser open at <http://localhost:3000>, zoom at 110–125% so the back row
   can read it.
3. **Second tab already open** at <http://localhost:8000/docs> — your fallback
   (see [If something breaks](#if-something-breaks)).
4. Log out of everything. Start signed out.
5. Close Slack, mail, notifications.

The shared password for every demo account is `VanrakshaDemo2026!`. You will
not have to type it: the login page has one-click buttons for the three
accounts you need.

---

## The run sheet

Three logins, in this order, forward only. No going back.

| # | Who | Screen | Time |
|---|-----|--------|------|
| 0 | — | Landing page | 0:20 |
| 1 | `farmer1@example.org` | `/report` | 1:40 |
| 2 | `district@example.org` | `/clusters` → `/dashboard` → `/map` | 2:00 |
| 3 | `vet.hoskote@example.org` | `/queue` | 1:20 |

Total 5:20. If you are cut to four minutes, drop the map (step 2) and the
access-control line (step 1) — in that order.

---

### 0 · Landing page — 20 seconds

**Screen:** <http://localhost:3000>

Do not read the page. Let the headline sit there for two seconds — *"From one
farmer's observation to a coordinated veterinary response"* — and say:

> India already forecasts livestock disease risk. ICAR-NIVEDI's NADRES-V2 does
> that, at district resolution, monthly. We did not rebuild it. The gap we went
> after is the one after a farmer actually notices something — where days pass
> before anyone who could act knows.

Click **Sign in**.

---

### 1 · The farmer — 1 minute 40

Click the **Farmer** button in the Demonstration accounts box. It fills both
fields. Press **Sign in**. You land on the dashboard — ignore it, click
**Report** in the top nav.

#### File the report live

Do this on screen, do not pre-fill it:

| Field | What to do |
|-------|-----------|
| Which animal? | **Cattle** is already selected. Leave it. |
| Farm | Select **Farmer 1's holding** |
| Animal | Skip it — leave "Not specified" |
| Symptom chips | Tap **Mouth blisters / ulcers**, **Foot blisters / lesions between claws**, **Fever**, **Sudden milk yield drop** |
| Free text | Type: `drooling a lot since yesterday, not eating` |
| Animals affected | `3` |
| Deaths | leave `0` |
| Temperature | `40.4` |
| How long | **About a day** |

While typing the free text, say:

> She is typing in ordinary words. Watch what the system does with them.

Press **Send report**.

#### What appears — and what to point at

The verdict screen loads. Three things are on it. Point at each.

**One — the band and the action.** Top right: **URGENT**. Under it:

> *"Assign a veterinarian now and isolate the affected animals. Restrict
> movement on and off the premises until the visit has taken place."*

**Two — the red caution box.** Read the title out loud:

> **"Vesicular signs — apply movement restriction pending veterinary
> assessment"**

Then say the line that matters most in the whole demo:

> This did not come from the score. It came from a pattern match. Blisters in
> the mouth and around the feet in a cloven-hoofed animal is a notifiable
> presentation, and the correct first action — stop moving animals — is
> procedural, not therapeutic. It should not wait on arithmetic. So the score
> can say *priority* and this rule still forces *urgent*. There are eight of
> these floors.

**Three — scroll down to "Why it scored 56".** Six rules, each with points and
evidence in plain English:

| Points | Rule |
|--------|------|
| +20.8 | Mouth blisters carries a severity weight of 0.80 in the clinical taxonomy |
| +10.5 | 3 of 4 animals affected (75% of the herd) |
| +9.9 | Rectal temperature 40.4 °C is 1.1 above the cattle normal upper limit |
| +6.73 | 3 animals reported with the same presentation |
| +6.0 | 6 distinct signs across 7 syndromic groups |
| +2.0 | No vaccination history available |
| FLOOR | Raised from priority to urgent |

Say:

> Every point traces to a named rule with its evidence. A veterinarian who
> disagrees knows exactly which rule to argue with. That is the difference
> between decision support and a number a machine handed you.

**Then the detail most people miss.** Stay on this table and point at the
`+6.0` row — *"6 distinct signs reported across 7 syndromic group(s)"*. She
tapped **four** chips. Say:

> Six signs, and she tapped four. The other two came out of "drooling a lot
> since yesterday, not eating" — salivation and reduced appetite — normalised
> against the same clinical vocabulary the scorer uses, and then scored. Free
> text is not a comment box here.

*(The full six-code list is not shown on this screen. It is visible in step 3,
on the expanded case in the vet's queue, under **Signs** — if a judge asks to
see it, that is where you go.)*

#### One line on access control

Click **Dashboard**. Point at the heading: **"Farmer 1's farms"** — 6 reports,
not the district's 72. Say:

> Her scope is her own herd. She has no Queue tab and no Clusters tab. That is
> not the UI hiding buttons — the API returns 403 to her token. Role is
> enforced server-side.

Click **Sign out**.

---

### 2 · The district officer — 2 minutes

Click the **District officer** button, **Sign in**.

#### The reveal

Click **Clusters**. The page says **"No active clusters."**

Let that sit for a beat. Say:

> Nothing is flagged. Every report in this district has been individually
> triaged — and individually, none of them is alarming.

Click **Run detection now**.

One cluster appears. Point at it:

- **Respiratory cluster · Sulibele** — severity **61**
- **9 reports · 21 animals · 0 deaths · Accelerating**
- *"9 reports within 1.3 km of each other in Sulibele share a respiratory
  presentation. most frequent signs are fever, cough, nasal discharge.
  reporting rate is still accelerating."*
- Spread across 1.3 km · detected by `cluster-detector/1.1.0`

Say:

> Nine reports over eleven days from farms within 1.3 km of each other, sharing
> a presentation. No single one of those farmers knew about the other eight.
> The detector needs all three to agree — distance, time, and syndromic
> similarity — before it will call it. Reports that are merely nearby are not a
> cluster.

Then point at the **Reviewer verdict** box underneath:

> And this is not decoration. Confirm or dismiss is what alert precision gets
> measured against. If the system cries wolf, dismissing it here is how that
> shows up in the numbers. We wanted the cost of a false alarm to be visible.

#### The alert, the map, and the honest number — 40 seconds

Click **Dashboard**. A red banner is now at the top that was not there before:

> **Respiratory cluster: 9 reports** — Sulibele

Say:

> Same detection, pushed to everyone whose role and geography make it theirs —
> the vets, the block officer, the district.

**Scroll to the bottom, to "Response performance."** Point at **Met response
target: 21.4%**. This is the beat that buys you credibility for everything
else:

> That number is bad, and it is supposed to be. It is the synthetic district's
> baseline — cases were closed late far more often than on time. We left it on
> the dashboard rather than tuning the demo data to look good, because an
> intervention you cannot measure against a bad baseline is not an
> intervention. Moving that number is the entire point of the system.

Click **Map**. The ring sits over Sulibele. One sentence:

> Eight villages reporting; one of them is doing something the others are not.

*(If the map is slow or looks wrong, skip it — it is the most skippable
thirty seconds in the demo.)*

Click **Sign out**.

---

### 3 · The veterinarian — 1 minute 20

Click the **Veterinarian** button, **Sign in**. Click **Queue**.

This is the payoff screen. Seven cases, ordered.

Point at the top of the list:

| Position | What it is |
|----------|-----------|
| 1st | **EMERGENCY** · Unassigned · Overdue |
| 2nd | **URGENT** · Unassigned · the report the farmer just filed |
| 3rd–6th | **PRIORITY** · all four badged **"part of a cluster"** |
| 7th | **PRIORITY** · no badge — a genuinely isolated case |

Say, pointing at position 2:

> That is the report we filed three minutes ago. It went straight to a
> veterinarian's queue, second in line, behind one emergency and ahead of
> everything else, with a six-hour response target attached.

Then point at the **"part of a cluster"** badges — and at the bottom case,
which has none:

> Those four were already in this queue as ordinary priority cases. The sweep
> we just ran tagged them. The vet now knows they are not four unrelated sick
> animals — they are one event. And the one at the bottom is not tagged,
> which is the part that matters: the detector is discriminating, not
> decorating.

Click the **urgent** case open. The **Signs** row lists all six codes — this is
where the free-text extraction from step 1 is visible. Then click the small
**"Why it scored 56"** toggle (it is collapsed by default). Say:

> Same reasons the farmer saw, same numbers. Nothing is translated or softened
> between the two of them — one record, one set of rules, two audiences.

Point at **Start work** / **Record outcome and close**:

> And it closes. Which is the part that makes any of this measurable at all.

#### The closing line

Stay on this screen. Do not go back to a dashboard. Say:

> Three minutes ago a farmer in Sulibele saw blisters in a cow's mouth. It is
> now second in a veterinarian's queue, with the reasons attached, a six-hour
> clock running, and a movement restriction already issued. That hour is the
> one that decides the outcome, and it is the hour nothing else was using.

Stop talking. Take questions.

> **If you scroll this screen's dashboard instead:** the vet's Response
> performance panel reads **0%**, not 21.4% — it is scoped to the Hoskote
> block, where no case met its target. Not a bug, but a worse number to end
> on. Show 21.4% at district level in step 2 and leave it there.

---

## If something breaks

Have this decided before you are standing up.

| What broke | What you do |
|-----------|-------------|
| Web app will not load | Switch to the `/docs` tab. Do the whole flow against the API. `POST /api/v1/reports` returns the full assessment as JSON — contributions, cautions, band. It is less pretty and every bit as convincing. |
| A page spins forever | The API died. `Ctrl+C` in the terminal, `./scripts/dev.sh` again. Do not re-seed — the database survives. |
| "Run detection now" returns nothing | The sweep already ran on this database. Say so, move on, show the cluster that is there. Do not re-seed mid-demo. |
| The report submit fails | Reload `/report` and file it again. The form keeps nothing, so it is a clean retry. |
| Nothing works at all | Deck slides 5, 6 and 7 carry this same worked example — triage, the caution, the cluster — with real engine output. Present those and say plainly that the live stack is down. |

**Do not** attempt a live `rm vanraksha.db` and re-seed in front of judges. It
takes long enough to feel like a failure.

---

## When the numbers drift

The dataset is deterministic — the same seed produces the same district every
time. But it is positioned relative to *now*, so a database seeded yesterday
shows slightly different 30-day counts than one seeded this morning.

Verified on a fresh seed (district officer, last 30 days):

| Metric | On a fresh seed | During the demo |
|--------|-----------------|-----------------|
| Reports filed | 71 (previous period 50 — trend **rising**) | 72, after the farmer files |
| Animals covered | 83 | 83 |
| Open cases | 7, all 7 past their response target | 8 open, 7 overdue |
| Deaths recorded | 1 | 1 |
| Overdue vaccinations | 56 | 56 |
| Bands | 28 routine · 31 monitor · 11 priority · 1 emergency | + 1 urgent |
| Active clusters | 0 | **0 before the sweep, 1 after** |

The one-higher numbers in the right column are the live report you filed in
step 1. If the district dashboard reads 72 and not 71, that is correct.

Seeded totals: 8 villages · 28 farms · 216 animals · 191 reports.

Cluster, after the sweep: respiratory · Sulibele · 9 reports · 21 animals ·
0 deaths · severity 61 · radius 1.3 km · growth ratio 2.4 (accelerating).

If your counts are within a few of these, nothing is wrong. If **Active
clusters** is not 0 before you press the button, the sweep has already run —
re-seed.

---

## What not to do

- **Do not claim the accuracy numbers are clinical.** The 24/24 triage
  agreement in `ml/` is against *our own* expected bands, not a veterinarian's.
  Slide 10 of the deck says this and so should you, first, before a judge finds
  it. Getting those vignettes ratified by a practising vet is the top item on
  the roadmap.
- **Do not demo Docker.** The images are written but were never build-verified.
  `./scripts/dev.sh` was. If asked, say exactly that.
- **Do not open the empty `infrastructure/`, `packages/` or `.github/`
  directories.** They are deliberate scoping decisions recorded in
  `docs/roadmap/` — which reads as discipline when you volunteer it, and as
  padding when a judge finds it.
- **Do not say the word "predict."** This system does not forecast disease. It
  triages what is reported and detects what is already happening. That
  distinction is the whole positioning.

---

## The three questions you will get

**"How is this different from NADRES-V2?"**
> NADRES-V2 forecasts risk from data that has already been collected. It is
> good at that and we are not competing with it. Our layer sits before it: the
> farmer's observation, in the hour it happens, turned into a routed case. We
> generate the field signal NADRES consumes.

**"Are these accuracy numbers real?"**
> The harness is real and it evaluates the exact module the API runs in
> production — the engine has zero third-party runtime dependencies, so there
> is no reimplementation to drift. What the numbers measure is agreement with
> *our* expected bands on a synthetic vignette set. That is honest evaluation
> of the logic, not clinical validation. Veterinary ratification is our next
> step, and until it happens we will not call it accuracy.

**"What happens with no network?"**
> The report is stored on the device and sent when a signal returns — the
> header shows the farmer which of the two happened, because a farmer who
> cannot tell will either file it twice or assume it went. In this dataset
> 36.5% of reports were filed offline. SMS and USSD are architecturally assumed and
> deliberately not built; that is a gateway procurement question, not a code
> question.
