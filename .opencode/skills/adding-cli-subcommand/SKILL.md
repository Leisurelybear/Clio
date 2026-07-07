---
name: adding-cli-subcommand
description: Use when adding or changing a Clio CLI command, argparse subparser, command dispatch branch, IO argument behavior, or user-facing CLI documentation.
---

# Adding a CLI Subcommand

## Workflow

1. Edit `clio/main.py`; root `main.py` is only a thin entry point.
2. Add a parser with `sub.add_parser(...)`.
3. Reuse existing shared argument helpers such as `_add_io_args()` when available.
4. Add a dispatch branch matching the subcommand name.
5. Load config using the same project inference rules as nearby commands.
6. Keep user-facing CLI text in Chinese.
7. Update `README.md`, `README.en.md`, and `docs/cli-reference.md` when the command is user-visible.
8. Add or update `clio/tests/test_main.py` and task-specific tests.

## Verification

```bash
python -m pytest clio/tests/test_main.py -q
python main.py --help
python main.py check
```

## Common Mistakes

- Editing root `main.py` instead of `clio/main.py`.
- Not reusing shared `-i`/`-o` handling.
- Creating a new `skip_existing` config field; reuse `analyze.skip_existing`.
- Forgetting English commit/docs naming while CLI prompts remain Chinese.
