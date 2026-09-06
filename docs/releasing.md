# Releasing Bernardyn to PyPI

Bernardyn publishes from a GitHub Release through PyPI **Trusted Publishing**.
No PyPI API token is stored in this repository or in GitHub Secrets.

The release workflow is [`.github/workflows/release.yml`](../.github/workflows/release.yml).
It runs the Linux release tests and lint, builds both the source distribution
and wheel, validates their metadata, then uploads the tested artifacts to PyPI.

## One-time setup for the first beta

Do these steps after the release workflow is merged into the repository's
default branch (`main`). The trusted-publisher configuration must name the
exact workflow file, `release.yml`.

1. Confirm the name is available at [PyPI](https://pypi.org/). A PyPI project
   name is actually claimed only by its first successful upload; a pending
   trusted publisher alone does not reserve it.
2. On GitHub, open **Settings → Environments → New environment**, name it
   `pypi`, and add yourself as a required reviewer. This makes each publish
   wait for your approval.
3. Sign in to PyPI. If `bernardyn` does not exist yet, use PyPI's
   **Publishing → Add a new pending publisher**. Select GitHub Actions and
   enter:

   | Field | Value |
   |---|---|
   | PyPI project name | `bernardyn` |
   | Owner | `jilavsky` |
   | Repository | `bernardyn` |
   | Workflow | `release.yml` |
   | Environment | `pypi` |

   If the project already exists under your PyPI account, instead open that
   project’s **Manage → Publishing** page and add the same GitHub publisher.
4. Merge the release workflow and the desired package version to `main`.
5. Create and publish the GitHub release/tag `v0.0.1b2` from that exact `main`
   commit. Publishing the GitHub Release starts the workflow automatically.
6. In **Actions**, open “Publish Bernardyn to PyPI”, approve the `pypi`
   environment when GitHub requests it, and wait for the PyPI job to finish.
7. Verify the new release at `https://pypi.org/project/bernardyn/`, then test
   it in a new environment on a separate computer:

   ```bash
   python -m venv bernardyn-test
   source bernardyn-test/bin/activate        # Windows: bernardyn-test\\Scripts\\activate
   python -m pip install --upgrade pip
   python -m pip install bernardyn==0.0.1b2
   bernardyn-doctor
   bernardyn
   ```

## Every later release

1. Change the version consistently in `pyproject.toml`,
   `bernardyn/__init__.py`, `bernardyn/io/container.py`, `recipe/meta.yaml`,
   the schema status line, and `changelog.md`.
2. Run `pytest`, `ruff check bernardyn tests`, `python -m build`, and
   `python -m twine check dist/*` locally.
3. Merge to `main`, create the matching `v<version>` GitHub Release, and
   publish it. Approve the protected `pypi` environment.

PyPI does not allow replacing an already uploaded version. If a release needs
correction, bump the version (for example, `0.0.1b2`) and release that instead.

## Security model

The `publish` job alone receives `id-token: write`. PyPI exchanges that
short-lived GitHub OIDC identity for a temporary upload token. Keep
`release.yml` protected: anyone able to alter a trusted publishing workflow
can change what gets published.
