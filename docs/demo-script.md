# Demo card

Print this. 5 minutes, 3 logins, forward only — never go back a screen.

**Reset, morning of the demo** (the cluster reveal only works once per database):

```bash
rm -f vanraksha.db* && ./scripts/dev.sh
```

Password for every account: `VanrakshaDemo2026!` — the login page has
one-click buttons, you never type it.

---

## 0 · Landing page — 20 sec

<http://localhost:3000>

> "India already forecasts livestock disease. NADRES-V2 does that.
> We didn't rebuild it."

> "Our gap is the hour *after* a farmer notices something — before
> anyone who can act knows."

→ **Sign in**

---

## 1 · FARMER — 1 min 40

**Farmer** button → **Sign in** → **Report** tab

| Do | What |
|---|---|
| Farm | Farmer 1's holding |
| Tap chips | Mouth blisters · Foot blisters · Fever · Milk yield drop |
| Type | `drooling a lot since yesterday, not eating` |
| Affected | `3` |
| Temp | `40.4` |
| How long | About a day |

→ **Send report**

**Screen shows:** `URGENT` · score **56** · red caution box · 7 rules

> "Look at the red box. That didn't come from the score."

> "Blisters in the mouth and feet is notifiable. Stop moving animals —
> that's procedural. It shouldn't wait for arithmetic."

> "The score said priority. The rule forced urgent. There are eight
> rules like this."

Scroll to **Why it scored 56** — seven rows:

> "Every point has a named rule and its evidence. A vet who disagrees
> knows exactly which rule to argue with."

Point at the bottom row, in red, marked **Floor**:

> "There's the override, sitting in the same list. Zero points, and it
> still set the band. The arithmetic is auditable — and so is the thing
> that overrules the arithmetic."

Point at the `+6.0` row — *6 distinct signs*:

> "Six signs. She tapped four. Two came out of her sentence."

→ **Dashboard** tab. Heading reads *Farmer 1's farms*, 6 reports:

> "Her scope is her own herd. No Queue tab, no Clusters tab. The API
> returns 403 to her token — not the UI hiding buttons."

→ **Sign out**

---

## 2 · DISTRICT OFFICER — 2 min

**District officer** button → **Sign in** → **Clusters** tab

Screen says **"No active clusters."** Pause.

> "Nothing flagged. Every report was triaged individually — and
> individually, none of them is alarming."

→ **Run detection now**

**One cluster appears:** Respiratory · Sulibele · severity **61** ·
9 reports · 21 animals · **Accelerating** · 1.3 km

> "Nine reports, eleven days, farms within 1.3 km, same presentation.
> None of those nine farmers knew about the other eight."

> "Distance, time, and symptoms all have to agree. Nearby alone isn't
> a cluster."

Point at **Reviewer verdict** box:

> "Confirm or dismiss is what alert precision gets measured against.
> We made the cost of a false alarm visible."

→ **Dashboard** tab. Red banner now at top:

> "Same detection, pushed to whoever's role and area make it theirs."

Scroll to bottom — **Response performance · Met target 21.4%**:

> "That number is bad, and it's meant to be. It's the baseline. We
> didn't tune the demo data to look good."

> "Moving that number is the whole point of the system."

→ **Map** tab (skip if slow):

> "Eight villages reporting. One is doing something the others aren't."

→ **Sign out**

---

## 3 · VETERINARIAN — 1 min 20

**Veterinarian** button → **Sign in** → **Queue** tab

**Seven cases:**

| # | |
|---|---|
| 1 | EMERGENCY · overdue |
| 2 | **URGENT** ← the report we just filed |
| 3–6 | PRIORITY · all four badged *part of a cluster* |
| 7 | PRIORITY · no badge |

> "That's the report from three minutes ago. Second in the queue,
> behind one emergency, six-hour clock running."

> "Those four were ordinary priority cases. The sweep tagged them.
> Not four sick animals — one event."

> "The last one isn't tagged. The detector discriminates, it doesn't
> decorate."

→ Click the **urgent** case open. **Signs** row shows all six codes.
Click **Why it scored 56** — the same seven rows, floor included:

> "Same reasons the farmer saw. Same seven rules, same override at the
> bottom. One record, one set of rules, two audiences."

Point at **Record outcome and close**:

> "And it closes. That's what makes it measurable."

**STOP HERE. Don't go back to a dashboard.**

> "Three minutes ago a farmer saw blisters in a cow's mouth. It's now
> second in a vet's queue, with the reasons attached, a six-hour clock,
> and a movement restriction already issued."

Take questions.

---

## If it breaks

| | |
|---|---|
| Web won't load | Switch to the `http://localhost:8000/docs` tab (keep it open). Do the flow in JSON. |
| Page spins forever | API died. `Ctrl+C`, `./scripts/dev.sh`. **Don't re-seed.** |
| Sweep finds nothing | It already ran. Say so, show the cluster that's there. |
| Submit fails | Reload `/report`, file it again. |
| Total failure | Open `docs/pitch-deck.html` from disk — works with no network. Slides 5–7 have the same example. Say the stack is down. |

**Never** `rm vanraksha.db` in front of judges.

---

## Expected numbers

Fresh seed, district, 30 days: **71 reports** (50 previous, rising) ·
83 animals · 7 open cases, all overdue · 1 death · 56 overdue vaccinations ·
**0 clusters**

Band chart, five rows top to bottom: routine 28 · monitor 31 · priority 11 ·
**urgent 0** · emergency 1. The urgent row is empty until the farmer files —
by the time the district officer looks, it reads 1. That bar is the report
from three minutes ago.

After the farmer files: 72 reports, 8 open cases. That's correct.

Cluster after sweep: 9 reports · 21 animals · 0 deaths · severity 61 ·
1.3 km · growth 2.4

Seeded: 8 villages · 28 farms · 216 animals · 191 reports.

**If clusters ≠ 0 before you press the button, the sweep already ran. Re-seed.**

---

## Don't

- **Don't say "predict."** We triage and detect. We don't forecast.
- **Don't claim clinical accuracy.** 24/24 is against *our* expected
  bands, not a vet's. Say it before a judge finds it.
- **Don't demo Docker.** Written, never build-verified. `dev.sh` was.
- **Don't open** `infrastructure/`, `packages/`, `.github/` — empty on
  purpose, recorded in `docs/roadmap/`.

---

## Three answers

**"How is this different from NADRES-V2?"**
> It forecasts from data already collected. We're the layer before —
> the farmer's observation turned into a routed case. We generate the
> field signal it consumes.

**"Are the accuracy numbers real?"**
> The harness runs the exact module the API runs — zero dependencies,
> no reimplementation to drift. But it measures agreement with *our*
> expected bands on synthetic vignettes. That's honest evaluation of
> the logic, not clinical validation. Vet ratification is next.

**"What about no network?"**
> Stored on the device, sent when signal returns, and the header tells
> the farmer which happened. 36.5% of reports in this dataset were
> filed offline. SMS and USSD are a gateway procurement question, not
> a code question.
