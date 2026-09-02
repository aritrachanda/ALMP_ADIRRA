# BIRD lineage traceability — findings (2026-08-26)

**Why this matters:** ADIRRA's mapping engine will eventually need to answer "where did this
regulatory report figure ultimately come from, in plain business terms?" This is the first real
test of whether the BIRD Knowledge Base can answer that question on its own, or whether it needs
help. Recorded here in full because the result is genuinely important for how the mapping engine
gets built later — not just a one-off check.

**The plain-English result:** BIRD's data dictionary lets you trace a regulatory report figure
back two full steps toward its business meaning — reliably, for every case tested. The third step
(back to the true "business concept" layer) isn't written down anywhere as an official rule, but
you can still find it with very high confidence using a simple trick, confirmed on every case
tested. This document explains all of that with real examples, and is a first, deliberately narrow
test — not a general-purpose lineage tool yet.

---

## 1. The question we're asking

BIRD organises its data in layers, from "closest to the regulator" down to "closest to plain
business language":

| Layer | Plain meaning |
|---|---|
| **ROL** | The actual regulatory report template a bank submits (e.g. an AnaCredit monthly file) |
| **EIL** | An intermediate, enriched version used to build the report |
| **ELDM** | A further-enriched version of the core business model, closer to plain business concepts, with extra regulatory detail added |
| **IL** | A more structural reshaping of the core business model |
| **LDM** | The core business model itself — plain-language business concepts like "Account", "Instrument", "Counterparty" |

A number in a regulatory report (ROL) doesn't mean anything on its own — it only makes sense once
you know which business concept it came from. So: **if you pick one number on one report template,
can you walk backwards through these layers and land on a real business concept?**

## 2. What we tested

We picked all **10 AnaCredit report templates** (the actual monthly submission templates: Accounting,
Counterparty, Counterparty default, Counterparty-instrument, Counterparty risk, Financial,
Instrument, Instrument-protection, Joint liabilities, Protection received) and, for each one, picked
one real reported figure and tried to walk it backwards.

## 3. What we found — a very consistent wall, two steps back

**Every single one of the 9 traceable figures stopped in exactly the same place:**

```
Report figure (ROL)  →  EIL  →  ELDM  →  (nothing recorded further back)
```

This wasn't a case of "some worked, some didn't" — it was **9 out of 9**, no exceptions. That tells
us it's a real structural fact about how BIRD published this data, not a data-quality accident.

We double-checked *why* it stops there: none of the ELDM starting points we landed on are ever
listed as the *destination* of a documented transformation rule anywhere in the whole dictionary —
they only ever appear as a starting point. In other words, **BIRD's own published rules simply
don't document how ELDM connects back to the core business model (LDM)** for this reporting path.

## 4. The good news — a reliable shortcut exists

Even though there's no *documented rule* connecting ELDM back to LDM, we found that:

- Every ELDM starting point we reached has a **plain-business-model twin with the exact same
  name**, findable just by changing its technical code slightly (swapping the "ELDM" part for
  "LDM"). Confirmed on all 8 distinct cases.
- The underlying concept itself (the actual "thing" being measured, like "RIAD code" or
  "Accounting classification") is stored **once**, shared across every layer, with no separate
  version per layer. So the same concept legitimately appears on both the ELDM cube and its LDM
  twin — confirmed directly by looking at the LDM twin's own attribute list, not just inferred.

**In every one of the 9 cases tested, this shortcut successfully found a real, named business
concept.** So the practical answer is: the "official" trail goes cold after two steps, but a
simple, consistent shortcut reliably picks up from there.

## 5. A fully worked real example, so this isn't just a summary

Attribute: **RIAD code** (a party identifier), as it appears on the "Protection received" AnaCredit
template, in the field `PRTCTN_PRVDR_CD`.

**Step back 1 (report → enriched build version):**
The dictionary's own link table says: the enriched-build cube `BIRD_PRTY_CD_EIL_1`'s field
`RIAD_CD` becomes the report's `PRTCTN_PRVDR_CD` field, via a specific documented rule.

**Step back 2 (enriched build version → further-enriched business model):**
The dictionary's own link table says: the further-enriched cube `BIRD_RIAD_PRTY_CD_ELDM_1`'s field
`RIAD_CD` feeds into that same `BIRD_PRTY_CD_EIL_1` cube's `RIAD_CD` field, via another specific
documented rule.

**Step back 3 (where the official trail stops):**
We looked for any documented rule that lands ON `BIRD_RIAD_PRTY_CD_ELDM_1` — there are **zero**.
It only ever appears as a *source*, never a *destination*, anywhere in the dictionary.

**The shortcut, applied here:**
`BIRD_RIAD_PRTY_CD_ELDM_1` is named "Register of Institutions and Affiliates Database (RIAD) party
code". Swapping "ELDM" for "LDM" in its code gives `BIRD_RIAD_PRTY_CD_LDM_1` — which exists, is
named **identically**, and independently has its own `RIAD_CD` field defined on it. The underlying
concept "RIAD_CD" itself is one single shared definition: *"The RIAD code is a string that uniquely
identifies the Party according to the identifier assigned by the Register of Institutions and
Affiliates Database (RIAD)."*

So: report field `PRTCTN_PRVDR_CD` → traced (officially, two real documented steps) → the concept
"RIAD code" → matched (by the shortcut) → business concept "RIAD party code" in the core model.

## 6. Important limits — what this test does NOT prove

- **Only AnaCredit's 10 templates were tested.** BIRD has other reporting frameworks (FINREP, Asset
  Encumbrance, Securities Holdings) not covered here — they may behave differently and should be
  re-tested separately, not assumed to follow the same pattern.
- **The shortcut is a strong pattern match, not an official rule.** It has been right every time we
  tried it, but it isn't stamped by the regulator the way the documented two steps are. If this
  ever feeds an automated system, it should be labelled as "very likely, pattern-matched" rather
  than shown with the same certainty as the two officially documented steps.
- There is a second, separate documented path in the same dictionary (core business model → a more
  structural reshaping) that these 10 templates never touch. It's possible that path has fuller
  official coverage all the way through — this has not been checked yet.

## 7. Why this matters for the mapping engine (for later)

When the mapping engine eventually needs to explain "what business concept does this regulatory
number come from," it should:

1. Try the officially documented chain first (currently reliable for exactly two steps back from a
   report figure).
2. When that runs out, fall back to the concept-match / naming-pattern shortcut described above.
3. **Always show which of the two produced the answer** — a documented rule and a pattern-matched
   guess are not the same kind of confidence, and stewards reviewing a mapping should be able to
   tell them apart at a glance.

This is not scheduled or designed as a build task yet — recorded here so it's not lost, to be
picked up when the mapping engine's design gets to this point.

---

*Investigation method: read-only queries against the live `bird` Postgres schema (see
`db/migrations/versions/0019_bird_knowledge_base.py`). No files were changed by this investigation.
Full technical detail and raw query evidence: `/memories/repo/mapping-redesign-decisions.md`,
Decision Point 24.*
