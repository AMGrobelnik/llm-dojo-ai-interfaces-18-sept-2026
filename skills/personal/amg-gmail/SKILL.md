---
name: amg-gmail
description: "Reads, searches, sends, drafts, replies to, labels and archives the author's personal Gmail through the Zapier-MCP server, and drives the other Zapier-connected apps on it — Trello cards, Notion, Google Docs, Discord, ChatGPT, Deepgram. Use whenever a request involves checking or searching the inbox, reading, sending, drafting, replying to, labeling or archiving mail, building a morning digest, telling which messages are Done versus not-Done in Shortwave, looking up Trello cards, or repairing a Zapier MCP that is missing, unauthenticated, or returning stale-auth or halted errors. Triggers: gmail, inbox, unread, email digest, send or draft or reply, archive, label, Shortwave Done, Zapier MCP, list_enabled_zapier_actions, Trello card, Notion page, stale auth. NOT for: uploading, backing up or sharing large files and run folders (use amg-dropbox), the work Google Workspace account, or SMTP and mail-sending code inside this repo."
---

# amg-gmail — the author's Gmail + Zapier MCP control surface

The author's Gmail and a handful of other apps are reachable from Claude Code
through a **Zapier MCP** server called `Zapier-MCP`. There is **no direct Gmail
API and no local script** — everything goes through Zapier's MCP tools. The author
runs the **Shortwave** email client on top of this same Gmail account.

- **Gmail account:** the author's personal Gmail — *not* the work Google
  Workspace. The exact address is whatever is bound to the Zapier-MCP OAuth
  connection; the tools act on it automatically (you never type it).
- **MCP server name:** `Zapier-MCP` · **scope:** user (global, all projects) ·
  **config file:** `~/.claude.json`.
- **Endpoint:** `https://mcp.zapier.com/api/v1/connect` (remote HTTP, OAuth).

---

## 0. Is it already working? (check first)

```bash
claude mcp get "Zapier-MCP"      # want: "User config" + Connected (no "Needs authentication")
```

- Connected → go to **§2** to load the tools, then **§3** to use them.
- Present but **"Needs authentication"** / actions return **stale-auth** → **§6**.
- Not listed at all → **§1** (install from scratch).

The tools show up as **deferred** names `mcp__Zapier-MCP__*`; their schemas are
not loaded until you fetch them (see §2).

---

## 1. Install / reinstall from scratch (if everything is gone)

```bash
claude mcp add --transport http --scope user "Zapier-MCP" \
  https://mcp.zapier.com/api/v1/connect
```

`--scope user` makes it global (every project). Then **the human must**:

1. **Restart Claude Code** — new MCP servers only load at startup
   (`claude -c` resumes the current conversation).
2. Run `/mcp` → select **Zapier-MCP** → **Authenticate** → a browser opens →
   log into Zapier and approve. This is where the Zapier account (and the apps
   inside it, incl. Gmail) get connected.
3. Confirm: `claude mcp get "Zapier-MCP"` shows Connected.

To remove: `claude mcp remove Zapier-MCP -s user`.

> Installing the server and logging in are **human-in-the-loop** (browser OAuth
> under the author's own accounts). An agent can run the `add` command and give the
> `/mcp` instructions, but cannot complete the login itself.

---

## 2. Load the tools (they are deferred)

Before any Zapier call, fetch the tool schemas with ToolSearch:

```
select:mcp__Zapier-MCP__list_zapier_skills,mcp__Zapier-MCP__get_zapier_skill,mcp__Zapier-MCP__list_enabled_zapier_actions,mcp__Zapier-MCP__discover_zapier_actions,mcp__Zapier-MCP__enable_zapier_action,mcp__Zapier-MCP__execute_zapier_read_action,mcp__Zapier-MCP__execute_zapier_write_action
```

The seven core tools:

- `list_enabled_zapier_actions` — **call FIRST**; lists enabled apps + their
  actions and params.
- `execute_zapier_read_action` — run a search/read (Find/Get).
- `execute_zapier_write_action` — run a write (Send/Create/Update).
- `discover_zapier_actions` — search 9,000+ apps to add.
- `enable_zapier_action` — enable an app's actions.
- `list_zapier_skills` — list saved Zapier workflows.
- `get_zapier_skill` — fetch a saved skill's instructions.

---

## 3. The core loop (always the same three moves)

1. **List** what's enabled — `list_enabled_zapier_actions` (add
   `selected_api` to drill into one app).
