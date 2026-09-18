# Finding nuances

Every checklist in this skill is a list of quirks somebody already found. The
interesting ones are the quirks nobody has found yet, and no list will contain
them. This page is the method that generates them.

The disposition, in one line: **treat every "that's probably fine" as an
unmeasured claim.**

---

## Quirks live in seams, not in states

A component in a state is usually correct — somebody looked at it. Defects
collect at the joins. When you are hunting, go to the seams:

| Seam | What lives there |
|---|---|
| Two states | Transitions nobody rendered |
| Two elements | The handoff |
| Two code paths for one outcome | The path with no tests |
| Two coordinate systems | Portals, containers, scroll |
| Two timelines | Animation vs data vs poll vs debounce |
| Code vs framework | Delegation, hydration, batching, StrictMode |
| Visual vs semantic | Looks right, reads wrong |
| Boundaries | First, last, exactly-at |
| Two libraries meeting | Nobody owns it |
| Guard vs consumer | A correct guard nobody routes through |
| Two tuned constants | Neither is wrong; their arithmetic is |
| A default never chosen | Inherited behaviour |

An example found at each seam, in the same order:

- **Two states** — a panel that opens correctly and never closes because the
  close path restores focus to its own trigger.
- **Two elements** — a hover panel the pointer cannot reach, because leaving
  the trigger kills it.
- **Two code paths for one outcome** — upload validates in the picker and not
  in the drop zone; `fill()` works and typing does not.
- **Two coordinate systems** — a popover positioned against the viewport while
  its clipping ancestor is a scroll container.
- **Two timelines** — a poll landing under a stationary pointer, changing what
  is beneath the cursor with no `mousemove`.
- **Code vs framework** — the seam between what you wrote and what the
  framework does: patching `addEventListener` shows the delegation root, never
  your `onClick`.
- **Visual vs semantic** — a `<div onClick>` that no keyboard can reach; a
  focus ring that appears for a mouse click.
- **Boundaries** — behaviour at exactly the breakpoint width, not 10px either
  side.
- **Two libraries meeting** — an overlay library's portal versus the app's
  scroll container and z-index.
- **Guard vs consumer** — a consumer that skips the guard: a hook computes
  `isPending: !hasLoaded && error === null` explicitly so a failed poll cannot
  render as an infinite skeleton — and the page that needed it reads the
  underlying store directly, where no error concept exists.
- **Two tuned constants** — a slider's arrow step is 1 s and the seek helper
  snaps to the live edge within 2 s of it — so the smallest keyboard step is
  *always* inside the snap window and can never leave the live edge, while
  Shift+Arrow (10 s) and PageDown (30 s) escape.
- **A default never chosen** — the browser's black focus outline; the scrollbar
  nobody styled; a cursor nobody set.

That last row is the richest and the least looked at. Most quirks are not
mistakes — they are **defaults that nobody ever decided**.

## Questions that generate nuances

Point these at any component. Each one reliably produces candidates, and
most take under a minute to answer.

**On the element itself**

1. What did nobody *choose* here — cursor, focus ring, scrollbar, selection
   colour, tab order, overscroll behaviour?
2. What is on top of it? What is underneath? Prove it with `elementFromPoint`,
   not by looking.
3. What is the smallest version of it? The emptiest? The largest?
4. What happens at exactly the boundary — first item, last item, exactly the
   breakpoint, exactly the max length?

**On the interaction**

5. What happens **between** its states, not in them?
6. What are the *two* ways to do this — mouse and keyboard, picker and drop,
   click and URL, type and paste? Does each work, and do they agree?
7. Does the **path** matter, or only the endpoint? Walk it with `steps`.
8. What if I do it **twice, fast**? What if I do it while the last one is still
   in flight?
9. What if I **leave halfway** — mid-drag, mid-composition, mid-navigation,
   mid-animation?
10. What does it leave behind when it closes?

**On the environment**

11. What if it is slow? What if it fails? What if it returns nothing?
12. What does the screen reader get, as opposed to what the screen shows?
13. What survives a reload — and what *shouldn't*?
14. What does this look like at 320 px, at 200% text, on touch, in dark mode,
    with reduced motion?

**On the code**

15. What does the framework do here that I did not write?
16. Which branch of this has never executed? (coverage answers this)
17. What is the assumption in this test double that reality does not honour?

## From a feeling to a finding

"Something feels off" is a legitimate starting point and a useless report.
Escalate it — each step names what you produce:

1. **Feeling** — "the panel is weird when I move down the list".
2. **Observation** — walk the path, capture at each waypoint, note where
   behaviour changes.
