export const meta = {
  name: 'handbook-delta-gate-mi',
  description: 'P6 delta gate (mech interp): blind A/B of the handbook vs a tool-equipped baseline',
  phases: [
    { title: 'Ideate', detail: 'k=6 per arm — tool-equipped baseline vs handbook arm' },
    { title: 'Judge', detail: '4 independent blind checkers over the shuffled pool' },
  ],
}

// Hardcoded on purpose: attempt 2 of this gate lost its parameters through the
// args channel and silently produced a full, valid-looking but meaningless run.
const DOMAIN = '<FILL: exact domain name>'   // hardcode; do NOT pass via args
const SLUG = '<FILL: handbook slug>'          // hardcode; do NOT pass via args
const SCOPE = '<FILL: one-line scope>'       // hardcode; do NOT pass via args
const K = 6
if (!DOMAIN || !SLUG || !SCOPE) {
  throw new Error('delta-gate: parameters missing — refusing to spawn agents')
}

const IDEA_SCHEMA = {
  type: 'object',
  properties: {
    handbook_read: { type: 'string', description: 'For the handbook arm: the exact first heading line of the file you read, or the literal string HANDBOOK_MISSING. For the baseline arm: the literal string N/A.' },
    direction: { type: 'string' },
    why_not_occupied: { type: 'string' },
    first_experiment: { type: 'string' },
  },
  required: ['handbook_read', 'direction', 'why_not_occupied', 'first_experiment'],
  additionalProperties: false,
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    best_of: { type: 'string' },
    best_of_reason: { type: 'string' },
    ratings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          engages_frontier: { type: 'boolean' },
          avoids_crowded: { type: 'boolean' },
          challenges_assumption: { type: 'boolean' },
          groundbreaking: { type: 'boolean' },
        },
        required: ['id', 'engages_frontier', 'avoids_crowded', 'challenges_assumption', 'groundbreaking'],
        additionalProperties: false,
      },
    },
  },
  required: ['best_of', 'best_of_reason', 'ratings'],
  additionalProperties: false,
}

const TASK = `Propose the SINGLE most promising, genuinely novel research direction in ${DOMAIN} (${SCOPE}) that a strong team should pursue over the next 12 months.\n\nBe concrete and specific. Keep each field to 2-4 sentences. The domain is EXACTLY "${DOMAIN}" - if that seems unset or ambiguous, stop and say so rather than substituting another field.`

phase('Ideate')

const armA = Array.from({ length: K }, (_, i) => () =>
  agent(
    `You are a research agent with web search. Ground yourself in the CURRENT (mid-2026) state of the field before answering - search the literature first.\n\n${TASK}\n\nSet handbook_read to the literal string N/A.\n\n(independent sample ${i + 1}; pursue your own angle, do not hedge)`,
    { label: `base-${i + 1}`, phase: 'Ideate', schema: IDEA_SCHEMA, agentType: 'general-purpose' },
  ),
)

const armB = Array.from({ length: K }, (_, i) => () =>
  agent(
    `FIRST read /home/<user>/projects/research-monorepo/handbook-staging/aii-handbook-auto-${SLUG}/SKILL.md and its sibling volatile.md, and use them as background. If that file does not exist or is empty, set handbook_read to the literal string HANDBOOK_MISSING and stop. Otherwise set handbook_read to the exact first markdown heading line of the file.\n\nYou ALSO have web search - use it to ground yourself in the CURRENT (mid-2026) state of the field.\n\n${TASK}\n\n(independent sample ${i + 1}; pursue your own angle, do not hedge)`,
    { label: `hb-${i + 1}`, phase: 'Ideate', schema: IDEA_SCHEMA, agentType: 'general-purpose' },
  ),
)

const all = await parallel([...armA, ...armB])
const baseRaw = all.slice(0, K)
const hbRaw = all.slice(K)

const missing = hbRaw.filter((r) => r && String(r.handbook_read).includes('HANDBOOK_MISSING')).length
log(`handbook-arm file check: ${missing} of ${hbRaw.filter(Boolean).length} reported HANDBOOK_MISSING`)
if (missing > 0) {
  throw new Error(`delta-gate: ${missing} handbook-arm agents could not read the handbook — arms are not distinct, aborting`)
}

function scrub(t) {
  return String(t || '')
    .replace(/\[S\d+\]/g, '')
    .replace(/handbook/gi, 'background reading')
    .replace(/\s+/g, ' ')
    .trim()
}

const entries = []
baseRaw.forEach((r) => { if (r) entries.push({ arm: 'base', r }) })
hbRaw.forEach((r) => { if (r) entries.push({ arm: 'hb', r }) })

const PERM = [7, 2, 11, 5, 0, 9, 3, 8, 1, 10, 4, 6]
const order = PERM.filter((p) => p < entries.length)
entries.forEach((_, i) => { if (!order.includes(i)) order.push(i) })
const pool = order.map((idx, n) => ({ id: `P${n + 1}`, arm: entries[idx].arm, r: entries[idx].r }))

const poolText = pool
  .map((p) => `### ${p.id}\nDIRECTION: ${scrub(p.r.direction)}\nWHY NOT ALREADY OCCUPIED: ${scrub(p.r.why_not_occupied)}\nFIRST EXPERIMENT: ${scrub(p.r.first_experiment)}`)
  .join('\n\n')

log(`pooled ${pool.length} ideas, de-identified and shuffled`)

phase('Judge')

const verdicts = await parallel(
  Array.from({ length: 4 }, (_, i) => () =>
    agent(
      `You are an independent expert reviewer in ${DOMAIN}. Below are ${pool.length} candidate research directions from mixed, undisclosed sources, in random order. Judge them ONLY on their text.\n\nYou have web search. USE IT to check whether a direction is already occupied before answering avoids_crowded.\n\nFor EVERY id answer four bounded yes/no questions:\n- engages_frontier: does it engage the genuine 2025-2026 state of the field rather than a generic or stale framing?\n- avoids_crowded: is it plausibly NOT inside an already-saturated lane? (search to check)\n- challenges_assumption: does it challenge a load-bearing assumption of the field rather than merely fill a gap?\n- groundbreaking: would a leading researcher call this potentially groundbreaking, as opposed to competent-but-incremental?\n\nThen pick best_of: the id of the SINGLE strongest direction overall, plus a one-sentence reason. Pick exactly one.\n\n${poolText}\n\n(reviewer ${i + 1}: judge independently and strictly)`,
      { label: `checker-${i + 1}`, phase: 'Judge', schema: VERDICT_SCHEMA, agentType: 'general-purpose' },
    ),
  ),
)

return {
  domain: DOMAIN,
  handbook_arm_ok: missing === 0,
  key: pool.map((p) => ({ id: p.id, arm: p.arm })),
  verdicts: verdicts.filter(Boolean),
  ideas: pool.map((p) => ({ id: p.id, arm: p.arm, direction: scrub(p.r.direction).slice(0, 260) })),
}
