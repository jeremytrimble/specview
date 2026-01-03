
To build with pyinstaller, run the following from the root directory of this repo:

```
uv sync --group build --group dev
uv run pyinstaller --clean specview.spec
```

or just

```
uv run --group build --group dev poe build
```

pyinstaller builds only tested on Linux so far.

