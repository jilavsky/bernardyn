# 1.0 release checklist (plan step 8)

The automated suite covers the code paths. This pass checks what tests cannot:
that real beamline data look right and that the workflow feels right to the
person who will use it. Budget about an hour on macOS, plus about 20 minutes on
Windows.

Use your own recent data, not `testData/`. Work on **copies** in a scratch
folder, because scenario E deletes the sources.

Prepare:

```bash
conda activate bernardyn
bernardyn-doctor          # must say "Core runtime: ready"
bernardyn --version       # 0.0.1b7 until the version bump below
```

Gather in a scratch folder, e.g. `~/bernardyn-rc-check/`:
- 5–10 reduced USAXS/SAXS NXcanSAS files from one series (temperature or time).
- One file that has both slit-smeared and desmeared data.
- One 2- or 3-column text file.
- Files with saved pyIrena results: Unified Fit and Size Distribution (ideally
  several samples), plus any Modeling, Simple Fits, or WAXS you have.

For each scenario, note **pass**, or what went wrong. A screenshot helps
most.

## A. Plain I(Q): no extra decisions

1. **File → Open folder…**, select the series, sort by temperature or
   time, and add it.
2. Expected:
   - log–log I(Q).
   - Axes `q [Å⁻¹]` and `Intensity [cm⁻¹]`.
   - Curves in the selected order, with legend names you recognise.
   - No dialog asking about anything you didn't choose.
3. Switch the view to Kratky, then Porod, then back to General I(Q). The units
   should stay on both axes each time, e.g. `Intensity·q² [cm⁻¹·Å⁻²]`.
4. Add the text file. If it has no error column, hover over it in the dataset
   list: it should say *estimated as 5% of I*. Turn on its error bars; the
   inspector should show a warning.

## B. Data + fit: no manual paths

1. **Add pyIrena results…**, choose one Unified Fit file, then **Data + fit
   I(Q)**.
2. Expected:
   - Measured symbols and a fit line, both in cm⁻¹.
   - The fit is within the data's Q range.
3. Repeat for Size Distribution, and for Modeling/Simple Fits/WAXS if you have
   them.
   - Modeling should now show your measured data too.
   - Simple Fits data and fit should share one axis unit.
   - Modeling saved with the new pyIrena should also offer **Residuals**.
   - WAXS should use linear axes and `arb. units`.

## C. Distributions: correct axes

1. **Add pyIrena results…** on a Size Distribution file, then tick **Volume
   distribution** and **Residuals**.
2. Expected: two new graphs.
   - The volume distribution is labelled `Radius [Å]` and
     `Volume fraction density [vol. fraction·Å⁻¹]`.
   - The residuals use a linear Y axis.
3. Change the line/symbol style. The values must not change; hover over a
   point, or export CSV before and after the change.
4. Compare one peak position and the total volume fraction with what pyIrena
   or Irena reports for the same fit.
5. Import a **Number distribution**, from an older file and from one saved by
   the new pyIrena. Both should read cm⁻³·Å⁻¹ with values of similar size,
   roughly 10¹⁵–10²⁰. A value around 10⁻⁵ means the legacy scaling was missed.

## D. Multi-file batch with one Undo

1. **Add pyIrena results…**, select all the Unified Fit files plus one file
   *without* results, then tick **Data + fit I(Q)** and **Residuals**.
2. Expected:
   - The dialog preview lists the targets and names the skipped file.
   - The data + fit curves land in the current graph, with **one colour per
     sample**, and one new "Unified Fit residuals" graph holds all the samples.
   - Afterwards a message names the skipped file.
3. Press **Undo** once. Everything from this import should disappear.

## E. Save, delete the sources, reopen and edit

1. Arrange a publication-style graph with a title, legend, an annotation and a
   power-law guide. Then **File → Save workspace package as…**.
2. Close Bernardyn and **move the scratch data folder away** (or delete the
   copies).
3. Reopen the workspace. Expected:
   - Every graph is identical, with no warnings.
   - You can still change the view, styles and output size, and export
     PNG/SVG/CSV.
4. **Templates → Save graph template…**, apply it to another graph, and
   **Rename graph template…**.
5. Optional: **Duplicate graph**, then **Edit → Remove unused data from
   workspace…**, then Undo.

## F. Windows (short)

On the Windows beamline PC:
1. `pip install` the release candidate.
2. Run `bernardyn-doctor`.
3. Open a few files, then save, reopen and export PNG.

If the PC shares a disk with the Mac:
1. Open the same workspace on both machines. The second one should name the
   first as the lock owner.
2. Quit the first one normally. The second should now open the workspace
   without **Break lock**.

## G. MCP / Aida (optional for rc1)

Point Aida (or any MCP client) at `bernardyn-mcp`, following
[docs/mcp.md](../docs/mcp.md). Ask for:

> Porod plot of these files.

Expected: a package plus a PNG preview in the output root, with labels in Å⁻¹.

## What to send back

- For each scenario: pass, or a description plus a screenshot.
- For anything numerically suspicious: the source file name, and if possible
  the saved `.bernardyn.h5`.
- Anything that felt like one decision too many. That counts as a finding,
  even if nothing is broken.

## After the pass: cutting 1.0.0rc1

These are done once A–E pass and the findings are fixed:

1. Version `1.0.0rc1` in all of these:
   - `pyproject.toml`
   - `bernardyn/__init__.py`
   - `recipe/meta.yaml`
   - the schema v3 status line
   - `CHANGELOG.md` (rename *Unreleased*)
2. Set `Development Status` to `5 - Production/Stable` only at 1.0.0 final.
3. Push to `main`, let CI pass on all three operating systems, then publish the
   GitHub Release `v1.0.0rc1` (see [docs/releasing.md](../docs/releasing.md)).
4. **For 1.0.0 final:** publish a stable pyIrena 1.2.x first. Then raise the
   floor to it in `pyproject.toml`, `recipe/meta.yaml`, `environment.yml`, and
   `MINIMUM_PYIRENA` in `bernardyn/diagnostics.py`; a test checks that the last
   one matches `pyproject.toml`.
5. pyIrena-side items, which are welcome but not blocking:
   - Release the `8a54ee8` changes (Modeling residuals, number-density
     units). Bernardyn already handles files from both before and after them.
   - Make `read_number_dist` public.
   - Simple Fits `I_model` units should be the data's units, not `arb`.
   - Check why `cumul_num_dist` ends about 30% below ∫N(r)dr.
   - Agree authoritative size-bin edges, if distribution bars are wanted.