2. **Inspect** the exact action — `list_enabled_zapier_actions` with
   `tool_name:"gmail_find_email"` (collision-safe) → returns the required
   `params`. **Always inspect before executing**; never guess action keys or
   params — they are not intuitive.
3. **Execute** — `execute_zapier_read_action` / `execute_zapier_write_action`
   with `selected_api`, `action` (the key), `params` (real values),
   `instructions` (natural-language context), `output` (what you want back).

Rules of thumb:
- **Prefer Find/Get lookups over triggers.** `New X` / `Updated X` /
  `X Matching Search` / anything `Instant` are *triggers* that poll on a cursor
  and return **empty when invoked once**. `Find` / `Get` / `Retrieve` query live.
- A **params resolver** may auto-fill inputs (shows `reason: llm-guess`). It's
  convenient but inspect + pass values yourself when correctness matters.
- Put required field values in `params`, not in `instructions`.

### Connected apps → `selected_api` (as of last check)

```
Gmail          -> GoogleMailV2CLIAPI    (20 actions)
Google Docs    -> GoogleDocsV2CLIAPI    (19)
Trello         -> TrelloCLIAPI          (51)
Notion         -> NotionCLIAPI          (31)
Discord        -> DiscordCLIAPI         (18)
ChatGPT/OpenAI -> ChatGPTCLIAPI         (27)
Deepgram       -> DeepgramCLIAPI        (4)
```

---

## 4. Gmail cookbook  (`selected_api: GoogleMailV2CLIAPI`)

**Read — Find Email** · action key `message` · tool `gmail_find_email`
- Required param: `query` — a standard **Gmail search string**.
- Returns ~5 results; **ordering is not strictly by date** — sort yourself.

```
execute_zapier_read_action(
  selected_api="GoogleMailV2CLIAPI", action="message",
  params={"query": "in:inbox"},
  instructions="Latest inbox emails for a digest.",
  output="Up to 5, most recent first: sender, subject, date, one-line snippet.")
```

**Gmail search recipes** (the `query` value):
- `in:inbox` — current inbox
- `is:unread` · `is:starred` · `is:important`
- `from:sender` · `to:me` · `subject:invoice`
- `newer_than:7d` · `older_than:30d` · `after:2026/06/01`
- `has:attachment` · `label:Promotions`
- combine freely: `from:sender in:inbox newer_than:14d`

**Write actions** (inspect params before first use):
- **Send Email** — `gmail_send_email` (writes a real, outbound email)
- **Create Draft** — `gmail_create_draft` · **Create Draft Reply** —
  `gmail_create_draft_reply`
- **Reply to Email** — `gmail_reply_to_email`
- **Add / Remove Label** — `gmail_add_label_to_email` /
  `gmail_remove_label_from_email` · **Create Label** — `gmail_create_label`
- **Archive Email** — `gmail_archive_email` (= mark Done, see §5) ·
  **Delete Email** — `gmail_delete_email`

> **Sending is outward-facing.** Draft first, or confirm the recipient/subject/
> body with the author before calling `gmail_send_email`. Archiving/labeling/
> deleting mutate his mailbox — confirm anything destructive.

---

## 5. Shortwave: "Done" vs "Not Done" (read it through Gmail)

Shortwave's **Done is not a private flag — it archives the message in Gmail**
(removes the `INBOX` label). So the inbox/archive state *is* the not-done/done
split, and it's fully readable via `gmail_find_email`:

- **NOT done** (still in Shortwave inbox): `query = "in:inbox"`
- **Done** (archived): `query = "-in:inbox -in:sent -in:draft -in:trash -in:spam"`
- Scope it: `from:sender in:inbox` = not-done from that sender; swap in the
  archived filter for done-from-them.

