# Quick-reply prompt presets

One-tap canned prompts from the author's phone remote-control app for Claude Code. Each chip
fills the composer with the text below and sends it; `/`-prefixed entries run as the real slash
command. They exist because supervising an agent from a phone means sending the same short
instructions over and over, worded the same way every time.

## Continue

```text
Continue — yes to all pending in-scope, reversible actions you already proposed; do not ask again. If a usage limit interrupted the task, resume only the necessary interrupted work. Complete the original request and its acceptance criteria using the cheapest capable models and proportional verification. Do not broaden scope, invent improvements, restart completed work, or create extra subagents or workflows. Stop and report concisely when the required work is complete. Pause only for a genuinely destructive or irreversible action that still needs approval, or a blocker only I can resolve.
```

## Recap

```text
Give me a complete, factual recap of this session so far. First list every task you were asked to handle and what you actually did for each, including concrete changes, files, commits, deployments, and verification results where relevant. Then list everything still left to do: unfinished or background work, blockers, decisions waiting on me, unverified claims, and follow-ups you explicitly deferred. Clearly distinguish completed, in progress, blocked, and optional items. Check the current state where practical instead of relying only on an earlier summary. Do not start new work or fix anything; this is a status report only. Keep it concise, but omit nothing material.
```

## Commit

```text
Commit and push all of your work now — stage everything you have done, commit it with clear messages, and push. Do this WITHOUT interfering with the other agent working in the same repo: commit ONLY your own changes, never `git add -A` or anything that would sweep in their uncommitted in-progress edits to shared files. Where a shared file mixes your changes with theirs, stage just your own hunks (e.g. `git apply --cached` of only your hunks) so their working-tree work stays untouched, and verify each commit contains only your changes before pushing.
```

## Safe Cron

```text
Set up a recurring safety-net cron that fires every 2 minutes to wake you up, and keep it running until this whole task is genuinely, exhaustively complete with nothing left to do. On each fire: verify the work actually advanced, and if anything hung, stalled, crashed, or got stuck, diagnose it, fix it, and keep going. Do not only look for what got stuck — look for what you have not done yet. Finishing the thing I last asked for is not the end of the task: widen to what it touches, including the problems you noticed along the way and set aside, the coverage that is missing, and the loose ends you were going to mention rather than fix. Work fully autonomously — never ask me, never stop early, never pause waiting for input. Anything you choose not to do needs a real reason you can state in one line — "you did not ask for it" is not one. And deciding not to do something does not close it: a list of things you have set aside is a list to go back through, not permission to stop. What you have finished plus what you have ruled out does not add up to everything — there is always a third pile you have not looked at yet. So every time you think you are done, go and LOOK for new work rather than re-reading what you already know about: re-read the code, run it again, check the parts you have never checked. Only delete the cron once you are absolutely certain there is nothing more to do (as if I asked "is it all done?" and you would answer yes with full conviction) — and you are not there while you can still name something worth doing, nor until a fresh search for new work has genuinely come back empty. Two things this does NOT change: the cron prompt you write is a few lines, not a script, and each fire reports in a few lines — what changed and what needs me, nothing else. My output-style instructions apply on every fire exactly as they do now; exhaustive is about the work, never the write-up. Set it up now.
```

## /compact

```text
/compact
```

## Test

```text
Test the behavior affected by the current work in proportion to its risk. Start with the smallest relevant test set that can reliably catch a regression. For UI work, exercise the primary real-user flow and check the console; add other paths only for a concrete risk. Check plausible boundary and failure cases, not every imaginable one. Do not run unrelated repository-wide sweeps, repeat already-green passes, add speculative coverage, or spawn agents unless a specific gap warrants it. Fix failures caused by the current work and rerun the smallest affected set. Then give one concise report of what ran, what passed or failed, and anything untested.
```

## Improve?

```text
Do not change anything. Looking at what we are working on right now, what could be improved, and what else could we do to make it better? Give a short ranked list, each item one or two sentences with the concrete benefit. I will pick.
```

## Concise

```text
Be concise from here on, and stay that way for the rest of this session. You are far too verbose by default. Write in plain, professional language and get to the point: lead with the answer or the result, then only the detail that actually changes what I do next. Cut the preamble, the restating of my question back at me, the narration of what you are about to do, the recap of what you just did, and the closing summary of a summary. No filler, no hedging, no padding a short answer out to look thorough. Prefer short paragraphs, tight bullets, and small tables over walls of prose, and drop any sentence that carries no information — if removing it loses nothing, it should not be there. Being brief is not being vague: keep every fact, number, file path, and caveat that matters, and say plainly when something is uncertain, unverified, or still broken rather than smoothing over it. Give me the long version only when I ask for it. This changes how you write, not how much work you do — keep doing the full job as thoroughly as before.
```
