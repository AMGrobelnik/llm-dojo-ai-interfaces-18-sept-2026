#!/usr/bin/env node
/**
 * Start server(s), wait until they really answer HTTP, run a command, then
 * tear the whole thing down. Exits with the command's exit code.
 *
 *   node with-server.mjs --server "bun run dev" --port 3000 -- node probe.mjs
 *   node with-server.mjs --server "python api.py" --port 8020 \
 *                        --server "bun run dev"   --port 3000 -- npx playwright test
 *
 * Four defects in the version this is derived from, each of which was observed
 * rather than theorised, and each fixed here:
 *
 *   1. ORPHANS. `Popen(cmd, shell=True)` + `terminate()` signals the SHELL,
 *      not the server. The parent exits, the child is reparented and keeps
 *      LISTENing. Every run leaked a server squatting the port. Fix: spawn
 *      detached (its own process group) and signal the GROUP.
 *   2. STALE SERVER MISTAKEN FOR READY. Readiness was a bare TCP connect, so a
 *      server leaked by defect 1 answered instantly and the whole run silently
 *      tested the wrong process. Fix: refuse to start when the port is already
 *      occupied, and probe real HTTP.
 *   3. DEADLOCK ON A CHATTY SERVER. stdout/stderr were piped and never drained,
 *      so a server that logs steadily filled the ~64 KB pipe buffer and blocked
 *      on write. Fix: stream to a log file.
 *   4. SWALLOWED BOOT ERRORS. On a crash-at-boot the only message was "failed
 *      to start within 30s". Fix: print the log tail on failure.
 */
