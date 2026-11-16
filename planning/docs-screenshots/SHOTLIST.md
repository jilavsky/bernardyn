# Documentation screenshots: shot list

One row per screenshot in `docs/`. The ID is `<page>-<nn>-<what>`, where `<page>` is the page's
file name; the image lives next to the page at `<page dir>/img/<page>/<id>.png`.

- **automated: yes**: `python scripts/make_doc_screenshots.py --only <id>` makes it.
- **automated: no**: needs judgment (real data, a tricky state, an OS dialog). The page holds an
  invisible `% SCREENSHOT <id>: …` comment until the image exists; then replace the comment with
  a `figure` that has alt text and a caption, and set the status to `done`.
- **status**: `done` (image committed and shown), `todo` (placeholder only).

`tests/test_doc_screenshots.py` checks that this list, the pages, the images and the
`@shot` functions agree.

Column order: ID · page · dataset · state to set up · must show · automated? · status.

Regenerate: `python scripts/make_doc_screenshots.py` (in the `bernardyn` conda environment).
Folders shown in the images are the fixed copy `/tmp/bernardyn-docs/testData`, rebuilt on each
run.

## window-tour

| ID | page | dataset | state to set up | must show | automated? | status |
|---|---|---|---|---|---|---|
| window-tour-01-window | window-tour | testData/Al_Mg_Si__40C_0min_0498.h5 | 1800×1000; Unified Fit Data + fit I(Q) added; File browser on testData with the file selected | the whole window, 12 numbered callouts matching the legend | yes | done |

## quickstart

| ID | page | dataset | state to set up | must show | automated? | status |
|---|---|---|---|---|---|---|
| quickstart-01-choose | quickstart | testData/Al_Mg_Si__40C_0min_0498.h5 | File browser on testData, file selected, Unified Fit · Data + fit I(Q) checked | File browser panel only; callouts 1 path, 2 file, 3 result, 4 Add to graph | yes | done |
| quickstart-02-added | quickstart | testData/Al_Mg_Si__40C_0min_0498.h5 | after Add to graph | data and fit in the graph and the Data browser | yes | done |
| quickstart-03-styled | quickstart | testData/Al_Mg_Si__40C_0min_0498.h5 | title "Al-Mg-Si alloy, 40 °C", Show top and right axes | Graph tab with callouts 1 title, 2 box axes, 3 tabs | yes | done |
| quickstart-04-datasets | quickstart | testData/Al_Mg_Si__40C_0min_0498.h5 | as 03, then data symbol size 3, fit line width 3, fit row selected | Datasets tab; callouts 1 tab, 2 list, 3 line width, 4 symbol size | yes | done |
| quickstart-05-preview | quickstart | testData/Al_Mg_Si__40C_0min_0498.h5 | as 04, Preview output… at 900×700 | the output preview window with the finished figure | yes | done |

## user-guide

| ID | page | dataset | state to set up | must show | automated? | status |
|---|---|---|---|---|---|---|
| user-guide-01-data-selector | user-guide | testData/ (folder), Al_Mg_Si__40C_0min_0498.h5 | data selector dialog on the folder, 1100×620; sample selected; first I(Q) data and Unified Fit · Data + fit checked | file list, both lists, Add selected; callouts 1–4 | yes | done |
| user-guide-02-preview | user-guide | Al_Mg_Si__40C_0min_0498.h5, Rh1_0085.h5 | graph with the Al-Mg-Si I(Q); File browser on Rh1_0085.h5, its I(Q) checked, Preview in graph on | the grey dashed preview curve, not in legend or Data browser; callouts 1 checkbox, 2 curve | yes | done |
| user-guide-03-distribution | user-guide | Al_Mg_Si__40C_0min_0498.h5 | import Size Distribution · Volume distribution | the new graph tab with the distribution on linear axes (cropped to tabs + plot) | yes | done |
| user-guide-04-power-law-dialog | user-guide | Al_Mg_Si__40C_0min_0498.h5 | I(Q) in a log-log graph; Annotations → Power-law slope… | the annotation dialog, Type Power Law, P = 4 | yes | done |
| user-guide-05-power-law-graph | user-guide | Al_Mg_Si__40C_0min_0498.h5 | as 04, after OK | the graph with the "slope −4" guide (cropped) | yes | done |
| user-guide-06-waterfall | user-guide | the three USAXS files in testData | New 3D waterfall, curves added, 3D tab open | a 3-D waterfall and the 3D tab; the offscreen Qt platform has no OpenGL context, so Bernardyn shows its 2-D fallback (checked 2026-11-16); take it on a real display | no | todo |

## workflow

| ID | page | dataset | state to set up | must show | automated? | status |
|---|---|---|---|---|---|---|
| workflow-01-file-menu | workflow | none | new window; File menu opened | the whole File menu (macOS shortcut glyphs when made on a Mac) | yes | done |
