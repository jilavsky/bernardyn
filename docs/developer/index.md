# Developer guide

Releasing and extending the package.

User-facing features and behaviour changes must be documented in the relevant
page here and recorded in the root `CHANGELOG.md` in the same change.

```{toctree}
:maxdepth: 1

releasing
extending
```

(developer-screenshots)=
## Documentation screenshots

The images in the user pages are made by `scripts/make_doc_screenshots.py`, from scratch copies
of `testData/`, with your Bernardyn settings untouched:

```sh
python scripts/make_doc_screenshots.py                  # all shots, about 40 s
python scripts/make_doc_screenshots.py --only quickstart  # one page
python scripts/make_doc_screenshots.py --list
```

`planning/docs-screenshots/SHOTLIST.md` lists every shot, including those still to be taken by
hand, and `tests/test_doc_screenshots.py` keeps the pages, the list and the images in step.
Fonts come from the operating system: regenerate a page's shots on one machine.
