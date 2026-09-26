# Contributing

## Setup

See README → *Running locally*. `make dev` starts everything in Docker.

## Checks before a PR

```bash
cd backend && ruff check app tests && pytest -q        # needs Postgres(+pgvector) & TEST_DATABASE_URL, or: make test-backend
cd frontend && npm run lint && npm test                 # tsc --noEmit + Vitest
```

## Conventions

- Backend: async SQLAlchemy 2.0, pydantic v2, one domain service per area. Routes stay thin. Use `event_bus.commit(session)` instead of `session.commit()` whenever you emitted world events.
- Schema changes need an Alembic migration (`alembic revision --autogenerate -m "..."`), and `alembic check` must be clean.
- Frontend: strict TypeScript, no `any`. Types in `types/world.ts` mirror `app/schemas/serializers.py`. Use `useApi` / `useWorldEvents` rather than ad-hoc fetch loops.
- Never log or return secrets. Never add a tool that reaches outside the world (see SECURITY.md).

## Adding an action (tool)

1. In `app/agents/actions/tools.py`, create a `Params` model and a `Tool` subclass with `name`, `description`, `params_model`, `energy_cost`, `cooldown_seconds` and `param_hint`. Implement `check()` for permission rules and `run()` through domain services. Return a `ToolResult` (activity, memory, importance).
2. Add it to `ALL_TOOLS`, and optionally add aliases in `registry.py`.
3. Allow it in the rooms where it makes sense (`world/seed_data.py` `allowed_actions`), or mark it `always_allowed`.
4. Optionally teach the offline engine (`llm/simulated.py`) when to choose it.
5. Add tests in `tests/test_permissions.py` or a new file.

## Adding a game

Write a pure rules module (`new_state`, `legal_moves`, `apply_move → (state, label, outcome)`, a policy), wire it into `GameService`, and add a board component in `frontend/features/games`.

## Commit style

Imperative subject line, with a body that explains *why*.
