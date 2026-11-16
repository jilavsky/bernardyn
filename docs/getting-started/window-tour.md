(window-tour)=
# A tour of the window

Bernardyn is one main window. Data come in on the left, the graph is in the
middle, and its settings are on the right. Everything else (data selector,
annotation editor, output preview) opens from there. The task guides,
starting with the {doc}`../guides/user-guide`, refer to the parts named here.

(window-tour-window)=
## The window

```{figure} img/window-tour/window-tour-01-window.png
:alt: Bernardyn main window: File browser and Data browser on the left, a graph of Unified Fit data and fit in the middle, Graph inspector on the right; numbered circles mark the parts in the legend.
:width: 100%

The main window with the Unified Fit data and fit of `Al_Mg_Si__40C_0min_0498.h5` from
`testData/`. The numbers match the legend below.
```

1. **Menu bar**: File, Edit, Graph, Templates, View and Help. On macOS it is at the top of the
   screen.
2. **Folder tree** of the File browser: click a folder to list its data files.
3. **File list**: the data files of that folder, sorted and filtered by the controls above it.
4. **I(Q) data in the current file**: the scattering curves of the selected file.
5. **Saved pyIrena results in the current file**: each saved fit and the curves it offers.
6. **Add to graph** adds the checked data of the selected files to the active graph;
   **Replace selected series** swaps them in for the series selected in the Data browser.
7. **Data browser — active graph**: the curves of the active graph, in drawing order. The
   buttons above it (**Add data…**, **Open folder…**, **Add from workspace…**) are the other
   ways to bring data in.
8. **Graph tabs**: one tab per graph in the workspace.
9. **Graph**: the active graph as it will be exported. The **Display: W × H px** badge gives
   the on-screen size.
10. **Graph inspector** tabs: **Graph** (graph-wide settings, axes, output size), **Datasets**
    (per-curve style, legend), **Annotations**, and **3D** for 3-D graphs.
11. **Documentation** opens this documentation in your web browser.
12. **Status bar**: messages on the left; the Bernardyn version and the open workspace file
    on the right.

(window-tour-panels)=
## Panels

The **File browser** (2–6), the **Data browser** (7) and the **Graph inspector** (10–11) are
dockable panels. Drag a panel's title to dock it elsewhere, or float it onto another monitor.
On macOS, floating panels stay visible when you switch to another application.

The File browser is closed with its × button and reopened with **View → Open File Browser**
(Ctrl+Shift+B). **View → Reset panel layout** puts every panel back in its default place. The
File browser's folder, favorites, and list settings are remembered on this computer, not stored
in workspace files.

Both primary panels may be floated while working, but open docked at the next
launch so they cannot be stranded outside a changed display arrangement. Use
**View → Open Data Browser**, **View → Open Graph Inspector**, or **View →
Reset panel layout** to recover a closed or misplaced panel immediately.

The inspector's **Datasets** tab provides the same **Show** selector,
per-series controls, visibility checkboxes, and the legend controls for the
active graph. Drag the divider below its dataset list to make that list taller.

How each panel is used is in the {doc}`../guides/user-guide`:
{ref}`importing data <user-guide-import>`, the
{ref}`File browser <user-guide-file-browser>`,
{ref}`choosing what is displayed <user-guide-display>` and
{ref}`editing a graph <user-guide-edit>`.

(window-tour-graph)=
## The graph area

The small **Display: W × H px** badge at the upper-right of the graph shows
the current on-screen canvas size. It changes when the application window is
resized and does not affect exported images. How the on-screen graph relates to the
exported image is explained under {ref}`user-guide-export`.

(window-tour-help)=
## Documentation and version

Use the red **Documentation** button above the right-side **Graph Inspector**
to open this documentation in your web browser.

To find your installed version, choose **About Bernardyn** in the app menu on
macOS or the **Help** menu on Windows/Linux, or read the status bar. From a
terminal, run `bernardyn --version` (`-version`, `--v`, and `-V` also work).
On Windows, use `python -m bernardyn --version` to print it in the terminal.
