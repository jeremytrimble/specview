
# specview

A desktop GUI application for viewing and annotating [SigMF](https://github.com/sigmf/SigMF) RF signal recordings.

## Features

- **Spectrum analyzer** — FFT-based frequency-domain display with configurable window and averaging
- **Waterfall display** — scrolling time-frequency spectrogram
- **Time-domain view** — raw I/Q sample display
- **Annotation support** — view, edit, and create SigMF annotations interactively
- **Multi-file support** — open and browse multiple recordings at once
- **Captures panel** — navigate between captures within a file

## Installation

### Pre-built binary (Linux)

Download the latest release from the [Releases page](https://github.com/jeremytrimble/specview/releases) and run the `specview` executable directly — no Python required.

### From PyPI

```
pip install specview
```

Requires Python 3.11+ and a working Qt6 environment.

### From source

```
git clone https://github.com/jeremytrimble/specview.git
cd specview
uv sync
uv run specview
```

## Usage

```
specview [file1.sigmf-meta [file2.sigmf-meta ...]]
```

Files can also be opened from the **File** menu after launch.

```
specview --help
```

## Building

See [RELEASING.md](RELEASING.md) for instructions on building wheel and PyInstaller binary releases.

## License

MIT — see [LICENSE](LICENSE).

