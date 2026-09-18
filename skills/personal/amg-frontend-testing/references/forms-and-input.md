# Forms, input and files

Text arrives in a field five different ways and they fire **different events**.
A handler wired to the wrong one passes a test that types and breaks for a user
who pastes. Most form test suites exercise exactly one channel.

Event traces below were measured in Chromium; they are not folklore.

---

## The five value-arrival channels

How the value arrives, and the events each way fires:

- **`locator.fill("x")`** — `beforeinput(insertText)`, `input`.
  **No key events, no `change`.**
- **`locator.pressSequentially("ab")`** —
  `keydown, beforeinput, input, keyup` **per character**.
- **`keyboard.insertText("x")`** — `beforeinput(insertText)`, `input`.
  No key events.
- **Ctrl+V paste** —
  `keydown ×2, paste, beforeinput(insertFromPaste), input, keyup ×2`.
- **`el.value = "x"`** (autofill, password manager) — **nothing at all**.

So `fill()` — the default in almost every test — skips key events entirely. Any
debounce, typeahead, mask, character counter or submit-on-Enter wired to
`keydown` is untested by it.

**Run the app's critical field through all five and assert the same end state:**

```ts
const channels = {
  fill:   () => f.fill("abc"),
  type:   () => f.pressSequentially("abc"),
  insert: async () => { await f.click(); await page.keyboard.insertText("abc") },
  paste:  async () => {
    await page.evaluate((t) => navigator.clipboard.writeText(t), "abc")
    await f.click(); await page.keyboard.press("ControlOrMeta+KeyA")
    await page.keyboard.press("ControlOrMeta+KeyV")
  },
  autofill: () => f.evaluate((el) => {
    // What Chrome autofill and every password manager actually do.
    const set = Object.getOwnPropertyDescriptor(el.constructor.prototype, "value")!.set!
    set.call(el, "abc")                                  // bypasses React's value tracker
    el.dispatchEvent(new Event("input", { bubbles: true }))
    el.dispatchEvent(new Event("change", { bubbles: true }))
  }),
}
for (const [name, run] of Object.entries(channels)) {
  await f.fill(""); await run(); await f.blur()
  await expect(derivedOutput, name).toHaveText("ABC")
}
```

Autofill deserves its own four-shape matrix — **silent / input-only /
change-only / both** — because managers differ. The classic bug is "the sign-in
button stays disabled after the password manager fills both fields".

## The validation state machine

Drive every transition, not the happy path. The five states — pristine,
touched, dirty, submitting, server-error — and the bugs living between them:

```ts
await expect(err).toHaveCount(0)                 // pristine: no error yet
await f.click(); await f.blur()
await expect(err).toHaveCount(0)                 // touched-but-unedited ≠ dirty
await f.pressSequentially("bad"); await f.blur()
await expect(err).toBeVisible()                  // dirty + touched → error
await f.fill("a@b.com"); await f.blur()
await expect(err).toHaveCount(0)                 // error clears on fix

// Slow 422 with a field-level error
await submit.click()
await expect(submit).toBeDisabled()              // submitting latch ENGAGED
await expect(err).toHaveText(/already taken/i)   // server error surfaced
await expect(submit).toBeEnabled()               // latch RELEASED after failure
await f.pressSequentially("!")
await expect(err).toHaveCount(0)                 // server error cleared on edit
```

Native event order is **focus → input → change → blur** — `change` fires
*before* `blur`. So "validate on change" and "validate on blur" are genuinely
different transitions, and a test that only blurs cannot tell them apart.

### `:user-invalid` — the browser's own "touched" oracle

For fields with native constraints, this beats reaching into framework
internals. Measured behaviour:

| After | `:invalid` | `:user-invalid` |
|---|---|---|
| Page load, empty `required` field | true | **false** |
| Focus then blur | true | **false** |
| `el.reportValidity()` | true | **false** |
| A real submit-button click | true | **true** |

So `:user-invalid` tracks *edited or submit-attempted*, not *focused* — exactly
the "has the user earned seeing this error" question. Assert your error UI
agrees with it; premature error display is the most common form bug there is.

Assert `validity.*` flags rather than message prose — messages are localized
and change.

## Submission counting

Two silent duplicate-submit paths, both worth one assertion each:

