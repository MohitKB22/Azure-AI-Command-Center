# Contributing

## Before you start

```bash
./scripts/dev.sh setup
make check        # confirm a clean baseline before you change anything
```

If `make check` fails on a fresh clone, fix that first — do not build on a red
baseline.

## Workflow

1. Branch from `main`: `feature/<short-name>` or `fix/<short-name>`.
2. Make the change, with tests.
3. Run `make check` — lint, types, tests and build, the same gate CI runs.
4. Open a pull request describing what changed and *why*.

## Pull request expectations

**Required**

- [ ] `make check` passes locally
- [ ] New behaviour has tests: success, permission denied, validation failure
- [ ] Mutations write an audit entry
- [ ] Schema changes ship with a migration, verified up → down → up
- [ ] No secret, key or connection string added anywhere, including tests
- [ ] Documentation updated when behaviour or configuration changed

**Reviewers will push back on**

- A route without a `require_permission` dependency
- A mutation with no audit record
- Business logic in a route handler instead of a service
- A provider imported directly instead of through `registry.py`
- Tests that assert only status codes and never behaviour
- Claims in documentation that are not backed by a passing test

## Code standards

**Python**

- ruff clean, line length 100, type hints on public functions
- Raise typed errors (`NotFoundError`, `ValidationError`, …); never build an
  error response by hand in a route
- Comments explain *why*. If a comment restates the code, delete it
- Never use `eval`, `exec`, or string-built SQL

**TypeScript**

- Strict mode; no `any` in domain types
- Every list page handles loading, empty and error states — an unhandled empty
  state is an incomplete feature
- Server state in TanStack Query; only session state in Zustand
- Labelled inputs, keyboard-reachable actions, visible focus

## Honesty rules

This project makes explicit claims about what is real and what is not. Preserve
them:

1. **Never fabricate data.** If a metric cannot be measured, report
   `not_configured` and zero. Do not synthesise a plausible number.
2. **Never fabricate a citation.** An answer without a supporting retrieved
   passage must say so.
3. **Never overstate a guardrail.** They are heuristics. Say so wherever a user
   might assume otherwise.
4. **Never claim verification you did not perform.** BUILD_REPORT.md distinguishes
   verified locally, verified with mocks, and requires Azure. Keep it accurate.

A pull request that makes the product look better by blurring one of these will
be rejected even if the code is otherwise good.

## Adding a dependency

Justify it in the pull request: what it does, why the standard library or an
existing dependency is insufficient, its maintenance status, and its licence.
Small, well-maintained and widely used beats clever.

## Commit messages

```
<area>: <imperative summary>

Why the change was needed. What alternative was rejected and why.
```

Example:

```
rag: drop signed hashing from the local embedding

Signed hashing cancels collisions in expectation but produced negative
cosine scores for short queries, which pushed the correct document out
of the top-K. Unsigned weights with a 768-dim space fixed the ranking
for every seeded evaluation question.
```
