# Bernardyn user guide

Bernardyn is a desktop workbench for preparing publication-oriented 1-D
scattering and diffraction graphs. A workspace can hold several graph tabs;
each graph keeps its own displayed datasets, transform, styling, axes, legend,
annotations, and (for 3-D views) camera settings.

Use the red **Documentation** button above the right-side **Graph Inspector**
to open this local documentation folder. In a PyPI installation, it opens the
GitHub documentation instead.

To find your installed version, choose **About Bernardyn** in the app menu on
macOS or the **Help** menu on Windows/Linux, or read the status bar. From a
terminal, run `bernardyn --version` (`-version`, `--v`, and `-V` also work).
On Windows, use `python -m bernardyn --version` to print it in the terminal.

## Import data

The top of the left **Data browser** holds the ways to add data to the active
graph; the same commands are in the **File** menu:

- **Add data…** opens the data selector for one or more chosen files.
- **Open folder…** opens the data selector for a whole folder, which can be
  sorted and filtered.
- **Add from workspace…** reuses anything already loaded, including results.
- Drag files or folders from the system file browser onto the **Data browser**
  list, even when that list is empty; this opens the data selector too.

In the data selector, select files on the left. The right side shows what the
current file contains, in two lists of equal standing:

- **I(Q) data**: the scattering curves in the file.
- **Saved pyIrena results**: each saved fit and the curves it offers, such as
  "Unified Fit · Data + fit I(Q)" or "Size Distribution · Volume distribution".

Check what you want in either list, or both, and press **Add selected**. The
checked choices apply to every selected file: I(Q) choices to files with the
same layout, and a checked result kind to every file that stores it. Both
kinds of choice are remembered for next time.

The selector recognises HDF5/NXcanSAS (`.h5`, `.hdf5`, `.hdf`, `.nxs`) and
two-to-four-column text data (`.dat`, `.txt`, `.csv`). For HDF5 files, choose
the desired 1-D datasets. Bernardyn remembers the chosen dataset layout and
can reuse that choice for later files with the same structure.

For a standard NXcanSAS path such as
`/entry/PP15_25C_1min/sasdata`, the curve and default legend label is
`PP15_25C_1min`. This keeps labels compact and distinguishes several samples
stored in one HDF5 file. When no sample group can be identified, Bernardyn
uses the filename.

### File browser: pick, check, and correct without dialogs

The **File browser** panel, at the left of the Data browser, stays open while
you work. Use it when data come from several folders, or when you want to try
one file after another.

- **Find the folder.** Click a folder in the tree, type or paste a path into
  the path field and press Enter, or use **Back** and **Up**. **☆** adds the
  folder to Favorites; **Places** lists Favorites, recent folders, and Home.
  Refresh (F5) re-reads a folder that is still being written to.
- **Choose files and data.** Sort and filter the file list as in the data
  selector, and check the I(Q) data or saved results below it. The panel and
  the data selector share what they learn about file layouts.
- **Include subfolders** also lists the files of the folders directly inside
  the current one (one level only), shown as `subfolder/file`. Point at a
  sample folder that holds `…_usaxs`, `…_saxs`, and `…_waxs` folders, type
  the sample (say `CC1`) in the filter, press **Select all visible**, then
  **Add to graph**: every technique arrives in one step. The filter matches
  both `subfolder/file` and the bare file name. **Group by folder** keeps each
  folder's files together; otherwise all files are sorted together. Subfolders
  are listed in the background, so the list can grow for a moment on a
  network drive. A folder with more than 50 subfolders lists none of them.
- **Add to graph** (or double-click, or Enter) adds the checked data of the
  selected files to the active graph. The panel stays where it was.
- **Replace selected series** (Ctrl+R) swaps the data of the series selected
  in the Data browser for the checked I(Q) data of the selected files, one
  file per series. Each series keeps its color, symbols, multiplier, offset,
  Q range, and place in the legend; the legend text becomes the new sample's
  name. Replace is one Undo step.
