# threatgraph

[![lint](https://github.com/GabDestal/threatgraph/actions/workflows/lint.yml/badge.svg)](https://github.com/GabDestal/threatgraph/actions/workflows/lint.yml)
[![test](https://github.com/GabDestal/threatgraph/actions/workflows/test.yml/badge.svg)](https://github.com/GabDestal/threatgraph/actions/workflows/test.yml)

A knowledge graph for cyber threat intelligence (CTI).

## Layout

```
app/            Python package (application code)
scripts/        One-off and maintenance scripts
tests/          pytest suite
demo.ipynb      Walkthrough notebook
.env.example    Template for local settings
```

## Getting started

Requires Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
make install
cp .env.example .env
```

## Development

```bash
make lint       # pylint
make test       # pytest + coverage (fails under 80%)
make coverage   # HTML report in htmlcov/
```

CI runs the same checks on every push to `main` and on every pull request:

- `lint.yml`: pylint
- `test.yml`: pytest with coverage

## Contributing

`main` is protected, so every change lands through a pull request that passes both checks.

Commit messages use a type prefix:

- `feat:` new functionality
- `fix:` bug fixes
- `docs:` documentation only
