# Specs

Spec-driven development: every module gets a spec here *before* it's implemented.
The spec is the single source of truth — code implements the spec, not the other
way around. If reality and the spec diverge (during implementation, code review,
or later maintenance), update the spec first, then the code.

A `write-spec` skill (`.claude/skills/write-spec/SKILL.md`) operationalizes
everything below — invoke it (or let it trigger) when drafting, amending, or
versioning a spec, rather than re-deriving this convention from scratch each time.

## Naming & storage

```
resources/documentation/<layer>/<module>/spec.md
```

- `<layer>` matches the pipeline layer (`ingestion`, `planning`, `render`, `common`,
  ...) — added as needed, no fixed set imposed up front.
- `<module>` matches the eventual `src/<layer>/<module>/` package name **exactly**.
  The spec tree, the `src/` tree, and the `tests/` tree are three parallel trees keyed
  on the same path (`tests/README.md` already states the `src/` ↔ `tests/` half of
  this — this extends the same rule one tree over rather than inventing a second one).
- The file is always named `spec.md`, never `<module>_spec.md` — the directory
  already disambiguates it, and this leaves room to bundle assets beside it (example
  prompts, fixture data) the way a skill bundles `references/`/`assets/`.
- **Pin the file layout inside the spec itself.** A good spec names every file it
  expects to exist under `src/` and `tests/` before any of them are written, so
  implementation has zero ambiguity to guess at.

**Precedent / worked example:** `resources/documentation/common/llm_service/spec.md`.

## Amendment vs. new version

A spec changes over time. Which kind of change it is determines how to make it:

| | Amendment | New version |
|---|---|---|
| **What changed** | Rationale, defaults, internal detail, an added clarification | The public contract: a signature, a schema field, a file path, an invariant |
| **Does code already implementing the old spec still comply?** | Yes | No |
| **How to make the change** | Edit `spec.md` in place; append a dated one-line entry to a `## Amendments` section at the bottom (create that section on the first amendment — don't scaffold it empty upfront) | Move the current `spec.md` to `archive/spec-v{N}.md`; write the new content to `spec.md`; add a header line, `**v{N+1}** — supersedes v{N}, see archive/spec-v{N}.md` |

The versioning phrasing mirrors what `ai-dj-design-v3.md` already does for its own
v1→v2→v3 history — reuse that convention rather than inventing a new one. A fresh
spec with no history carries no version header at all; the marker only earns its
place once there's something to disambiguate from.

## Lifecycle

1. **Propose** — a module needs a spec: a new build-order item, or a design gap
   found during implementation, code review, or later maintenance.
2. **Draft in Plan Mode** — write `spec.md` at its pinned path, including the file
   layout it expects (above).
3. **Get approval** — the spec is reviewed and approved *before* any code exists.
4. **Implement** strictly to the approved spec.
5. **If reality forces a deviation** — during implementation, review, or later
   maintenance — stop, apply the amendment-vs-new-version rule above, update the
   spec, get it approved, *then* resume code. Never let code and spec drift silently.

Add sub-folders per component/layer as they're built (e.g. `ingestion/`,
`planning/`, `render/`) — no fixed structure is imposed up front.