- **Drag** files from the list onto a graph tab to add them to that graph, or
  onto the Data browser list.

Newly added series are selected in the Data browser, so a wrong file is
fixed with: **↓** to the next file, then **Replace selected series**. Repeat
until it is the right one.

**Preview in graph** shows the current file as a grey dashed curve in the
active graph while you move through the list (it appears after a short
pause, so moving quickly loads only the file you stop on). Nothing changes
until you press **Add to graph** or **Replace selected series**: the preview
is not a series, is not in the legend, is not saved, cannot be undone, and
never appears in exported or printed images. It uses the I(Q) data checked
for that file's layout and the graph's current view; when the view needs a
value the file does not store (for example I₀ and Rg for the dimensionless
Kratky view), the panel says so instead. Axes left on automatic range widen
to show the preview and return afterwards; fixed ranges are kept. Preview
works in 2D graphs.

The panel is an ordinary panel: drag its title to dock it elsewhere, or float
it onto another monitor. On macOS, floating panels stay visible when you
switch to another application. Close it with its × button; reopen it with
**View → Open File Browser** (Ctrl+Shift+B). **View → Reset panel layout**
puts it back. Its folder, favorites, and list settings are remembered on
this computer, not stored in workspace files.

## Choose what is displayed

The left **Data browser — active graph** controls the order in which curves are
drawn. Its **Show** selector can narrow the list to ordinary SAS data or the
measured, fit, component, residual, and distribution roles of saved pyIrena
results. Filtering only changes the list; it
does not hide or remove a curve from the graph. Drag rows within the unfiltered
list to change drawing order, or select rows and use **Remove selected from
graph** to hide them from that graph. Removing a row does not delete the
canonical dataset from the workspace.
Use **Add from workspace…** to tick one or more loaded catalog datasets,
including imported result curves, and place them in the active graph without
reading their source files again. Each entry names its kind (for example
"Unified Fit residuals"); in a view other than General I(Q) only scattering
curves are offered. These
changes, along with removal and reordering, can be undone and redone.
**Edit → Remove unused data from workspace…** drops loaded datasets that no
graph uses, after listing them; source files are never changed and the step
can be undone.

Right-click selected rows in the active-graph list to **Copy selected to…** or
**Move selected to…** an existing graph, or choose **Create new 2D graph** in
the destination dialog. The underlying canonical datasets remain shared in the
workspace. Each target graph applies its own selected view, so moving a curve
to an I(Q) graph restores I(Q) rather than retaining a transform intended for
the source graph. All transfers can be undone or redone.

Saved **Unified Fit**, **Size Distribution**, **Modeling**, **Simple Fits**,
**WAXS Peak Fit**, and **Carbon fitting** results appear in the selector's
**Saved pyIrena results** list. Bernardyn uses pyIrena's HDF5 schema to find
them and its result readers to load them. Files without the checked results
are named after the import.

**Data + fit I(Q)** adds the measured data, total fit, and components to the
current graph, which must use the General I(Q) view. With several files, each
file keeps one colour: data as symbols, the fit as a solid line, and components
dashed. Modeling saves no copy of the data it fitted, so Bernardyn adds the
file's primary scattering curve as the measured data when the file has one.
WAXS includes its background and individual peaks; Carbon fitting includes its
grain Porod, micropore, and diffraction components. WAXS curves use linear axes
when added to an empty graph.

Every other choice creates **one new graph holding that curve from every
file**, so a batch gives a comparison rather than a tab per file. A file keeps
the same colour on each graph. **Residuals** use a linear Y axis; WAXS
residuals also use a linear Q axis. Modeling residuals are available for
files saved by a pyIrena version that stores them. Size Distribution offers
volume, number, surface, and cumulative distributions, and Modeling offers the
volume and number distribution of each population. Bernardyn uses the stored
radius centres and values; it does not infer bin widths or recalculate
distributions.

Number distributions are shown in Irena units, cm⁻³·Å⁻¹ (cumulative number in
cm⁻³). Files from older pyIrena versions stored them per Å³ of sample; those
values are converted (×10²⁴) on reading, as pyIrena does. The whole import is
one Undo step.

