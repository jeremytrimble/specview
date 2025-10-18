
To build with pyinstaller, run the following from the root directory of this repo:

```
uv sync --group build --group dev
uv run pyinstaller --clean specview.spec
```

pyinstaller builds only tested on Linux so far.

## Using Specview

### Flexible Plot Display

Specview provides a flexible dockable window interface that allows you to customize the display to suit your workflow:

#### Dockable/Detachable Windows

All plot views (Time View, Spectrum Analyzer, Waterfall, Annotations, and Captures) are in dockable windows that can be:
- **Rearranged** by dragging the title bar to a different position in the main window
- **Detached** by dragging the title bar outside the main window, creating a separate floating window (ideal for multi-monitor setups)
- **Re-docked** by dragging a floating window back into the main window
- **Hidden/Shown** using the View menu or by closing the dock widget's close button

#### View Menu Controls

The **View** menu provides the following options:
- **Time View** - Toggle visibility of the time domain plot
- **Spectrum Analyzer** - Toggle visibility of the frequency domain plot
- **Waterfall** - Toggle visibility of the waterfall/spectrogram plot
- **Annotations** - Toggle visibility of the annotations table
- **Captures** - Toggle visibility of the captures panel
- **Reset Layout** - Restore all dock widgets to their default positions and make them all visible

#### Layout Memory

Your custom layout is automatically saved when you close the application and restored when you reopen it. This includes:
- Window size and position
- Dock widget positions (which area they're in, tab order, etc.)
- Dock widget states (visible/hidden, docked/floating)

Use **View → Reset Layout** if you want to restore the default layout at any time.

