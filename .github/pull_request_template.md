## Summary

- What changed?
- Why is it needed?

## Validation

- [ ] Relevant unit, contract, integration, recovery, and security tests
- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run pyright`
- [ ] `uv run pytest`
- [ ] `uv run python scripts/check_docs.py`
- [ ] `npm run build --prefix=site`

## Documentation synchronization

- [ ] Authoritative engineering `docs/` updated
- [ ] Site beginner learning path updated
- [ ] Site developer documentation updated
- [ ] Site current status or milestone summary updated
- [ ] Content distinguishes concepts, accepted design, implemented behavior, and plans
- [ ] Changed prose was read in context; terms are introduced through concrete behavior rather than mechanical replacement
- [ ] External references use primary sources and do not imply BearAgent already supports their capabilities

Every Feature PR must address all documentation surfaces. If no dedicated page is added, name the existing page or index that was updated.
