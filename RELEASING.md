# Making a `specview` release.

## Update source files:
1. Pick a PEP-440-compliant version string.
2. Set the `__version__` string at the top of `src/specview/version.py`.
3. Set the `version` in `pyproject.toml`.
4. Add a corresponding entry to `CHANGELOG.md`.

## Test build:
1. Run the tests for good measure: `uv run poe test`
2. Make sure pyinstaller build works (at least locally): `uv run --group build --group dev poe build`

The `poe build` task produces both artifacts under `dist/`:
- `specview-<version>-*.whl` — installable Python wheel
- `specview` — self-contained PyInstaller binary (Linux)

## Create a GitHub release:
1. Commit the updated files and create an annotated tag:
   ```
   git tag -a v1.2.3 -m "v1.2.3"
   git push origin v1.2.3
   ```
2. On GitHub, go to **Releases → Draft a new release** and select the tag.
3. Write release notes summarising what changed (copy from `CHANGELOG.md`).
4. Attach the PyInstaller binary (`dist/specview`) and the wheel (`dist/specview-*.whl`) as release assets.
5. Publish the release.

## Upload to PyPI:
```
uv run twine upload dist/specview-*.whl
```
or
```
uv publish dist/specview-*.whl
```
