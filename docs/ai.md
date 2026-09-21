# SahuCodeX AI — design (build phase 5, not yet implemented)

> Status: **planned.** The `ollama` service exists in `docker-compose.yml` behind the `ai` profile and the environment
> variables are reserved in `.env.example`, but no AI endpoint is implemented yet.

## Principles

* **Local and open-source first.** Default provider is [Ollama](https://ollama.com); no paid API is ever required. Paid
  providers, if added, are optional plug-ins behind the same interface.
* **No hardcoded model.** `OLLAMA_MODEL` names whatever model you have pulled. `AI_PROVIDER` and `OLLAMA_BASE_URL` are
  configuration, not code.
* **Fails cleanly.** If Ollama is down or the model is missing the API returns a structured error and the rest of the
  platform keeps working.
* **The judge is authoritative.** SahuCodeX AI is an assistant, not a source of truth. If the AI says "this should pass"
  and SahuJudge says `WRONG_ANSWER`, the verdict stands. The UI keeps four things visibly distinct: *suggestion*,
  *explanation*, *review*, and *actual execution result*, and AI review never claims code is correct.
* **No fake responses.** Every AI output comes from the model; there are no canned answers standing in for it.

## Setup (once phase 5 lands)

```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull <model-name>
# then in .env:  OLLAMA_MODEL=<model-name>
```

Or install Ollama on the host and keep `OLLAMA_BASE_URL=http://localhost:11434`.

## Planned features

* **Progressive hints** — three levels, given the problem, language, current code and previous hints; teach, never dump
  the solution.
* **Explain code** — what it does, algorithm, key logic, time/space complexity, potential issues.
* **Review** — structured sections: correctness, bugs, edge cases, time and space complexity, readability, optimisation.
* **Debugger** — code + error + input + expected/actual output → likely causes and debugging steps.
* **Chat** — streaming (Server-Sent Events), Markdown and code blocks with copy, conversation history with rename/delete,
  optional context (problem, code, language, compiler error, judge result).
* **Optional RAG** over an algorithm/data-structure knowledge base in Qdrant or Chroma. Strictly optional; the core
  platform and every feature above work without it.

## Abuse and cost controls

Authentication required · per-user rate limits (Redis, env-configurable) · prompt-length and response-length caps ·
request timeout · usage rows recorded per request (`user_id`, feature, model, conversation, timestamp). Prompts are
treated as untrusted input: model output is rendered as inert Markdown, never executed and never trusted to make
authorization decisions.