**Caveats (state honestly):**
- This reads **inbox vs archived**. Shortwave *Done* archives, so it maps 1:1 —
  but a **manual Gmail archive** looks identical, and **Snooze also leaves the
  inbox**, so snoozed mail reads as "done" until Shortwave resurfaces it. That
  snooze overlap is the one ambiguity you can't resolve from Gmail alone.
- Shortwave's **labels do sync to Gmail** (Promotions/Updates/Socials/Forums +
  custom), so `label:` queries work. But *Done itself* is the **absence of
  INBOX**, not a label.
- You **cannot** see Shortwave-only metadata: the done-timestamp, snooze time,
  pins, or its AI threads.

---

## 6. When an app's auth goes stale ("halted" / stale-auth errors)

Symptoms seen in practice:
- `Authentication is stale for <API>. Please re-authenticate at: <connectAuthUrl>`
- `Action execution was halted by the platform...` — **usually also stale auth**
  (not necessarily an admin restriction). Google apps (Gmail + Google Docs)
  tend to go stale together.

**Fix — re-auth that one app** (human, ~15 s):
```
https://mcp.zapier.com/mcp/servers/<SERVER_ID>/app-auth/<SELECTED_API>
```
e.g. `.../app-auth/GoogleMailV2CLIAPI`. Or in Claude Code: `/mcp` →
**Zapier-MCP** → re-authenticate.

**Find `<SERVER_ID>`:** it's embedded in every execution's `feedbackUrl` and in
stale-auth errors' `connectAuthUrl` — read it live from there. It's
instance-specific and changes on reinstall, so never hardcode it.

Other transient failures:
- **`transport dropped mid-call; response was lost`** → just **retry** the call
  (not an error, the connection blipped).

---

## 7. Trello cookbook  (`selected_api: TrelloCLIAPI`) — the reliable non-Google app

**Find Card** · action key `organization_card_v2` · tool `trello_find_card` —
no required params, so it's a cheap broad read.

Useful params:
- `open_cards_only` (bool) · `cards_limit` (int, default 50)
- `member` — `"@me"` for cards assigned to you (resolver often sets this)
- `due_filter` — `day` | `week` | `month` | `overdue` | `complete` | `incomplete`
- `keyword` · `label` · `board` (dynamic SELECT) · `is_starred` · `organization_id`

Output returns **board_id / list_id (IDs, not names)** — resolve names with
`trello_find_board_by_id` / `trello_find_list_by_id` when you need them. The IDs
are account-specific, so read them live rather than hardcoding.

---

## 8. Recipes

**Morning digest (Gmail + Trello)** — one ask, two apps:
1. `gmail_find_email` `query="in:inbox"` → latest inbox (= not-done).
2. `trello_find_card` `{open_cards_only:true, cards_limit:10}` → open cards.
3. Merge into one summary; optionally flag which emails are from real people vs
   newsletters.

**Triage helpers:**
- "What haven't I done from X?" → `from:X in:inbox`.
- "What did I mark done recently?" → archived filter + `newer_than:7d`.

---

## 9. Other apps — quick gotchas

- **Notion** (`NotionCLIAPI`) — `notion_find_data_source_items` needs a
  `datasource` (dynamic SELECT) **and at least one search field**, else it errors
  `Nothing to search with`. Known data sources: Media, Subject Grades, Subject
  Resources, P 2, AN 2, DS 2, ARS, LA (mostly study/course DBs). Writes
  (`create_page`, `create_database_item`) need a parent page/database.
- **Google Docs** (`GoogleDocsV2CLIAPI`) — `Find a Document` requires a `title`
  (no broad "recent docs" list). `Create Document From Text`
  (`google_docs_create_document_from_text`) needs `file` (plain text / basic
  inline HTML — no tables) + `title`.
- **Discord** — reads/writes need a server + channel selection.

---

## 10. Discover & add more apps

```
discover_zapier_actions(app="Slack")        # search 9,000+ apps
enable_zapier_action(selected_api="SlackCLIAPI", app_display_name="Slack")
```
New app auth returns a URL for the human to approve.

**Saved Zapier skills** (`list_zapier_skills` / `get_zapier_skill`):
- `zapier:onboarding` — the built-in onboarding rundown flow.
- `zapier:mcp-roast` — email-persona vs chat-persona roast.
