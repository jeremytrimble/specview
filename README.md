
To build with pyinstaller, run the following from the root directory of this repo:

```
uv sync --group build --group dev
uv pip install -e .
uv run pyinstaller --clean specview.spec
```

pyinstaller builds only tested on Linux so far.

