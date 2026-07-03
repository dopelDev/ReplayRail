# Release Procedure

ReplayRail uses Docker as the authoritative local release gate.

## Preconditions

- The package version in `pyproject.toml` is the intended release version.
- `CHANGELOG.md` has an entry for the release.
- The working tree contains only intentional changes.
- PyPI Trusted Publishing is configured for `github.com/dopelDev/ReplayRail` and the `pypi` GitHub Actions environment.

## Local Verification

Run the full gate locally:

```bash
docker compose build test
docker compose run --rm test
docker compose down
```

The test service runs:

```bash
pytest -p no:cacheprovider
ruff check .
ruff format --check .
mypy src/replayrail
python -m build
twine check dist/*
```

## Release Steps

1. Update `pyproject.toml` version.
2. Update `CHANGELOG.md`.
3. Run the Docker release gate.
4. Commit the release changes.
5. Push the commit to GitHub:

```bash
git push github main
```

6. Publish to TestPyPI first.
7. Verify installation from TestPyPI.
8. Tag the release:

```bash
git tag vX.Y.Z
git push github main
git push github vX.Y.Z
```

9. Create a GitHub release for the tag, or run the `Publish to PyPI` workflow manually.
10. Confirm the package is visible on PyPI.

## TestPyPI Dry Run

Configure TestPyPI Trusted Publishing before running the workflow:

- Owner: `dopelDev`
- Repository: `ReplayRail`
- Workflow file: `publish-testpypi.yml`
- Environment: `testpypi`
- Project name: `replayrail`

Run the `Publish to TestPyPI` workflow manually from GitHub Actions.

After it completes, verify installation:

```bash
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  replayrail==X.Y.Z

python -c "from replayrail import ReplayRail, ReplayRailConfig; print('ok')"
```

Use TestPyPI only as a package upload and install smoke test. Do not treat TestPyPI dependency resolution as production-equivalent because dependencies are normally resolved from real PyPI through `--extra-index-url`.

## Notes

- Do not publish from an unverified working tree.
- Do not publish if `twine check dist/*` fails.
- The publish workflow expects PyPI Trusted Publishing. It does not store a PyPI API token in the repository.
