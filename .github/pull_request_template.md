## Summary

- What changed?
- Why is it needed?

## Change governance

- Classification: `S0 | S1 | S2`
- Feature Spec: `F-NNNN | N/A - reason`
- ADR: `ADR-NNNN | N/A - reason`
- Plan: `PLAN-F-NNNN | N/A - one coherent S1 change`

## Validation

- [ ] Relevant unit, contract, integration, recovery, and security tests
- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run pyright`
- [ ] `uv run pytest`
- [ ] `uv run python scripts/check_docs.py`
- [ ] `uv run python scripts/check_governance.py`
- [ ] `npm run build --prefix=site` or `N/A - site unaffected`

## Documentation impact

- Engineering `docs/`: `<path | N/A - reason>`
- Site beginner learning path: `<path | N/A - reason>`
- Site developer documentation: `<path | N/A - reason>`
- Site current status or milestone summary: `<path | N/A - reason>`
- Generated reference: `<path | N/A - reason>`

- [ ] Every surface above has either an updated path or a concrete `N/A` reason
- [ ] Content distinguishes concepts, accepted design, implemented behavior, and plans
- [ ] Changed prose was read in context; terms are introduced through concrete behavior rather than mechanical replacement
- [ ] External references use primary sources and do not imply BearAgent already supports their capabilities
