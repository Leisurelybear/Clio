#!/usr/bin/env python3
"""Thin wrapper -- delegate to the clio package."""

from clio.main import main

if __name__ == "__main__":
    raise SystemExit(main())
