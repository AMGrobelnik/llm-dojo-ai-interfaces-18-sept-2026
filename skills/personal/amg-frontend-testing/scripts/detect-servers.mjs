#!/usr/bin/env node
/**
 * Probe for dev servers already listening on the usual ports.
 *
 * Prints JSON: [{ url, status, server, title, ms }]. Exit 0 with an empty array
 * when nothing is up — "nothing found" is an answer, not an error.
 *
 * Four fixes over the probe this is derived from:
 *   - concurrent, not serial. Ten ports at a 500 ms timeout cost ~5 s
 *     serially and ~0.5 s in parallel, and the serial version is dead time
 *     on every single invocation.
 *   - probes 127.0.0.1 AND ::1. Node may resolve "localhost" to ::1 while a
 *     dev server binds IPv4 only, which reports "no servers found" for a
 *     server that is plainly running.
 *   - a generous timeout, and headers END it. A closed port is refused in
 *     ~3 ms (25 ms worst case, measured), so the timeout NEVER gates dead
 *     ports -- it only ever decides
 *     whether a slow-but-alive server is reported. Measured on a Next dev
 *     server compiling "/" on demand: at 700 ms it was missed entirely and
 *     the run took 0.79 s; at 1500 ms it was found and the run took 0.65 s.
 *     A short timeout buys nothing and loses real servers.
 *   - reports the Server header, <title> and elapsed ms, so a human can tell
 *     which app is on which port instead of being asked.
 */
import { argv, exit, stdout } from "node:process"

const DEFAULT_PORTS = [3000, 3001, 3002, 4200, 5000, 5173, 5174, 8000, 8080, 8020, 9000, 1234]
const TIMEOUT_MS = 2500
const BODY_MS = 1500

function usage() {
  stdout.write(`Usage: node detect-servers.mjs [--ports 3000,5173] [--timeout 2500] [--host 127.0.0.1]

Probes each host:port for an HTTP response. Any status < 500 counts as alive.
Prints a JSON array to stdout. Always exits 0 unless the arguments are bad.

  --ports    comma-separated, added to the default list
  --only     comma-separated, used INSTEAD of the default list
  --timeout  milliseconds to wait for response HEADERS (default ${TIMEOUT_MS});
             the body then gets a further ${BODY_MS} ms, and a body that times
             out still counts as a hit. Raising this does not slow the run:
             closed ports are refused in ~3 ms (8 dead ports at a 5000 ms
             timeout measured 0.05 s total). Wall time is set by the slowest
             LIVE server, never by the timeout.
  --host     extra host to probe (default: 127.0.0.1 and [::1])
`)
}

function arg(name) {
  const i = argv.indexOf(`--${name}`)
  return i === -1 ? undefined : argv[i + 1]
}

if (argv.includes("--help") || argv.includes("-h")) {
  usage()
  exit(0)
}

const timeout = Number(arg("timeout") ?? TIMEOUT_MS)
const only = arg("only")
  ?.split(",")
  .map((p) => Number(p.trim()))
  .filter(Boolean)
const extra = arg("ports")
  ?.split(",")
  .map((p) => Number(p.trim()))
  .filter(Boolean)
const ports = only ?? [...new Set([...DEFAULT_PORTS, ...(extra ?? [])])]
const hosts = [...new Set(["127.0.0.1", "[::1]", arg("host")].filter(Boolean))]

/** One probe. Resolves to a hit or null; never rejects. */
async function probe(host, port) {
  const url = `http://${host}:${port}/`
  const started = performance.now()
  const ac = new AbortController()
  let timer = setTimeout(() => {
    ac.abort()
  }, timeout)
  try {
    // GET, not HEAD: dev servers routinely 404 or 501 a HEAD on "/" while
    // serving the app perfectly well on GET.
    const res = await fetch(url, { signal: ac.signal, redirect: "manual" })
    if (res.status >= 500) return null

    // Headers arrived, so the server is PROVEN alive. Re-budget for the body
    // and never let a slow or huge body downgrade a hit to a miss -- the
    // title is a nicety, the hit is the answer.
    clearTimeout(timer)
    timer = setTimeout(() => {
      ac.abort()
    }, BODY_MS)

    let title = null
    const ctype = res.headers.get("content-type") ?? ""
    if (ctype.includes("text/html")) {
      try {
        const body = await res.text()
        title = body.match(/<title[^>]*>([^<]{0,80})/i)?.[1]?.trim() ?? null
      } catch {
        title = null
      }
    } else {
      await res.body?.cancel()
    }
    return {
      url,
      status: res.status,
      server: res.headers.get("server"),
      title,
      ms: Math.round(performance.now() - started),
    }
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

const results = await Promise.all(hosts.flatMap((h) => ports.map((p) => probe(h, p))))

// Collapse 127.0.0.1 and ::1 hits on the same port — they are one server.
const byPort = new Map()
for (const hit of results.filter(Boolean)) {
  const port = new URL(hit.url).port
  if (!byPort.has(port)) byPort.set(port, hit)
}

stdout.write(JSON.stringify([...byPort.values()], null, 1) + "\n")
