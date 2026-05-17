# Making a `specview` release.

## Update source files:
1. Pick a PEP-440-compliant version string.
2. Set the `__version__` string at the top of `version.py`
3. Set the `version` in `pyproject.toml`.

## Test build:
1. Run the tests for good measure: `uv run poe test`
2. Make sure pyinstaller build works (at least locally): `uv run --group build --group dev poe build`

## Finalize
1. Commit the updated files, which should include at least.
2. Tag the commit containing those updates (e.g. `git tag -a v1.2.3`).
3. Push.