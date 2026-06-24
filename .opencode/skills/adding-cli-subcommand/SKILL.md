---
name: adding-cli-subcommand
description: Use when adding a new CLI command, registering a subcommand parser under main.py
---

# Adding a New CLI Subcommand

## Overview

CLI subcommands are registered in `main.py` using `argparse`. Each follows a consistent pattern.

## Implementation

1. In `main.py`, create parser: `p_X = sub.add_parser(...)` with appropriate arguments
2. Add dispatch branch matching the subcommand name
3. Reuse `_add_io_args()` for `-i`/`-o` arguments
4. Use `config.analyze.skip_existing` for skip behavior (consistent with other steps)
5. Update READMEs

## Common Mistakes

- Not reusing `_add_io_args()` — leads to inconsistent CLI interface
- Creating new `skip_existing` config fields — reuse `analyze.skip_existing`
- Forgetting README update — users discover features through CLI docs
