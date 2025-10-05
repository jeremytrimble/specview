# Building Specview

This document describes how to build Specview as a standalone executable using PyInstaller.

## Automated Build (GitHub Actions)

The repository includes a GitHub Actions workflow that automatically builds Specview for Linux, Windows, and macOS on every push to the main branch and for pull requests.

### Workflow Details

The build workflow (`.github/workflows/build.yml`) performs the following steps:

1. Sets up Python 3.11
2. Installs required dependencies (including Qt libraries on Linux)
3. Installs the project dependencies using `uv`
4. Builds the executable using PyInstaller
5. Uploads the built artifacts for each platform

### Accessing Build Artifacts

After a successful workflow run:

1. Go to the Actions tab in the GitHub repository
2. Click on the latest "Build" workflow run
3. Scroll down to the "Artifacts" section
4. Download the artifact for your platform:
   - `specview-linux` - Linux executable
   - `specview-windows` - Windows executable (.exe)
   - `specview-macos` - macOS executable

## Manual Build

### Prerequisites

- Python 3.11 or later
- Qt5 libraries (on Linux)
- `uv` package manager (or `pip`)

### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/jeremytrimble/specview.git
   cd specview
   ```

2. Install dependencies:
   
   Using `uv`:
   ```bash
   uv venv
   uv pip install -e .
   uv pip install pyinstaller
   ```
   
   Or using `pip`:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   pip install pyinstaller
   ```

3. Build the executable:
   ```bash
   pyinstaller specview.spec
   ```

4. Find the built executable in the `dist/` directory:
   - Linux/macOS: `dist/specview`
   - Windows: `dist/specview.exe`

### Platform-Specific Notes

#### Linux

Install Qt5 development libraries:
```bash
sudo apt-get update
sudo apt-get install -y qt5-qmake qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools libqt5gui5
```

#### Windows

No additional dependencies required beyond Python.

#### macOS

No additional dependencies required beyond Python.

## PyInstaller Configuration

The build is configured using the `specview.spec` file in the repository root. This file defines:

- Entry point: `src/specview/main.py`
- Hidden imports for all required dependencies
- Single-file executable output
- GUI mode (no console window)

### Including Assets in the Bundle

To include additional files (like icons, images, or data files) in the PyInstaller bundle:

1. Edit the `specview.spec` file
2. Add entries to the `datas` parameter in the `Analysis` section:

   ```python
   datas=[
       ('path/to/asset/file.png', 'destination/folder'),
       ('path/to/data/directory', 'data'),
   ],
   ```

   The format is: `('source_path', 'destination_in_bundle')`

3. Access the bundled files in your code using PyInstaller's runtime path:

   ```python
   import sys
   import os
   
   def resource_path(relative_path):
       """ Get absolute path to resource, works for dev and for PyInstaller """
       if hasattr(sys, '_MEIPASS'):
           # PyInstaller creates a temp folder and stores path in _MEIPASS
           base_path = sys._MEIPASS
       else:
           base_path = os.path.abspath(".")
       
       return os.path.join(base_path, relative_path)
   
   # Usage
   icon_path = resource_path('assets/icon.png')
   ```

### Hidden Imports

The spec file already includes all necessary hidden imports for Specview. If you add new dependencies, you may need to add them to the `hiddenimports` list:

```python
hiddenimports=[
    'PyQt5',
    'pyqtgraph',
    'numpy',
    'scipy',
    'sigmf',
    'pandas',
    # Add new imports here
],
```

## Troubleshooting

### Missing Dependencies

If the built executable fails with import errors, check if the missing module is in the `hiddenimports` list in `specview.spec`.

### Large Executable Size

The single-file executable includes all dependencies. To reduce size:

- Remove unnecessary dependencies from the project
- Use PyInstaller's `--exclude-module` option for modules not used at runtime
- Disable UPX compression if it causes issues: set `upx=False` in the spec file

### Platform-Specific Issues

- **Linux**: Ensure all Qt libraries are installed and available
- **Windows**: Some antivirus software may flag PyInstaller executables as suspicious
- **macOS**: You may need to sign the application for distribution

## Development Workflow

For development, you don't need to build an executable. Simply run the application directly:

```bash
python src/specview/main.py [options]
```

Or using `uv`:

```bash
uv run python src/specview/main.py [options]
```
