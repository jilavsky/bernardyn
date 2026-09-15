# Bernardyn user guide

Bernardyn is a desktop workbench for preparing publication-oriented 1-D
scattering and diffraction graphs. A workspace can hold several graph tabs;
each graph keeps its own displayed datasets, transform, styling, axes, legend,
annotations, and (for 3-D views) camera settings.

Use the red **Documentation** button above the right-side **Graph Inspector**
to open this local documentation folder. In a PyPI installation, it opens the
GitHub documentation instead.

## Import data

Use one of the following ways to add data to the active graph:

- **File → Open data…** for one or more files.
- **File → Open folder…** to browse supported files in a folder.
- Drag files or folders from the system file browser onto **Datasets in active
  graph** at the left, even when that list is empty.

The selector recognises HDF5/NXcanSAS (`.h5`, `.hdf5`, `.hdf`, `.nxs`) and
two-to-four-column text data (`.dat`, `.txt`, `.csv`). For HDF5 files, choose
the desired 1-D datasets. Bernardyn remembers the chosen dataset layout and
can reuse that choice for later files with the same structure.

For a standard NXcanSAS path such as
`/entry/PP15_25C_1min/sasdata`, the curve and default legend label is
`PP15_25C_1min`. This keeps labels compact and distinguishes several samples
stored in one HDF5 file. When no sample group can be identified, Bernardyn
uses the filename.

## Choose what is displayed

The left dock, **Datasets in active graph**, controls the order in which curves
are drawn. Drag rows within this list to change drawing order, or select rows
and use **Remove selected from graph** to hide them from that graph. Removing a
row does not delete the canonical dataset from the workspace.
Use **Add from workspace…** to place another loaded catalog dataset in the
active graph without reading its source file again. These changes, along with
removal and reordering, can be undone and redone.

The inspector's **Datasets** tab provides per-series controls, visibility
checkboxes, and the legend controls for the active graph.

- Click a row to edit its style, legend label, visible Q range, multiplier,
  and offset.
- Use **Shift-click** to select a contiguous block of rows.
- Use **Command-click** on macOS or **Ctrl-click** on Windows/Linux to add or
  remove individual rows from the selection.
- Right-click a selected group and choose **Check selected** or **Uncheck
  selected** to show or hide the whole selection.
- Use the **Legend** group to show, position, frame, and arrange the legend.
  Its text uses the Graph tab's font family, its color matches the axes, and
  its marker size can be made independent of the plotted markers.
- In the per-dataset **Errors** controls, choose intensity uncertainty (**Show
  Y**) and Q resolution (**Show X**) independently. Enable **Caps** to draw
  conventional end caps on the selected error bars; **Size** controls their
  length as a percentage of the relevant axis span (0.5% by default).

## Edit a graph

Use the **Graph** tab in the right-side inspector for graph-wide settings.

- Choose 2-D, 3-D waterfall, or 3-D surface rendering. Before Bernardyn
  opens a 3-D view, it checks whether Qt can create the necessary OpenGL/GLX
  context. On remote or headless X sessions where that is unavailable,
  Bernardyn remains open and shows a 2-D offset-waterfall fallback instead;
  the status bar explains why and the 3-D graph settings are retained.
- Set axis labels, logarithmic axes, automatic or fixed ranges, grid lines,
  axis colour, and width. Numeric arrow controls redraw while they are used,
  at no more than five updates per second; pressing Enter applies immediately.
- **Autoscale** enables both automatic axes and immediately fits the displayed
  data. Presentation-only choices such as grid, legend, or tick-label settings
  preserve an interactive zoom instead of refitting the graph.
- Enable **Show top and right axes** under **Box axes** to draw a boxed 2-D
  plot. The added axes carry tick marks but no duplicate numeric labels.
- Leave **Show minor tick labels** off for dense log plots. Major labels and
  all tick marks remain visible. Enable it only when there is enough room for
  minor labels.
- Tick labels always use the plotted data values; Bernardyn does not apply a
  hidden SI-prefix multiplier to a log axis.
- Choose whether the background colour applies to the whole canvas or only to
  the interior plot area. The latter leaves a white frame around the axes and
  is available for 2-D graphs.
- **Reset graph to defaults…** restores graph-wide settings, axes, legend,
  annotations, background, and output settings while keeping the loaded curves
  and their styles. The action can be undone.

Graphs keep their own configuration, so editing one graph does not alter
another graph tab unless you deliberately apply a graph template.

## Add and refine annotations

Open the **Annotations** tab and use **Add**, **Edit**, or **Delete**. Text,
arrows, horizontal rules, vertical rules, and boxes use plotted data
coordinates. A box is drawn behind the curves, making it useful for lightly
highlighting a region without obscuring data. Use its two coordinate pairs as
opposite corners and choose a colour with transparency for its fill.

When editing an annotation, change its coordinates or appearance and press
**Update graph**. The dialog remains open while the graph updates, allowing
positioning by repeated adjustment. **OK** saves the final values and closes
the dialog. Each press of **Update graph** is an intentional graph update.

## Save and export

Use **File → Save workspace package as…** for an editable archive of all graph
tabs and the shared dataset catalog. Use **Save graph package…** to archive
only the active graph. Both use the native `.bernardyn.h5` format and embed the
data needed to reopen the graph without its original source files.

Bernardyn remembers the last successfully opened or saved **workspace** package
and reopens it at the next application launch. Saving a single graph does not
replace that remembered workspace. If the remembered file was moved, deleted,
or cannot be read, Bernardyn starts with a new empty workspace instead.

**Copy graph image** (Edit menu or Cmd/Ctrl+C) places a raster graph image on
the system clipboard for pasting into other applications. **File → Print
graph…** opens the system print dialog and prints the same graph image while
preserving its aspect ratio.

**Output (in)** and **Output DPI** control the size and resolution of exported
PNG/JPEG files and the clipboard image. The interactive 2-D graph is fitted to
the available window at the same output aspect ratio; unused space is canvas-
coloured padding. It therefore previews the output shape without trying to
match the output's absolute physical size. SVG remains vector output, but uses
the same requested physical dimensions.

The small **Display: W × H px** badge at the upper-right of the graph shows
the current on-screen canvas size. It changes when the application window is
resized; it is useful for comparing the fitted display with **Canvas (px)**,
but it is not the exported image size.

Use **Preview output…** beside the output controls (or in the File/Graph menu)
to open a separate, exact-pixel raster preview. It is generated only on demand;
the preview window can be closed independently and has its own **Copy image**
and **Print…** buttons.

Use the export actions for images (PNG/JPEG/SVG), displayed data (CSV/Igor
ITX), or canonical datasets (Igor H5XP). These exports serve different
purposes and do not replace a Bernardyn workspace package. CSV and ITX export
the visible curves by default; hide a curve to omit it from a displayed-data
export.

For format details, see [Data flow and file formats](data-flow-and-formats.md).
