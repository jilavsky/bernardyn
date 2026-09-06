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

The inspector's **Datasets** tab provides per-series controls and visibility
checkboxes.

- Click a row to edit its style, legend label, visible Q range, multiplier,
  and offset.
- Use **Shift-click** to select a contiguous block of rows.
- Use **Command-click** on macOS or **Ctrl-click** on Windows/Linux to add or
  remove individual rows from the selection.
- Right-click a selected group and choose **Check selected** or **Uncheck
  selected** to show or hide the whole selection.

## Edit a graph

Use the **Graph** tab in the right-side inspector for graph-wide settings.

- Choose 2-D, 3-D waterfall, or 3-D surface rendering.
- Set axis labels, logarithmic axes, automatic or fixed ranges, grid lines,
  axis colour, and width.
- Enable **Show top and right axes** under **Box axes** to draw a boxed 2-D
  plot. The added axes carry tick marks but no duplicate numeric labels.
- Leave **Show minor tick labels** off for dense log plots. Major labels and
  all tick marks remain visible. Enable it only when there is enough room for
  minor labels.
- Tick labels always use the plotted data values; Bernardyn does not apply a
  hidden SI-prefix multiplier to a log axis.
- Enable and place the legend; set its frame, column count, and font size.

Graphs keep their own configuration, so editing one graph does not alter
another graph tab unless you deliberately apply a graph template.

## Add and refine annotations

Open the **Annotations** tab and use **Add**, **Edit**, or **Delete**. Text,
arrows, horizontal rules, and vertical rules use plotted data coordinates.

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

Use the export actions for images (PNG/JPEG/SVG), displayed data (CSV/Igor
ITX), or canonical datasets (Igor H5XP). These exports serve different
purposes and do not replace a Bernardyn workspace package.

For format details, see [Data flow and file formats](data-flow-and-formats.md).
