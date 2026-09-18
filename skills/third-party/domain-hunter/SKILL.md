---
name: domain-hunter
description: "Brainstorms brandable domain names and turns them into a purchase decision: compares registrar pricing for first year versus renewal across Cloudflare at-cost, Spaceship, Porkbun, NameSilo, Namecheap and Dynadot, hunts promo codes, and ends in one recommendation with a price-comparison table. Use whenever a domain is about to be BOUGHT — weighing candidate names, choosing a registrar, or asking what a .ai or .io actually costs per year. Triggers: buy or register a domain, cheapest registrar, domain price comparison, renewal price, promo code, coupon, domain deal, .ai two-year minimum, WHOIS privacy, tld-list, Spaceship API. NOT for: a plain registered-or-not lookup on a name, which amg-is-domain-taken answers faster and more reliably; NOT for DNS, CDN or analytics on a domain already held, which amg-cloudflare covers."
---

# Domain Hunter Skill

Help users find and purchase domain names at the best price.

## Workflow

### Step 1: Generate Domain Ideas & Check Availability

Based on the user's project description, generate 5-10 creative domain name suggestions.

**Guidelines:**
- Keep names short (under 15 characters)
- Make them memorable and brandable
- Consider: `{action}{noun}`, `{noun}{suffix}`, `{prefix}{keyword}`
- Common suffixes: app, io, hq, ly, ify, now, hub

**CRITICAL: Always check availability before presenting domains to user!**

Use one of these methods to verify availability:

**Method 1: WHOIS check (most reliable)**
```bash
# Check if domain is available via whois
whois {domain}.{tld} 2>/dev/null | grep -i "no match\|not found\|available\|no data found" && echo "AVAILABLE" || echo "TAKEN"
```

**Method 2: Registrar search page**
Open the registrar's domain search in browser to verify:
```bash
open "https://www.spaceship.com/domains/?search={domain}.{tld}"
```

**Method 3: Bulk check via Namecheap/Dynadot**
- https://www.namecheap.com/domains/registration/results/?domain={domain}
- https://www.dynadot.com/domain/search?domain={domain}

**IMPORTANT:**
- Only present domains that are confirmed AVAILABLE
- Mark any uncertain domains with "(unverified)"
- Present suggestions to user and **wait for confirmation** before proceeding
- Ask user to pick their preferred options or provide feedback
- Only move to Step 2 after user approves domain name(s)

### Step 2: Compare Prices

Use **WebSearch** to find current prices:

```
WebSearch: "cheapest .{tld} domain registrar 2026 site:tld-list.com"
WebSearch: ".{tld} domain price comparison tldes.com"
```

**Key price comparison sites:**
- tld-list.com/tld/{tld}
- tldes.com/{tld}
- domaintyper.com/{tld}-domain

### Step 3: Find Promo Codes

> **Optional — the two skills this step delegates to are NOT installed here.**
> Checked 2026-08-20: no Twitter or Reddit skill exists in
> `.claude/skills/`, in `~/.claude/skills/`, or in notes-repo's
> `resources/skills/`, so `scripts/search_tweets.py` and
> `scripts/search_posts.py` are not on this machine and the `cd` below
> lands nowhere. Skip to Step 4 unless you have installed them; the
> commands are kept because they are correct *given* those skills, and
> the registrar handles below are useful on their own for a manual search.

Use **Twitter skill** to search registrar accounts:

```bash
cd <twitter_skill_directory>
python3 scripts/search_tweets.py "from:{registrar} promo code" --type Latest --limit 15
python3 scripts/search_tweets.py "{registrar} promo code coupon" --type Latest --limit 15
```

Use **Reddit skill** to search domain communities:

```bash
cd <reddit_skill_directory>
python3 scripts/search_posts.py "{registrar} promo code" --limit 15
python3 scripts/search_posts.py "{registrar} coupon discount" --subreddit Domains --limit 10
```

**Major registrar Twitter handles:**
- @spaceship, @Dynadot, @Namecheap, @Porkbun, @namesilo, @Cloudflare

### Step 4: Recommend

Present final recommendation in this format:

```
## Recommendation

**Domain:** example.ai
**Best Registrar:** Spaceship
**Price:** $68.98/year (2-year minimum = $137.96)
**Promo Code:** None available for .ai
**Purchase Link:** https://www.spaceship.com/

### Price Comparison
| Registrar | Year 1 | Renewal | 2-Year Total |
|-----------|--------|---------|--------------|
| Spaceship | $68.98 | $68.98  | $137.96      |
| Cloudflare| $70.00 | $70.00  | $140.00      |
| Porkbun   | $71.40 | $72.40  | $143.80      |
```

## Important Notes

1. **Premium TLDs** (.ai, .io) rarely have promo codes - wholesale costs are too high
2. **.ai domains** require 2-year minimum registration
3. **Cloudflare** offers at-cost pricing with no markup
4. **Renewal prices** often differ from registration - always check both
5. **WHOIS privacy** is free at most registrars (Cloudflare, Namecheap, Porkbun)

## References

- [references/registrars.md](./references/registrars.md) - Detailed registrar comparison
- [references/spaceship-api.md](./references/spaceship-api.md) - Spaceship API for automated domain operations