3. **Measurement** — a number: two panels open, `scrollTop` unchanged, 2,040
   renders, 415 px of overflow.
4. **Mechanism** — the line of code or the framework behaviour that causes it.
5. **Minimal repro** — the two steps that still reproduce it.

**Never stop at observation** — that is where findings get dismissed as flake.
And never skip to mechanism; a guessed cause that happens to be wrong costs
more than no cause at all.

## The tells

Things that are almost always worth a closer look:

- **A default you can name.** If you can say "that's just the browser's
  default X", ask whether anyone chose it.
- **A number that is suspiciously round or suspiciously large.** 2,040 renders
  for 5 keystrokes. Four polls per click. 415 px of overflow.
- **A comment explaining why something is fine.** The longer the justification,
  the more often it is stale. Two in this session were: a comment saying a
  panel scrolled and was selectable when it was neither, and a config arguing
  against the mocking its own suite had adopted.
- **A thing that works only one way round.** Opens fine, closes oddly. Works by
  mouse, not by keyboard. Fine going forward, wrong on Back.
- **Two things that should agree and were never compared.** The rendered value
  and the submitted value. The visual order and the tab order. The mock and the
  schema.
- **Anything with a delay in it.** Debounce, grace window, animation, poll,
  retry. Every one has a "what if the next thing happens during it".
- **Anything portalled.** It has left its DOM parent, so every assumption about
  containment, clipping, stacking and event bubbling needs re-checking.
- **Anything you had to look at twice to understand.** If it took you two
  passes, it will take the next person two passes, and one of you will be
  wrong.

## Turning the environment against itself

Amplifiers make latent quirks manifest, and they are cheap:

- Throttle the CPU 4× — races become reproducible.
- Slow every request by 2 s — every in-flight state becomes observable.
- Force the smallest viewport and 200% text together.
- Pin the clock, then advance it in slices.
- Corrupt the client store before first paint.
- Run the same interaction 5× in a row and diff the recorder tallies — anything
  that is not identical is a state leak.

## Feed it back

**A nuance you find is a checklist entry you earned.** When a hunt turns up
something real:

1. Add it to `exploration-catalogue.md`, phrased as a checkbox someone else can
   run.
2. If it generalizes, add the *seam* to the table at the top of this page —
   the class matters more than the instance.
3. Write the regression guard, then **break the fix and watch it fail**.
4. If the technique that found it was novel, write that down too. The method is
   worth more than the bug.

The catalogue in this skill grew entirely this way. None of it was designed up
front; every entry is a quirk somebody hit, generalised.

## A finding contains two claims, and they fail independently

Every finding asserts **what you saw** and **why it happens**. Verify both. The
observation is what makes it real; the mechanism is what a fixer acts on, and a
correct observation with a wrong mechanism sends someone to the wrong line.

Three from one project, all with a correct symptom and a wrong cause:

- **Reported:** "a no-op +/− round trip unpins the preset, because
  `updateConfig` lacks a did-anything-change comparison". **True:** the PUT
  with `preset: ""` is real — but neither click is a no-op (3→4→3 is two
  genuine edits), so the proposed comparison would fire on both and change
  nothing. The unpin comes from a stored marker, by design.
- **Reported:** "the resize handles render 0px **tall**". **True:** genuinely
  broken, but they are 0px **wide** by design; the missing **height** was the
  defect. Filed on the wrong axis.
- **Reported:** "the runs list is not capped" *(a ruled-OUT claim)*.
  **True:** three layers checked and clean; the cap was `limit=200` in the
  service the handler delegates to.

Practical consequences:

- When the mechanism is uncertain, **report the observation and say the cause is
  unconfirmed.** That is far more useful than a confident wrong cause.
- A verifier should be asked to attack **both halves** — "reproduce it, then
  check whether the stated cause can actually produce it". On that project the
  single most valuable verdict was *"symptom confirmed, named root cause
  impossible"*.
- If your fix does not make the symptom disappear, suspect the mechanism, not
  the fix.

## Ruling something OUT is a claim, and needs the same rigour

Negative findings feel safe. They are not — a wrong "ruled out" closes an
investigation and is never revisited.

Measured on one project. The hypothesis was "the runs list is capped, so an old
run would 404 falsely". Three layers were checked and all three were genuinely
clean:

- the fetch helper sends no `limit`
- the OpenAPI contract declares **no parameters at all** on that endpoint
- the request handler has no slice, no `LIMIT`, no cap constant

Conclusion written: *"the 200 is the user's real run count, not a cap."* Wrong.
The cap was `limit=200`, one layer further down, in the **service the handler
delegates to**. Three independent clean checks read as conclusive and were
merely shallow — nobody had asked what the handler *calls*.