- **Reload after a POST re-POSTs**, and under automation there is no "confirm
  resubmission" interstitial to stop it. Assert `posts === 1` after `reload()`
  — the fix is post/redirect/get or an idempotency key.
- **`dblclick` on a slow submit fires twice.** So does double-Enter. Assert
  exactly one request.

And **assert the request body, not the toast**. A toast proves the UI thinks it
succeeded; `request.postDataJSON()` proves what actually left — catching dropped
fields, untrimmed values, wrong content type, unsanitized filenames.

## Accessible error wiring

Visible error text a screen reader never announces is a real and common bug.
`toHaveAccessibleErrorMessage()` reads `aria-errormessage` **only when
`aria-invalid="true"`** — if the app wires errors through `aria-describedby`
instead, use `toHaveAccessibleDescription()`. Assert `aria-invalid` *clears* on
fix too.

## Files in

Only when `input[type=file]` exists. Build buffers in memory; no fixture files
needed:

```ts
await input.setInputFiles([{ name: "x.csv", mimeType: "text/csv", buffer: Buffer.from("a,b") }])
```

The battery: wrong type against an `accept` filter, **zero bytes**, a unicode
name, a `../../` traversal-shaped name, a 300-character name, 200 files at
once, and `setInputFiles([])` to clear. For a hidden input behind a styled
button, `page.waitForEvent("filechooser")`.

**Playwright cannot drop files.** A drop zone needs a synthesized
`DataTransfer` inside `evaluate` — and `evaluateHandle` if you want to assert
the hover state between `dragenter` and `drop`. Whichever path the picker
validates, the drop path must validate identically; they are usually two code
paths and only one gets the checks.

## Files out, and the clipboard

- **Download**: `waitForEvent("download")`, then assert `failure() === null`,
  the `suggestedFilename()`, and the byte content — a zero-byte download
  reports success. Race it against `context.waitForEvent("page")` if the app
  might open a tab instead.
- **Clipboard**: needs `permissions: ["clipboard-read", "clipboard-write"]` in
  Chromium. Assert the payload *and* the flavors. Then stub a **rejecting**
  `writeText` and confirm the "Copied!" toast does not appear — a success
  message on a failed copy is the actual bug.
- **File System Access API** (`showSaveFilePicker`) exists in headless but is
  undrivable, so those flows are usually completely untested. Stub it in an
  init script, record the writes, and stub the `AbortError` cancel path too.

## Rich text and IME

Only when `[contenteditable]` exists, or `compositionstart` appears in the
bundle.

- **`fill()` on a contenteditable is one `insertText`** — mention triggers,
  markdown shortcuts and autoformatters never fire. Use select-all +
  `pressSequentially`.
- **The paste sanitizer trap**: the browser sanitizes the *default* paste, but
  `getData("text/html")` still carries the hostile markup — so any custom
  `onPaste` handler is unprotected. Paste hostile-shaped HTML and assert both
  the DOM *and* that no custom handler re-inserted what the browser stripped.
- **Pasting an image** has `types === ["Files"]` and no text flavor at all. The
  app must preview, upload, or explain — never silently no-op.
- **IME/composition**: CDP `Input.imeSetComposition` then `Input.insertText`
  (Chromium only). The assertion that matters: **Enter mid-composition confirms
  the candidate and must not submit the form.**

## Number and length edges

- `input[type=number]`: `fill()` **throws** on junk; typing junk leaves
  `value: ""` with `badInput: false`. Assert how the app parses `""`, `"-"`,
  and `"1e5"`.
- `maxlength` truncates both `fill` and typing, so you cannot reach an
  over-length state through either — use the native setter, and expect no help
  from `validity.tooLong`.

## Drag to reorder

Probe which family you are dealing with before writing anything —
`el.closest('[draggable="true"]') !== null`. Native HTML5 drag → `dragTo()`
works. A JS library (dnd-kit, react-beautiful-dnd, SortableJS) → `dragTo()`
silently does nothing or silently passes; you need real
`mouse.down` → a threshold-exceeding move → `mouse.move(..., { steps: 10 })` →
a settle frame → `mouse.up`. Wrong family means a test that proves nothing.

Assert the **keyboard** reorder path too; it is almost always missing.
