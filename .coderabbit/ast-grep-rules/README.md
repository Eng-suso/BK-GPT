# CodeRabbit ast-grep rules

Deterministic AST checks for the anti-patterns in `backend/CODE_QUALITY.md`.
Loaded via `tools.ast-grep.rule_dirs` in `.coderabbit.yaml`. Same output on
every PR — this is the deterministic layer, not the LLM's judgement.

| Rule | Catches |
|------|---------|
| `python-bare-except` | `except:` with no exception type |
| `python-broad-except-fake-success` | `except Exception` returning `None`/`[]`/`{}`/`False` |
| `python-unbounded-while-true` | `while True:` with no `break`/`return`/`raise` |

## Verify a rule locally

```bash
# one-off, no install
uvx ast-grep scan --rule .coderabbit/ast-grep-rules/python-bare-except.yml backend/
```

## Add a rule

One rule per file. Keep `severity: warning` unless the pattern has zero false
positives. Test against `backend/` before committing — a noisy rule trains
people to ignore CodeRabbit.
