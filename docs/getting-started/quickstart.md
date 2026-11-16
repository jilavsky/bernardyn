(quickstart)=
# Quickstart: a first figure

A first figure in about ten minutes: a USAXS curve and its saved pyIrena Unified Fit, with a
title, box axes and a visible fit line, exported as a PNG. The parts of the window used here
are named in {doc}`window-tour`.

(quickstart-data)=
## The example file

The example is `Al_Mg_Si__40C_0min_0498.h5` from the
[`testData/` folder](https://github.com/jilavsky/Bernardyn/tree/main/testData) of the
Bernardyn repository: USAXS data of an Al-Mg-Si alloy with a saved pyIrena Unified Fit and Size
Distribution. Download the folder (or clone the repository), or use any file of your own that
holds a saved pyIrena fit.

% CHECK(Jan): testData/ is not installed with the package (pip/conda); is pointing users at
% the GitHub folder the intended way to get the example files?

(quickstart-open)=
## 1. Open the file

Start Bernardyn (`bernardyn` in a terminal, see {doc}`installation`). The first time, it opens a
new, unsaved workspace with one empty graph tab. Later it reopens the workspace you last saved;
choose **File → New workspace** to start empty.

```{figure} img/quickstart/quickstart-01-choose.png
:alt: File browser panel showing the testData folder, the file Al_Mg_Si__40C_0min_0498.h5 selected, and "Unified Fit · Data + fit I(Q)" checked in the saved pyIrena results list.
:width: 360px

The File browser after steps 1–3. The numbers match the steps below.
```

In the **File browser** at the left:

1. Type or paste the path of the `testData` folder into the path field and press Enter (or
   click your way to it in the folder tree).
2. Click `Al_Mg_Si__40C_0min_0498.h5` in the file list. The two lists below it show what the
   file holds: its **I(Q) data** and its **Saved pyIrena results**.
3. Check **Unified Fit · Data + fit I(Q)** under **Saved pyIrena results**. This brings the
   measured data that the fit used together with the fit itself.
4. Press **Add to graph**.

(quickstart-added)=
## 2. The data and the fit are in the graph

```{figure} img/quickstart/quickstart-02-added.png
:alt: Main window after Add to graph: the Data browser lists the Unified Fit data and fit, and the graph shows the data as blue symbols with the fit line underneath.
:width: 100%

After **Add to graph**: the data and the fit in the active graph, listed in the Data browser.
```

The **Data browser**, next to the File browser, lists the two curves. Both have the same colour, because
they come from the same file: the data as symbols and the fit as a solid line. With the
default symbol size the fit is hard to see under the data; step 4 fixes that.

(quickstart-style)=
## 3. Title and axes

```{figure} img/quickstart/quickstart-03-styled.png
:alt: Graph inspector, Graph tab, with the title set to "Al-Mg-Si alloy, 40 °C" and "Show top and right axes" checked; the graph shows the new title and a boxed frame.
:width: 100%

The **Graph** tab of the Graph inspector (3) with a title (1) and box axes (2).
```

In the **Graph inspector**, on the **Graph** tab:

1. Type a title, for example `Al-Mg-Si alloy, 40 °C`, and press Enter.
2. Check **Show top and right axes** to draw a boxed plot.

(quickstart-datasets)=
## 4. Make the fit visible

```{figure} img/quickstart/quickstart-04-datasets.png
:alt: Graph inspector, Datasets tab, with the fit curve selected and its line width set to 3; the graph shows smaller data symbols and a visible fit line.
:width: 100%

The **Datasets** tab (1): select a curve in the list (2), then change its line width (3) or
symbol size (4).
```

Open the **Datasets** tab. Select the **Unified Fit data** row and set the symbol **Size** to
3; then select the **Unified Fit fit** row and set the line **Width** to 3. Press Enter after
each value, or use the arrows.

(quickstart-export)=
## 5. Check and export the image

```{figure} img/quickstart/quickstart-05-preview.png
:alt: Output preview window showing the finished figure at 1950 × 1350 px with title, boxed log-log axes, data symbols, fit line and legend.
:width: 80%

**Preview output…** shows the exact exported image: 6.5 × 4.5 in at 300 dpi, 1950 × 1350 px.
```

Press **Preview output…** at the bottom of the **Graph** tab (or choose it in the File or Graph
menu) to see the image exactly as it will be exported. **Output (in)** and **Output DPI** on the
**Graph** tab set its size; fonts are true points at that size.

Then choose **File → Export image…** (Ctrl+E), give a name ending in `.png`, and save. JPEG and
SVG work the same way.

(quickstart-next)=
## Next steps

- Keep the editable figure, with its data embedded, as a workspace package: **File → Save
  workspace package as…** ({doc}`../guides/workflow`).
- Add more files, residuals or size distributions, and compare samples: {doc}`../guides/user-guide`.
- Make the same figure from a script: {doc}`../guides/headless-recipes`.
