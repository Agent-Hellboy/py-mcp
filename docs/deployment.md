# Docs Deployment

This repository now ships a GitHub Pages workflow so the documentation can be browsed as a hosted site instead of raw markdown files.

## Published URL

The site is configured to publish at:

- `https://agent-hellboy.github.io/py-mcp/`

## Local Preview

Install the docs dependencies and run MkDocs locally:

```bash
pip install -e '.[docs]'
mkdocs serve
```

The local preview runs at `http://127.0.0.1:8000/` by default.

## CI Workflow

The deployment flow lives in `.github/workflows/docs.yml`.

It does three things:

- builds the site on pushes and pull requests that touch `docs/**`, `mkdocs.yml`, or the docs workflow itself
- comments on pull requests with the target GitHub Pages URL
- deploys the built site to GitHub Pages on pushes to `main` or `master`

## GitHub Setup

For the first deployment, the repository Pages source should be set to `GitHub Actions` in the GitHub Pages settings.

After that, a push to the default branch is enough to publish the latest docs.

## What To Edit

- add or update pages under `docs/`
- update navigation in `mkdocs.yml`
- keep the hosted links in `README.md` aligned with the pages you expose