import { spawn } from "node:child_process"
import { createWriteStream, mkdirSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { argv, exit, stdout, stderr } from "node:process"

function usage() {
  stdout.write(`Usage: node with-server.mjs --server CMD --port N [--server CMD --port N ...] \\
                            [--timeout 60] [--log-dir DIR] -- COMMAND [ARGS...]

--server / --port are positionally paired and repeatable; servers start in the
order given and each must answer HTTP before the next one starts.
Everything after -- is the command to run once all ports are ready.

  --timeout   seconds to wait per server (default 60)
  --log-dir   where server logs go (default: a temp dir, path is printed)
  --allow-existing   reuse a server already on the port instead of refusing
`)
}

if (argv.includes("--help") || argv.includes("-h") || argv.length < 3) {
  usage()
  exit(argv.length < 3 ? 2 : 0)
}

const sep = argv.indexOf("--")
if (sep === -1) {
  stderr.write("with-server: missing `--` separator before the command to run\n")
  exit(2)
}
const head = argv.slice(2, sep)
const command = argv.slice(sep + 1)
if (command.length === 0) {
  stderr.write("with-server: nothing to run after `--`\n")
  exit(2)
}

const servers = []
let timeoutSec = 60
let logDir = tmpdir()
let allowExisting = false
for (let i = 0; i < head.length; i++) {
  if (head[i] === "--server") servers.push({ cmd: head[++i], port: null })
  else if (head[i] === "--port") {
    const s = servers[servers.length - 1]
    if (!s) {
      stderr.write("with-server: --port given before any --server\n")
      exit(2)
    }
    s.port = Number(head[++i])
  } else if (head[i] === "--timeout") timeoutSec = Number(head[++i])
  else if (head[i] === "--log-dir") logDir = head[++i]
  else if (head[i] === "--allow-existing") allowExisting = true
  else {
    stderr.write(`with-server: unknown option ${head[i]}\n`)
    exit(2)
  }
}
if (servers.some((s) => s.port === null)) {
  stderr.write("with-server: every --server needs a --port\n")
  exit(2)
}

/** Real HTTP probe. A TCP connect is not proof the app is up. */
async function answers(port) {
  for (const host of ["127.0.0.1", "[::1]"]) {
    try {
      const ac = new AbortController()
      const t = setTimeout(() => {
        ac.abort()
      }, 700)
      const res = await fetch(`http://${host}:${port}/`, { signal: ac.signal, redirect: "manual" })
      clearTimeout(t)
      if (res.status < 500) return true
    } catch {
      /* not up yet */
    }
  }
  return false
}

const started = []

/** Signal the whole process group, escalating. */
async function stopAll() {
  for (const { child, name } of started.reverse()) {
    if (child.exitCode !== null || child.signalCode !== null) continue
    try {
      process.kill(-child.pid, "SIGTERM")
    } catch {
      /* already gone */
    }
    const died = await Promise.race([
      new Promise((r) => child.once("exit", () => { r(true) })),
      new Promise((r) => setTimeout(() => { r(false) }, 5000)),
    ])
    if (!died) {
      stderr.write(`with-server: ${name} ignored SIGTERM, killing group\n`)
      try {
        process.kill(-child.pid, "SIGKILL")
      } catch {
        /* already gone */
      }
    }
  }
}

let code = 1
try {
  for (const [i, s] of servers.entries()) {
    if (await answers(s.port)) {
      if (!allowExisting) {
        stderr.write(
          `with-server: something is ALREADY serving :${s.port}.\n` +
            `  Refusing to start a second one — a stale server from a leaked run\n` +
            `  looks exactly like a ready server, and the run would silently test it.\n` +
            `  Investigate with:  ss -ltnp | grep :${s.port}\n` +
            `  Or pass --allow-existing to reuse it deliberately.\n`,
        )
        // NOT a bare exit(): process.exit skips the finally below, so any
        // server started earlier in this same loop would be orphaned.
        await stopAll()
        exit(2)
      }
      stdout.write(`with-server: reusing existing server on :${s.port}\n`)
      continue
    }

    const logPath = join(logDir, `with-server-${s.port}.log`)
    // ``--log-dir`` is documented and was unusable without this: the flag
    // accepts any path, and ``createWriteStream`` throws ENOENT rather than
    // creating it, so the script died before starting a single server.
    mkdirSync(logDir, { recursive: true })
    const log = createWriteStream(logPath)
    // An unhandled 'error' on this stream is an UNCAUGHT EXCEPTION, which kills
    // the process without running the finally below — leaking every server
    // already started. Measured: one ENOENT here left a detached server holding
    // its port, which is exactly the "stale server from a leaked run" this
    // script refuses to start alongside.
    log.on("error", (e) => {
      stderr.write(`with-server: log stream error (${logPath}): ${e.message}\n`)
    })
    stdout.write(`with-server: starting :${s.port} — ${s.cmd}\n  log: ${logPath}\n`)
    const child = spawn(s.cmd, {
      shell: true,
      detached: true, // own process group, so we can signal the whole tree
      stdio: ["ignore", "pipe", "pipe"],
    })
    // Drain both streams to a file. Piping without draining deadlocks a
    // server that logs steadily once the ~64KB buffer fills.
    child.stdout.pipe(log)
    child.stderr.pipe(log)
    started.push({ child, name: `server ${i + 1} (:${s.port})`, logPath })

    const deadline = Date.now() + timeoutSec * 1000
    let ready = false
    while (Date.now() < deadline) {
      if (child.exitCode !== null) break
      if (await answers(s.port)) {
        ready = true
        break
      }
      await new Promise((r) => setTimeout(r, 400))
    }
    if (!ready) {
      let tail = ""
      try {
        tail = readFileSync(logPath, "utf8").split("\n").slice(-25).join("\n")
      } catch {
        /* no log */
      }
      stderr.write(
        `with-server: :${s.port} never answered within ${timeoutSec}s` +
          (child.exitCode !== null ? ` (process exited ${child.exitCode})` : "") +
          `\n--- last lines of ${logPath} ---\n${tail}\n`,
      )
      // Same reason as the exit(2) above: this server IS running by now.
      await stopAll()
      exit(1)
    }
    stdout.write(`with-server: :${s.port} ready\n`)
  }

  const run = spawn(command[0], command.slice(1), { stdio: "inherit" })
  code = await new Promise((r) => {
    run.on("exit", (c, sig) => { r(sig ? 1 : (c ?? 1)) })
  })
} finally {
  await stopAll()
}
exit(code)
