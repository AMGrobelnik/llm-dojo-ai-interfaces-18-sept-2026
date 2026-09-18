---
description: Tear down ALL RunPod pods, then hand-build and push both Docker images via buildx with the registry cache. SUPERSEDED and destructive — the canonical ship path is push to origin/main (the local aii-image-watcher builds both images automatically) then `aii_launcher --redeploy <sha>`. Reach for this only when a manual out-of-band build is specifically needed.
---

MAXIMIZE PARALLELISM. Launch everything that can run concurrently in a SINGLE message with multiple tool calls.

Builds use `docker buildx` with a **registry build cache** (`type=registry,mode=max`) so cold builds on any machine reuse cached stages, and `--push` ships straight to Docker Hub in one step (no separate `docker push`).

**Step 0 — ensure the buildx builder exists (idempotent; run once per machine):**

The default `docker` driver cannot export a registry cache (`type=registry,mode=max`) on an overlay2 host, so a persistent `docker-container` builder is required:

```bash
docker buildx inspect aii-builder >/dev/null 2>&1 \
  || docker buildx create --name aii-builder --driver docker-container --bootstrap
```

**Step 1 — all in parallel (one message, 3 tool calls):**

- Delete all running AND suspended/exited RunPod pods via REST API
- Build + push **pipeline** with registry cache (background):

```bash
docker buildx build --builder aii-builder \
  -f Dockerfile.pipeline -t <author>/aii_pipeline:latest \
  --cache-to   type=registry,ref=<author>/aii_pipeline:buildcache,mode=max,image-manifest=true,oci-mediatypes=true,ignore-error=true \
  --cache-from type=registry,ref=<author>/aii_pipeline:buildcache \
  --push .
```

- Build + push **server** with registry cache (background):

```bash
docker buildx build --builder aii-builder \
  -f Dockerfile.server -t <author>/aii_server:latest \
  --cache-to   type=registry,ref=<author>/aii_server:buildcache,mode=max,image-manifest=true,oci-mediatypes=true,ignore-error=true \
  --cache-from type=registry,ref=<author>/aii_server:buildcache \
  --push .
```

Notes:

- `--push` builds inside BuildKit and uploads in one step — it **replaces** the old `docker build` + `docker push`. There is no separate push step.
- Each image gets its OWN sibling `:buildcache` tag (distinct from `:latest`, as required). The two caches never collide.
- `mode=max` caches all stages (including intermediate multi-stage layers) so cold builds on other machines reuse them; `image-manifest=true,oci-mediatypes=true` keeps the cache artifact Docker-Hub-compatible; `ignore-error=true` keeps a transient cache-export hiccup from failing an otherwise-good push.
- The FIRST build against a fresh `:buildcache` tag is a benign full cache miss (`--cache-from` logs "not found"); the SECOND build — or the first on another machine — reuses the cache. Expected, not an error.

**Step 2 — verify each push landed (query the registry, not `docker images`):**

A `--push`-only build does not appear in local `docker images`, so verify against the registry:

```bash
docker buildx imagetools inspect <author>/aii_pipeline:latest
docker buildx imagetools inspect <author>/aii_server:latest
```

(Add `--load` alongside `--push` on a single-arch build if you also want the image in local `docker images` for a `docker run` smoke test.)

**Step 3 — after both pushes complete:**

- Git commit all staged+unstaged changes and push to remote

**Maintenance:** the `docker-container` builder keeps a growing local cache volume that `docker system prune` does NOT touch — run `docker buildx prune` (or `-a`) periodically to cap disk.
