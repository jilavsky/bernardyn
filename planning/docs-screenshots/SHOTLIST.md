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