That cap no longer exists — it was removed on 2026-09-06, the day the owner's
account crossed 200 runs and run 201 went missing from the sidebar and from
search at once. Going to look for it in the code today finds nothing, which is
exactly the trap this section is about: absence at the layer you check is not
absence.

Two rules fall out:

- **Checking N layers proves nothing about layer N+1.** For "is there a cap /
  filter / truncation anywhere", follow the call chain to the data source. Stop
  at the first layer that *produces* the value, not the first that looks clean.
- **Prefer an empirical disproof to a code-reading one.** On that same project
  every hypothesis ruled out by *measurement* held up — 6,111 API values
  checked for whitespace-only bodies, a click counted against a blocked
  endpoint — and the only one ruled out by *reading code* was the one that was
  wrong.

## Reproducibility is not correctness

A deterministic result feels like a confirmed one. It is not — **a bug in your
own probe reproduces perfectly**, because DOM order, selector semantics and
measurement code are all deterministic. Two identical runs agreeing tells you
the *measurement* is stable, and says nothing about whether it is measuring the
right thing.

Measured on one project: a generated sweep flagged the same two cells across
two full runs. That agreement was treated as evidence for two rounds. The cause
was a selector in the oracle that swept a `listbox` into an array named
`dialogs` — a mistake that could not possibly have been intermittent.

The discipline that resolves it is the one from the seam list: **re-derive the
finding a second way that does not share the first method's failure mode.**
Dump what the selector actually matched. Read the source region a scan flagged.
Assert it in the live DOM instead of a static parse. On that project the tally
came out at **eight false positives from the probes, none from the app** — so
treat your own instrument as the leading suspect, not the last one.

## A negative needs a positive control

"I looked and it wasn't there" is only a finding if the instrument was known to
be capable of seeing it. Otherwise you have measured your own probe.

Measured on one project. A sweep of eight chart views reported the tooltip
absent on every one — `tooltipAt=0/3`, uniformly. It was written up as a
defect. Three things were wrong at once:

- the probe hovered `main svg` **first**, and the first SVG in `main` was a
  16px icon, not the chart (there were three)
- the hover targets were points in the empty plot area, where ECharts'
  default `trigger: "item"` shows nothing *by specification*
- one of the views under test configures no tooltip at all

Pointed at an actual rendered mark, the same detector fired on 6 of 6 hovers
and printed the tooltip text. Nothing was broken. The absence was entirely
manufactured.

The rule: **before reporting that something does not happen, make it happen
once.** Find the case where the feature demonstrably works, confirm your
detector reports it, and only then trust the detector's silence elsewhere. If
you cannot produce a single positive, you do not yet have an instrument — you
have a function that returns "no".

Two corollaries worth holding separately:

- **Uniformity across independent subjects is a tell, not a confirmation.**
  Eight views failing identically is far more consistent with one broken probe
  than with eight independently broken charts. Treat a suspiciously clean
  result the way you would treat a suspiciously round number.
- **The first matching element is not the element under test.** In any app with
  icons, avatars, or decorative graphics, `querySelector` on a tag name is a
  coin flip. Size-rank the candidates, or assert the match's dimensions and
  identity before you measure a single attribute of it.

A control catches the mirror-image failure too — **a detector that fires on
everything.** On the same project a later probe scored pages for an error state
with a regex over body text (`/error|failed|unable/`). It returned true on all
four *healthy* baselines, because the app legitimately contains a tab named
"Errors" and run statuses that read "failed". A signal that is true on the
control discriminates nothing, and it reads as a *reassuring* result — "yes,
there's an error state" — which is far less likely to be questioned than a
worrying one. Run your detector against a known-good case and a known-bad case;
if it cannot tell them apart, you have no signal, whichever way it answers.

Count the interceptions, too. A route handler that never matched reports the
same clean result as a feature that works. On that project `interceptHits=0`
was the only thing separating "this page handles failure fine" from "my glob
never matched the URL that page requests" — so assert on the hit count and let
a zero FAIL the test rather than pass it silently.

This also invalidates whatever *else* the misaimed run reported. That same
sweep's accessibility numbers were read off the icon; re-measured on the real
charts, one of them (`tabindex`) reversed outright — the DOM *property*
defaults to `0` for SVG in Chrome while the *attribute* was absent, which is
the difference between "eight unnamed tab stops" and "not focusable at all".
When a probe is found to be misaimed, re-run everything it touched; do not
salvage the half that looks plausible.

## Empty is not failure, and only one of them gets tested

