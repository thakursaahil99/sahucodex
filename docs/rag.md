# RAG (retrieval-augmented search)

> Status: **implemented in build phase 8.** Semantic "similar problems" on the problem detail page, a semantic
> search endpoint, and retrieval-augmented context in SahuCodeX AI chat. Runs on [Qdrant](https://qdrant.tech)
> (local, open-source, no paid API) for vector storage, with embeddings from Ollama's own `/api/embeddings`.
> Verified end to end against an in-process Qdrant and a real Ollama embedding model — see
> [What was run](#what-was-run).

## Principles

* **Optional, exactly like SahuCodeX AI itself.** Leave `QDRANT_URL` unset and `Settings.rag_configured` is `False`:
  every RAG-dependent feature is simply absent (the "Similar problems" panel doesn't render; `/search/semantic` and
  `/problems/{slug}/similar` answer `503 RAG_UNAVAILABLE`; chat proceeds with no extra context) while the rest of
  the platform works unaffected.
* **Fails cleanly, never fabricates.** A configured but unreachable Qdrant, or an embedding call that fails, raises
  `RagUnavailableError` and surfaces as a clean `503` — never an empty result standing in for "nothing found",
  which would be indistinguishable from a real empty result. Chat's retrieval step is the one exception: there, a
  RAG failure is swallowed and chat proceeds with no extra context, because a missing "by the way, here are some
  related problems" aside is not worth failing someone's question over (see `app.modules.ai.service._related_problems`).
* **Only ever indexes what a solver could already read.** The embedded text is a problem's own title, tags and
  public `description` — the exact words on the problem page. Hidden test cases and the editorial are never part of
  it, by construction: `index_problem` takes the ORM `Problem` only for its title/description/tags, nothing else.
* **The index is never stale by more than "since the last edit."** There is no background reindex job. Indexing
  happens synchronously, in the same request, right after an admin creates, edits, publishes, unpublishes, or
  archives a problem (`app.modules.admin.problems`) — an unpublished or archived problem is removed from the index
  in that same call, not left to rot.
* **Embeddings are Ollama's, independent of `AI_PROVIDER`.** A deployment can run `AI_PROVIDER=openrouter` for chat
  while still using a local Ollama purely for embeddings (`OLLAMA_EMBED_MODEL`) — RAG and chat are two separate
  concerns that happen to both be able to use Ollama, not one feature.

## Setup

```bash
# Option A — Docker Compose
docker compose --profile ai up -d ollama          # embeddings need a model server too
docker compose exec ollama ollama pull nomic-embed-text
docker compose --profile rag up -d qdrant
# .env:  QDRANT_URL=http://qdrant:6333             (the API reaches the `qdrant` service automatically)

# Option B — both installed on the host
ollama pull nomic-embed-text
# a local Qdrant, e.g.:  docker run -p 6333:6333 qdrant/qdrant
# .env:  QDRANT_URL=http://localhost:6333
```

Then restart the API and publish or re-save a problem — indexing happens on that save (see
[Principles](#principles)), not retroactively for problems that existed before RAG was configured. To backfill
every already-published problem once, re-save each one through the admin editor (there is no separate backfill
script; the same "index on save" code path is the only writer, so this keeps there being exactly one way a vector
gets into Qdrant, and only from what an admin currently believes is published).

`OLLAMA_EMBED_MODEL` defaults to `nomic-embed-text` (768 dimensions — see `app.modules.rag.service._VECTOR_SIZE`).
Swapping to a different embedding model with a different output size needs a new `QDRANT_COLLECTION` name, since a
Qdrant collection is fixed-dimension: the old collection's vectors would not compare against the new model's.

## What it does

* **`GET /api/problems/{slug}/similar`** — the problem detail page's "Similar problems" panel. Nearest neighbours
  of the given problem's own vector (its own point is always excluded from its own results).
* **`GET /api/search/semantic?q=...`** — free-text semantic search, complementing (not replacing) the existing
  keyword `tsvector` search in `app.modules.problems.search`. Meant for "problems about X" queries a keyword match
  would miss (e.g. "ordering things so each comes after what it depends on" finding a topological-sort problem that
  never uses either of those exact words).
* **Retrieval-augmented chat context** — when a SahuCodeX AI chat message has no problem already attached (an
  open-ended question, not "help with the problem I'm on"), the top 3 semantically related problems are named in
  the system prompt by slug and title, so the model can point the learner at a real problem instead of inventing
  one. A chat with a problem attached never gets this — the model already has that problem's full statement, and
  cross-problem suggestions would be noise, not help.

## What was run

Hermetic tests (`apps/api/tests/test_rag.py`, 8 tests) run against an in-process Qdrant
(`AsyncQdrantClient(location=":memory:")` — a real Qdrant implementation, not a mock, just not over the network) and
a deterministic fake embedder, covering: RAG absent when unconfigured, a clean 503 when configured but unreachable,
indexing on publish and "similar" finding it, removal from the index on unpublish, semantic search ranking by
meaning over keyword overlap, and chat context injection appearing only when no problem is attached. The
`docker-compose.yml` `qdrant` service (`--profile rag`) was not booted in the environment this was built in (no
Docker); it parses as valid YAML. The `qdrant-client` Python package and its `AsyncQdrantClient` were installed and
exercised directly (both in-memory and against the same library's remote-mode code path) as part of writing this
feature.

## Known limitations

* **No backfill job.** As noted in [Setup](#setup), a problem published before RAG was configured (or before an
  edit) is not retroactively indexed — only re-saving it indexes it. At the platform's current problem-set size
  (dozens, not thousands) this is a one-time manual step, not an operational burden; a proper backfill command
  would be the first thing to add if the catalog grows large enough to make it one.
* **In-Python ranking, not SQL-side.** `app.modules.problems.service.recommend_problems` (a related but separate
  feature — see [problems.md](problems.md)) and RAG's own candidate resolution both rank in Python after a DB
  fetch. Fine at current scale; noted here so a future "why is this slow" search lands on the right answer.
* **The `docker-compose.yml` `qdrant` service was never booted** (no Docker in the environment this was built in,
  same as the `sandbox`/`judge`/`ollama` services before it) — see [What was run](#what-was-run).
