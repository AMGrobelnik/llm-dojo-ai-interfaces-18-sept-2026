---
name: amg-is-domain-taken
description: "Checks whether given domain names are already registered, sweeping one keyword across up to 32 TLDs at once via RDAP with a DNS fallback for .io, .co, .me, .gg, .so and .sh, in parallel, printing AVAILABLE / LIKELY AVAILABLE / taken or JSON. Use whenever a name must be confirmed free before anyone commits to it, and whenever a shortlist of brainstormed names needs a fast registered-or-not verdict. Triggers: is this domain taken, domain availability, RDAP, WHOIS-style lookup, check .com .ai .dev .io, bulk TLD sweep for one name, is the name still free. NOT for: registrar prices, renewal costs, promo codes or a where-to-buy recommendation, which domain-hunter owns; NOT for DNS records, traffic analytics or anything on a domain already owned, which amg-cloudflare owns."
---

## Script

### Domain Check (domain_check.py)

Check domain availability across TLDs. Uses RDAP (1197+ TLDs) with DNS fallback for unsupported TLDs (.io, .co, .me, .gg, .so, .sh). Runs checks in parallel (10 threads).

**Example input:**
```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-is-domain-taken" && \
python3 $SKILL_DIR/scripts/domain_check.py myproject
```

**Check specific TLDs:**
```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-is-domain-taken" && \
python3 $SKILL_DIR/scripts/domain_check.py myproject --tlds com,ai,dev,io
```

**Check all 32 TLDs:**
```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-is-domain-taken" && \
python3 $SKILL_DIR/scripts/domain_check.py myproject --all
```

**Check specific full domain names:**
```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-is-domain-taken" && \
python3 $SKILL_DIR/scripts/domain_check.py example.com my-site.ai coolname.dev
```

**JSON output:**
```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-is-domain-taken" && \
python3 $SKILL_DIR/scripts/domain_check.py myproject --json
```

**Parameters:**

`<keyword>` or `<domain1> <domain2> ...` (required)
- If no dots: treated as keyword, expanded across TLDs
- If dots present: treated as full domain names

`--tlds` (optional)
- Comma-separated TLD list (default: com,io,ai,dev,app,co,net,org,xyz,tech)

`--all` (optional)
- Check all 32 TLDs (adds me,cc,gg,so,sh,to,is,ly,fm,tv,systems,tools,solutions,studio,cloud,run,science,research,engineering,software,digital,world)

`--json` (optional)
- Output JSON instead of formatted text

## Result Interpretation

- **AVAILABLE** (green): RDAP confirmed not registered -- high confidence.
- **LIKELY AVAILABLE** (yellow): No RDAP for this TLD, DNS negative -- probably available but verify on a registrar before purchasing.
- **taken** (red): Domain is registered.
- **rate limited**: Too many requests, retry later.
