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