Use **Graph → New 2D graph** or Ctrl/Cmd+Shift+N to create a 2-D graph quickly.

The inspector's **Datasets** tab provides the same **Show** selector,
per-series controls, visibility checkboxes, and the legend controls for the
active graph. Drag the divider below its dataset list to make that list taller.

Both primary panels may be floated while working, but open docked at the next
launch so they cannot be stranded outside a changed display arrangement. Use
**View → Open Data Browser**, **View → Open Graph Inspector**, or **View →
Reset panel layout** to recover a closed or misplaced panel immediately.

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
- In the per-dataset **Show errors** controls, choose intensity uncertainty
  (**Y**) and Q resolution (**X**) independently. Enable **Caps** to draw
  conventional end caps on the selected error bars; **Size** controls their
  length as a percentage of the relevant axis span (0.5% by default).
- Text files without an uncertainty column get an estimated uncertainty
  (5% of I by default, set in the data selector). Bernardyn records this:
  hovering over a dataset shows whether its uncertainty is measured or
  estimated, the graph lists a warning while estimated error bars are shown,
  and Igor ITX and H5XP exports note it beside the data.

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
- **Canvas (px) → Set** resizes the application so the displayed 2-D canvas
  matches the requested pixel width and height. The display badge confirms the
  actual on-screen size; later window resizing remains available.
- **Reset graph to defaults…** restores graph-wide settings, axes, legend,
  annotations, background, and output settings while keeping the loaded curves
  and their styles. The action can be undone.

Graphs keep their own configuration, so editing one graph does not alter
another graph tab unless you deliberately apply a graph template.
**Graph → Duplicate graph** copies the active graph, with its curves, styles,
and annotations, into a new tab that can then be edited independently.

The **Templates** menu saves, applies, renames, and deletes graph templates.
The template list shows each template's view, output size, and number of
series styles.

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

For log-log SAXS graphs, **Power-law slope…** adds a one-decade guide with
`I = B q^-P`. Enter the positive power exponent `P` (the default is 4 for a
Porod guide); Bernardyn chooses `B` to place the guide at the selected centre.
The guide is labelled, can be dragged to a new position, and remains editable
or deletable in the annotation list.

## Save and export

Use **File → Save workspace package as…** for an editable archive of all graph
tabs and the shared dataset catalog. Use **Save graph package…** to archive
only the active graph. Both use the native `.bernardyn.h5` format and embed the
data needed to reopen the graph without its original source files.

Bernardyn remembers the last successfully opened or saved **workspace** package
and reopens it at the next application launch. Saving a single graph does not
replace that remembered workspace. If the remembered file was moved, deleted,
or cannot be read, Bernardyn starts with a new empty workspace instead.

The **File → Recent workspaces** menu keeps the ten most recently opened or
saved workspace packages. Choose an entry to open it in a separate Bernardyn
window, or to bring its existing window to the front. **File → New window**
opens a blank workspace, and **Open workspace in new window…** opens a chosen
package alongside the current one.

Several different workspace packages can be edited at once. Bernardyn locks a
package for the lifetime of its editing window, including across separate app
processes, so the same package cannot be silently edited and saved from two
places. If a package is already open, switch to that window or use **Save As**
to create a distinct editable copy.

The lock does not expire while its owner may still be running, even on a disk
shared between computers. If Bernardyn quit unexpectedly on another computer,
the next attempt to open the package says which program, process and computer
hold the lock and offers **Break lock**. Break it only when that program is no
longer running; otherwise whichever copy is saved last overwrites the other.

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
export. Both contain the values as plotted, after the view transform and any
point removed for a logarithmic axis. CSV files begin with `#` lines giving
the graph title, axis labels with units, and each series' view and units;
read them with `pandas.read_csv(path, comment="#")` or skip lines starting
with `#`. ITX waves carry their data units.

For format details, see [Data flow and file formats](data-flow-and-formats.md).
