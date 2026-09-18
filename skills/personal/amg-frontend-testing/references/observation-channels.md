# Observation channels: look at one thing every way it can be looked at

A single thing going wrong produces evidence in several places at once, and
**every channel is blind to some failure class it cannot express.** A
screenshot cannot show that the click handler never attached. The console
cannot show that a panel is 40 px off-screen. The DOM diff cannot show which
component decided to write it.

So the rule is not "take a screenshot and look". It is:

> **Point every channel you have at the same interaction, and when two of them
> disagree, the disagreement is the finding.**

---

## The channels, and what each one alone will miss

Each channel below names what it uniquely catches, then what it is blind to.

- **Single screenshot** — catches layout, colour, text, truncation, overlap.
  Blind to anything in motion; anything off-screen; what is *under* the
  pointer; whether it works.
- **Screenshot burst / screencast** — catches flicker, stuck intermediate
  states, animation that ends wrong. Blind to cause: it shows you *that*,
  never *why*.
- **`elementFromPoint` hit test** — catches the row you highlighted not being
  the node under the cursor. Blind to anything not at that coordinate.
- **Geometry probe** (`getBoundingClientRect`, ancestor `overflow`) — catches
  clipped by an ancestor vs hanging off the viewport: same symptom, different
  fixes. Blind to whether it is visible to a *user* (opacity, stacking).
- **Accessibility snapshot** (`ariaSnapshot`) — catches looks right, reads
  wrong: a `<div onClick>` no keyboard reaches. Blind to pixels; a
  perfectly-labelled invisible button passes.
- **Console + `pageerror`** — catches thrown errors, framework warnings. Blind
  to silent failures, and 4xx responses — those never reach it.
- **`response` ≥ 400 + `requestfailed`** — catches a 404 that the console
  never mentions. Blind to requests that succeeded and returned the wrong
  thing.
- **DOM mutation record** — catches what actually changed; transient flickers;
  writes that changed nothing. Blind to which component did it; whether a node
  was patched or replaced.
- **Framework commit stream** (`flags & 1`) — catches which component decided;
  wasted re-renders. Blind to anything outside the framework's own tree.
- **Network timeline** — catches duplicate requests, wrong order, a poll
  firing per keystroke. Blind to client-side state.
- **Performance observers** (LoAF, INP, `layout-shift`) — catches a janky
  interaction nobody can screenshot. Blind to correctness.
- **Coverage** — catches the branch that never executed in the whole sweep.
  Blind to whether the branches that ran were right.

## Measured cases where one channel lied and another caught it

Every case here happened in this project. They are the argument for the rule.
Each names the lie, then the channel that exposed it.

- A screenshot showed a hover panel open over a row — `elementFromPoint`
  proved the pointer was over the **panel**, not the row it appeared to
  highlight.
- The console was clean through a whole run — a `response` listener caught a
  **401** that produced no console message.
- A path-keyed DOM diff reported an attribute patch,
  `class: lucide-eye → lucide-eye-off` — symbol-tagged node identity proved it
  was a **React remount**: two different components in one slot. Different
  diagnosis, different fix.
- A MutationObserver reported the same attribute going `null → e` four times —
  reconstructing from `oldValue` gave the real chain
  `null → b → c → d → e`. Reading the live value in the callback is wrong for
  every record but the last.
- `actualDuration > 0` said three components re-rendered — `flags & 1` proved
  **five**, and gave the same answer on all four runs, while `actualDuration`
  varied run to run and was right once in four.
- A comment in the source said a panel scrolled and was selectable — it was
  **neither**. Prose is not a channel.
- A scrollbar-drag test failed, implying an app bug — measuring the gutter
  (**0 px**, document included) proved the whole environment is on overlay
  scrollbars: a harness property, not a defect.

Note the shape of the last one: a channel does not only produce false
negatives. It produces **false positives that look like app bugs**, and the
only defence is a second channel.

## The bundle

Attach all of it once, up front, rather than reaching for one at a time.
Cheap channels have no reason to be conditional.

```ts
// before goto — see SKILL.md step 2
const notes = []
page.on("console", (m) => m.type() === "error" && notes.push(`console: ${m.text()}`))
page.on("pageerror", (e) => notes.push(`pageerror: ${e.message}`))
page.on("requestfailed", (r) => notes.push(`requestfailed: ${r.url()}`))
page.on("response", (r) => r.status() >= 400 && notes.push(`http ${r.status()}: ${r.url()}`))
```

Then, around the interaction under suspicion:

```
before:  aria snapshot · geometry of the target · commit count baseline
during:  screenshot burst OR screencast · mutation record · network log
after:   aria snapshot · geometry · hit test at the pointer · notes ledger
diff every pair.
```

The diffs are the product. A run that ends with four artifacts nobody compared
has told you roughly nothing.

## Escalation order

Do not start with the expensive channel. Start with the one that decides
whether you need the expensive one.

1. **Screenshot** — is it visibly wrong? (seconds)
2. **Ledger** — did anything error, 4xx, or warn? (free, already attached)
3. **Geometry + hit test** — is it where and what you think? (milliseconds)
4. **Aria snapshot** — does it *read* the way it looks? (milliseconds)
5. **Burst / screencast** — is the problem in the transition rather than a
   state? (seconds)
6. **Mutation record** — what actually changed, and did anything flicker?
7. **Commit stream** — which component decided, and did anything render for
   nothing?
8. **Coverage / perf observers** — only when the question is "what did we never
   exercise" or "why is this slow".

Most findings resolve by step 4. The point of listing 5–8 is that **"I looked
and it seemed fine" is a statement about step 1 only**, and should be reported
that way.

## The corroboration rule

Before filing a finding, name **two** channels that agree on it. Before
dismissing something as fine, name the channel that *could have* caught it if
it were broken — and if you cannot, you have not checked, you have glanced.

Both halves matter. The first stops plausible-but-wrong reports. The second
stops the much more common failure: a sweep that passes because nothing it ran
was capable of failing.
