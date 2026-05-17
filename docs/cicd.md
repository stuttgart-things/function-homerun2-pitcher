# CI/CD

## GitHub Actions Workflows

| Workflow                      | Trigger                                | Description                                                                 |
|-------------------------------|----------------------------------------|-----------------------------------------------------------------------------|
| `build-test.yaml`             | PR / push to main / dispatch           | Ruff lint, pytest, multi-arch xpkg build, PR-tagged push to ghcr           |
| `build-scan-image.yaml`       | PR / push to main / dispatch           | Trivy vulnerability scan of the runtime image (via Dagger)                  |
| `e2e.yaml`                    | PR / push to main / dispatch           | kind + Crossplane v2 + Operations end-to-end test (self-hosted runner)     |
| `lint-repo.yaml`              | PR / push to main                      | commitlint, ruff, yamllint, dockerfilelint, GitHub workflow validation     |
| `release.yaml`                | After `Build & Test` + `Build & Scan` succeed on main, or dispatch | semantic-release → multi-arch xpkg push to ghcr |
| `pages.yaml`                  | After `Release` succeeds, or dispatch  | Deploy MkDocs/TechDocs to GitHub Pages                                     |
| `cleanup-pr-artifacts.yaml`   | PR closed                              | Deletes the per-PR xpkg tag from ghcr                                       |

## Release flow

Releases are automated via [semantic-release](https://semantic-release.gitbook.io/) running inside [`dagger/release`](https://github.com/stuttgart-things/dagger/tree/main/release).

1. Push to `main` triggers `Build & Test` and `Build & Scan Runtime Image`.
2. Both completing successfully triggers `Release`.
3. semantic-release reads commits since the last tag, applies the Angular preset:
    - `feat:` → minor bump
    - `fix:` / `perf:` → patch bump
    - `ci:`, `chore:`, `docs:`, `style:`, `refactor:`, `test:` → no release
4. If a new version is produced:
    - A `chore(release): X.Y.Z [skip ci]` commit is pushed to `main`.
    - A GitHub release + tag `vX.Y.Z` is created with the CHANGELOG diff.
    - Multi-arch (`amd64` + `arm64`) xpkgs are built and pushed as `ghcr.io/stuttgart-things/function-homerun2-pitcher:vX.Y.Z`.
    - The release body is updated with an Artifacts table.

!!! note
    Squash-merging a PR collapses internal commits under the PR title's prefix. Use `fix:` or `feat:` on the PR title so semantic-release picks it up — `ci:` won't trigger a release even if the PR body contains a fix.

## Tasks

Common local tasks via [Taskfile](https://taskfile.dev/):

```sh
task                   # list all tasks
task install           # hatch env create
task test              # pytest (unit)
task fmt               # ruff fmt + lint
task build             # multi-arch xpkgs to dist/
task smoke             # run the runtime image and check the gRPC port
task e2e               # full kind-based e2e
task lint:precommit    # pre-commit run --all-files
task lint:commit       # commitlint against main
```

## Versioning

This repo follows [SemVer](https://semver.org/) via conventional commits:

- Breaking changes: `feat!:` or `BREAKING CHANGE:` footer → major bump
- New features: `feat:` → minor
- Bug fixes: `fix:` → patch
- Everything else → no release
