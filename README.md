# Specview: A SigMF File Viewer and Annotation Editor

The [SigMF](https://sigmf.org/) ("Signal Metadata Format") is a standard format for exchanging digitally-sampled time-series data with JSON-based metadata.  It is often used for storing real or complex-valued (IQ) time series data in digital signal processing or software-defined radio applications.

Specview is a portable and performant SigMF file viewer and annotation editor.

## Installation:

### Self-Contained single-file exectuable
- Available for Linux, Mac, and Windows.
- Releases page: https://github.com/jeremytrimble/specview/releases

### From PyPI
Install the `specview` package from PyPI using your favorite Python package/tool manager:
- `pip install --user specview`
- `pipx install specview`
- `uv tool install specview`
- `pixi global install --pypi specview`

## Development

To run unit tests:

```
uv run --group build --group dev poe test
```

To build wheel/pyinstaller single-file executables:
```
uv run --group build --group dev poe build
```

## License
Specview is built on top of numerous open-source projects and proudly released under the GNU General Public License.
