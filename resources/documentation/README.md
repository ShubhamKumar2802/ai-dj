# Specs

Spec-driven development: every module gets a spec here *before* it's implemented.
The spec is the single source of truth — code implements the spec, not the other
way around. If reality and the spec diverge (during implementation, code review,
or later maintenance), update the spec first, then the code.

Add sub-folders per component/layer as they're built (e.g. `ingestion/`,
`planning/`, `render/`) — no fixed structure is imposed up front.