The empty state is the one degenerate case everybody remembers: no results, no
items, new account. It gets a designed screen and a passing test. **Failure** —
the request 500s, the payload is truncated, the JSON does not parse — usually
gets nothing, and it is invisible precisely because the empty-state test looks
like it covered the neighbourhood.

They are not the same input. An empty list is a *successful* response: the
loaded flag flips, the store publishes, the designed empty state renders. A
failed request never publishes anything, so the UI stays in whatever it shows
before data arrives — which is the skeleton, forever.

Measured on one project, intercepting a single endpoint at four settings:

| Injected | What rendered |
|---|---|
| real data | full UI, charts, 0 console errors |
| `{"events": []}` | full UI, 11 tabs, "No tool calls yet." |
| HTTP 500 | topbar only; 70 skeleton nodes, same at 3, 8, 15 s |
| truncated JSON | identical to the 500, and **zero console output** |

The `{"events": []}` row is the correct rendering, all 11 tabs present; the
500's 70 skeleton nodes were unchanged at 3 s, 8 s and 15 s.

No `role="alert"`, no live region, no retry control, nothing in the log. The
mechanism was a textbook version of the seam above: the fetch hook computed an
error-aware pending flag with a comment naming this exact symptom, and the page
consumed the *store* instead of the hook.

How to run it, cheaply — intercept one endpoint and cycle it through:

- **HTTP 500** (and 401, and 403 — they often take different paths)
- **a valid but empty payload** — the control that proves your probe works
- **malformed JSON**, truncated mid-object
- **a response that never resolves** — hold the route open
- **the right shape with wrong types** — `null` where an array is expected

Then ask three questions of each: *is there a message, is there a way to retry,
and did anything get logged?* Three noes is a finding. And hold the failure
under observation for 15 s — "still loading" and "permanently stuck" look
identical at 3 s, and only one of them is a bug.

Note which case is the positive control here: the empty payload. If your probe
cannot render the designed empty state, it is not reaching the endpoint, and
every conclusion you draw from the failure cases is worthless.

## Two correct constants, one defect

The hardest seams to read out of source are the ones where every individual
value is defensible and the bug lives in the *relationship* between them. Both
sites look right in review. Both may carry comments explaining why they are
right. Neither comment mentions the other.

Measured on one project: a playback slider's keyboard step was `1` second, and
the seek helper snapped back to the live edge for any target within `2` seconds
of it, so that a drag landing slightly short of the head would not freeze just
behind it. Both choices were deliberate and the 2 s rule carried a twelve-line
comment describing the real bug it fixed. The defect was only `1 < 2`: an arrow
press at the live edge always targeted `elapsed - 1`, always fell inside the
window, and was always routed straight back to "go live". The smallest and most
reachable keyboard step was a permanent no-op at the most common starting
position, while the larger steps worked fine — which is exactly the pattern that
makes it look like the keys "just don't work sometimes".

What generalises:

- **No amount of reading either file alone finds this.** It took pressing the
  key and watching the value not change. When a control has both a step size
  and a tolerance — sliders, drag snapping, debounce vs animation, retry delay
  vs timeout, poll interval vs request duration — compare the two *numbers*, and
  test the smallest increment specifically. Big steps working is not evidence.
- **Fix the relationship, not whichever constant you found first.** Retuning
  either number trades one bug for another. Here the honest fix was to
  distinguish intent: a pointer drag near the head is imprecise and should be
  forgiven, a keyboard step is exact and must not be — so the keyboard opts out
  of the tolerance.
- **Then guard the behaviour the original constant protected.** Bypassing the
  snap in *both* directions would have fixed the backward step while reopening
  the very latch bug the window existed for, because a forward step landing on
  the head would no longer re-latch. The regression test has to assert the old
  behaviour explicitly, or the fix silently trades places with the bug.

## Verify the fix, not the rule that prompted it

The cheapest way to ship a broken fix is to re-run the single check that failed.
It passes, and you stop. Three things measured on one project, all caught only
because the verification asserted *structure at more than one viewport* instead:

- **Two elements assumed to be breakpoint complements were not.** A page title
  appeared twice — once in a desktop rail, once in a mobile nav — so both were
  promoted to `<h1>`, with a code comment asserting "exactly one of the two is
  ever in the layout". Measured at 1440: **two `<h1>`s in the layout**. The
  assumption had been written into a comment as though it were established. The
  fix that actually works puts one visually-hidden heading in the CONTENT, which
  is correct at every width by construction rather than by a belief about CSS.
