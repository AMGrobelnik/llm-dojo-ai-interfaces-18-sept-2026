---
name: amg-prompt-optim
description: "Compresses an existing LLM prompt file for conciseness with zero information loss: renders the full prompt including imported shared components, splits it into gap-free segments, measures each with Python len(), and presents a savings table plus inline diffs, editing only segments that save 15 percent or more and only after explicit approval. Use whenever a request asks to optimize, compress, shorten, tighten or cut the token count of a prompt, system prompt, agent instructions or prompt template. Triggers: optimize prompt, compress or shorten prompt, prompt token count, wordy instructions, s_prompt.py, u_prompt.py, prompt components, system prompt trimming. NOT for: writing a new prompt from scratch, tuning a skill's frontmatter description for triggering (use anthropic-skill-creator), producing domain knowledge content (use amg-handbook-forge), or refining an image-generation prompt across rounds of feedback (use amg-iter-image-gen-human)."
---

# Prompt Optimization Skill

Remove words that add no clarity or information. **Keep words that make things clearer**, even if removing them would be shorter. The goal is NOT maximum compression — it's removing genuinely dead weight while preserving (or improving) readability.

Only shorten when the shorter version delivers the same information equally clearly. If extra words help the LLM understand the intent better, they stay.

## Format

For each prompt file, break it into logical segments (tagged blocks like `<principles>`, `<strategic_mindset>`, or functional sections).

**Segments MUST cover the ENTIRE prompt** — when concatenated in order, they must reconstruct the full prompt with no gaps. Every part of the prompt must belong to a segment, even if it's just a few characters (e.g., a one-line instruction between tagged blocks).

Use Python `len()` on the raw string content to count characters. Run the count in code, don't estimate.

**Step 1: Show summary table FIRST** with all segments. For every segment (including shared/skip), show the optimized version's char count and reduction:

```
| # | Segment | Chars | Optimized | % Reduced | Diff |
|---|---------|------:|----------:|----------:|-----:|
| 1 | name    | X     | Y         | P%        | -Z   |
| 2 | name    | X     | X         | 0%        | 0    |
|   | **TOTAL** | **X** | **Y**   | **P%**    | **-Z** |
```

- **Chars**: current segment length (use Python `len()` even for shared/dynamic segments — expand them to get actual char count)
- **Optimized**: proposed length after optimization (same as Chars if no change)
- **% Reduced**: savings as percentage of that segment's chars (0% if no change)
- **Diff**: character difference (e.g., -132, or 0 if no change)
- Every segment gets a numeric row — no "dyn" or "—" placeholders. Expand shared/dynamic components to compute their real char counts.
- TOTAL row sums all columns
- Mark segments with ≥ 15% reduction as **CHANGE**, others as skip

**Step 2: Show full text for EVERY segment** (in prompt order). ALL segments must be shown — shared, local, skip, and CHANGE alike. The user must see the complete prompt broken into segments with nothing omitted.

For **skip** segments, show the full current text in a plain code block:

```
**Segment N: name** [LOCAL/SHARED: file.py] (X chars) — skip
```
[full current text]
```
```

For **CHANGE** segments, show the full text with `diff` blocks **inline** where changes occur. Unchanged lines stay in plain code blocks. Changed lines appear as `diff` blocks with `[brackets]` around the specific changed words, right at their position in the text:

````
**Segment N: name** [LOCAL/SHARED: file.py] (X → Y chars, saved Z) — CHANGE

```
unchanged text before...
```
```diff
-context [old words] context
+context [new words] context
```
```
unchanged text after...
```
````

The `diff` block gives red/green line colors. `[brackets]` highlight the exact words that changed within each line. The reader sees the full segment with changes shown in-place.

## Rules

1. **NO information or clarity loss** — every concept, instruction, constraint, and detail must survive. Words that aid comprehension count as useful even if technically redundant. If the original says "search 5-6 semantically different phrasings", the proposed must too. When in doubt, keep the longer version.

2. **Conciseness techniques** (what TO do):
   - Remove filler words: "their specific field" → "their field"
   - Remove redundant qualifiers: "conceptual novelty" → "novelty" (when context is clear)
   - Remove redundant "known": "Apply known method X to known domain Y" → "Apply method X to domain Y"
   - Condense sentence structure: "If your idea lives in a crowded neighborhood of similar approaches, it's NOT novel enough." → "Crowded neighborhood of similar approaches → NOT novel enough."
   - Remove examples when the point is already clear without them (e.g., "(e.g., adaptive split selection exists in BART → applying it to FIGS is not novel)" can be dropped if the rule itself is sufficient)
   - Remove wrapping phrases: "When you find similar work, do NOT rationalize" → "Do NOT rationalize" (the "when" is obvious from context)
   - Compress references: "If you found even 1 paper with a similar core mechanism, ABANDON" → "Even 1 paper with similar core mechanism → ABANDON"
   - Use arrow notation for implications: "X is Y" → "X → Y" where appropriate

3. **What NOT to do**:
   - Don't remove specific numbers (e.g., "5-6 phrasings", "2-3 fields")
   - Don't remove named concepts (e.g., "FRAMEWORK PORTING", "GAP-FILLING")
   - Don't merge distinct mistakes/principles into one
   - Don't change the meaning or weaken emphasis (keep ALL CAPS emphasis words)
   - Don't remove CHECK: lines — these are actionable self-verification steps
   - Don't rewrite from scratch — edit the existing text
   - Don't add new information or instructions
   - Don't strip words that make intent clearer to an LLM — "What we're doing and why" is clearer than just removing it even if field names seem self-explanatory

4. **Shared components** — if a segment comes from a shared/imported file used by multiple prompts, flag it clearly. Changes to shared components affect all prompts that import them.

5. **Threshold** — only apply changes to segments saving ≥ 15%. Display all segments but skip editing those below threshold.

## Workflow

1. Read the prompt file (e.g., `s_prompt.py`, `u_prompt.py`)
2. Read any component files it imports (check imports at top of file)
3. Render the full prompt text by expanding all component calls
4. Break into segments
5. For each segment: compute CURRENT char count and PROPOSED char count using Python `len()`
6. **Always show ALL segments** with their full CURRENT text, char counts, and savings.
7. **Only apply changes to segments saving ≥ 15%**
8. Show total savings at the end (only counting segments that meet the threshold)
9. Wait for explicit user approval before applying any changes
10. After approval, apply changes to the actual source files
11. Verify imports still work: `python -c "from module import function; print('OK')"`

## Example

**Segment 5d: mistake 4** [LOCAL: s_prompt.py] (611 → 479 chars, saved 132) — CHANGE

```
**4. Rationalizing Overlapping Prior Work**
```
```diff
-[When you find similar work, do] NOT rationalize minor differences as novelty. Two [common] traps:
+[Do] NOT rationalize minor differences as novelty. Two traps:
```
```

FRAMEWORK PORTING: "Nobody did this in MY framework" — if the core mechanism exists in any context,
```
```diff
-porting [it] is engineering, not novelty. [(e.g., adaptive split selection exists in BART → applying it to FIGS is not novel)]
+porting is engineering, not novelty.
```
```

GAP-FILLING: Papers A, B, C
```
```diff
-[each] cover variants → you propose the missing combination. [An expert] would say
+cover variants → you propose the missing combination. [Expert] would say
```
```
"obviously someone will do that eventually."
```
```diff
-CHECK: [If the] core mechanism exists in ANY context, ABANDON. Don't salvage by narrowing scope.
+CHECK: Core mechanism exists in ANY context [→] ABANDON. Don't salvage by narrowing scope.
```
