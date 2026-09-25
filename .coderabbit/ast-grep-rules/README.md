# CodeRabbit ast-grep rules

Deterministic AST checks for the anti-patterns in `backend/CODE_QUALITY.md`.
Loaded via `tools.ast-grep.rule_dirs` in `.coderabbit.yaml`. Same output on
every PR — this is the deterministic layer, not the LLM's judgement.

| Rule | Catches |
|------|---------|
| `python-bare-except` | `except:` with no exception type |
| `python-broad-except-fake-success` | `except Exception` returning `None`/`[]`/`{}`/`False` |
| `python-unbounded-while-true` | `while True:` with no `break`/`return`/`raise` |
| `python-llm-client-outside-gateway` | A provider client built outside `backend/llm/` — spend with no ledger row |

## Verify a rule locally

```bash
# one-off, no install — the package is `ast-grep-cli`, the executable `ast-grep`
uvx --from ast-grep-cli ast-grep scan --rule .coderabbit/ast-grep-rules/python-bare-except.yml backend/
```

`uvx ast-grep` does not resolve: there is no `ast-grep` package on PyPI.

## Add a rule

One rule per file. Keep `severity: warning` unless the pattern has zero false
positives. Test against `backend/` before committing — a noisy rule trains
people to ignore CodeRabbit.

`severity: error` is for invariants, not style: a violation is a defect the
codebase does not currently have. Before promoting a rule to `error`, check it
both ways — green on `backend/`, and red on a scratch file that violates it on
purpose. A rule that is green because it matches nothing is worse than no rule.