- **The fix surfaced a pre-existing defect.** Adding the first `<h1>` to a page
  immediately produced a `heading-order` violation, because its section titles
  were `<h3>`. That was always wrong and had been invisible while no `<h1>`
  existed. The new violation was the old structure becoming legible — and the
  honest response is to fix the hierarchy, not to back out the heading.
- **A landmark fix held at 1440 and not at 390.** Wrapping a sidebar in `<nav>`
  and `<header>` took `region` from 202 violations to zero on desktop. At 390px
  a *different*, mobile-only top bar was still outside every landmark, plus an
  image whose `alt` duplicated the text beside it — neither visible at desktop.
  Verifying only at the width that motivated the change would have shipped
  "all routes clean" and been wrong for every phone user.

So: assert the invariant ("exactly one `<h1>` in layout", "zero violations"), at
every viewport the change can reach, and check that nothing you did not intend
to touch moved. And when a fix reveals a new failure, read it as information
about the code rather than as a fault in the fix.

One more, from the same pass: **your own fix can make someone else's real
finding look false.** Two defects were fixed while a parallel review was still
running, and a verifier re-testing the live tree reported one of them "not
real" — correctly, for the tree it saw, and wrongly about the finding. If work
is happening concurrently, record what you changed and when, or verdicts will
quietly contradict findings that were true when they were made.

## The honest close

You will not find everything, and a report implying otherwise is worse than one
that admits its limits. Say which seams you worked, which questions you asked,
which amplifiers you ran, and which you did not. "I walked the pointer paths and
the data edges at three viewports; I did not touch keyboard, touch, or the
error states" is a useful report. "Looks fine" is not.

## The app may not show you the error text you injected

When you fulfil a failure response, the UI often maps the server's message
to its own copy. Probing for the string you INJECTED then finds nothing and
reads as "the app renders no error at all" — a false absence, and a much
more serious-sounding finding than the real one.

Measured once: a 401 carrying allauth's "The email address and/or password
you specified are not correct." rendered as "Incorrect email or password."
The probe reported `bannerShown=false`; the banner was there the whole time.

Two rules:

1. Before concluding an element is absent, dump the rendered text
   (`document.body.innerText`) and look. One extra line separates
   "the app is silent" from "my needle was wrong".
2. Match on what the app renders, or on structure (the banner's container,
   a tone class, `[role]`), not on the payload you controlled.

The same applies in reverse: finding your injected string proves the app
passed the server text through verbatim, which is itself worth noting when
the message could carry raw backend detail to a user.

## "Reproducible" means reproducible under a CONTROLLED environment

A finding can pass every reproducibility check you know and still be an
artifact of shared state you did not reset.

Measured once, apparently conclusively:

* Firefox showed 33 broken images on a page where Chromium showed 0.
* Every response was HTTP 200 — not a 404 cascade.
* Fetching one failing URL twice returned BYTE-IDENTICAL responses — so
  not a race.
* A third decoder (PIL) also rejected the bytes — so not a browser quirk.
* The payload was 164 bytes short of its source and un-resized — so the
  server really was emitting something wrong.

Three independent decoders agreeing is normally the end of the argument. It
was still wrong. The same URL later returned a correct, resized, cleanly
decoding image, and rerunning with the server-side cache cleared before EACH
engine gave identical results for both.

The engine was confounded with **server load and cache state**. Repeat
fetches proved the bytes were stable in that moment, not that the condition
was.

Before filing any A-vs-B difference, ask what is SHARED between the arms —
build caches, optimizer caches, warmed queries, other agents' load — and
reset it before each arm, or run the arms in both orders. If the effect
survives that, it is real.

Corollary: the first arm you run warms shared state for the arms that
follow. A comparison where A always runs before B measures order as much as
identity.

## A zero is only evidence if you show the non-zero was possible

"No wasted re-renders during 12 s idle" sounds like a clean result. It is
unfalsifiable unless you also show the app was DOING something in that
window: on a finished run the polls legitimately stop, and "nothing
re-rendered" is trivially true when nothing fetched.

Measured: counting API requests in the SAME window turned the zero into
evidence — 6 requests on one route and 15 on another, with 0 commits and 0
components performing work. The app polled 21 times and re-rendered nothing.

The pattern generalises to every absence you report. Pair the zero with a
counter for the mechanism that would have produced a non-zero:

| Claim | Zero you report | Predicate that makes it mean something |
|---|---|---|
| no wasted re-renders | commits = 0 | requests > 0 in that window |
| no console errors | errors = 0 | the code path actually executed |
| no a11y violations | violations = [] | passes > N, rule enabled |
| endpoint failure handled | no stuck skeleton | interception fired |

Without the second column you have measured that nothing happened, which is
not the same as measuring that the right thing happened correctly.
