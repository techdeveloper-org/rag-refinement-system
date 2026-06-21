# Contributing to RAG Refinement System

Thank you for taking the time to contribute! This guide covers everything you need to open a great issue or pull request.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Quality Gates](#quality-gates)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to uphold it.

---

## Reporting Bugs

1. Search [existing issues](https://github.com/techdeveloper-org/rag-refinement-system/issues) first to avoid duplicates.
2. Open a new issue using the **Bug Report** template.
3. Include: Python / Node version, OS, steps to reproduce, expected behaviour, actual behaviour, and any relevant logs.

**Security vulnerabilities** — do **not** open a public issue. Email [techdeveloper28@outlook.com](mailto:techdeveloper28@outlook.com) with the details.

---

## Suggesting Features

1. Search [existing issues](https://github.com/techdeveloper-org/rag-refinement-system/issues) for similar proposals.
2. Open a new issue using the **Feature Request** template.
3. Explain the problem you are solving, the proposed solution, and any alternatives you considered.

---

## Development Setup

### Backend

```bash
git clone https://github.com/techdeveloper-org/rag-refinement-system.git
cd rag-refinement-system

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install ".[dev]"

cp .env.example .env           # fill in provider keys
docker compose up -d postgres qdrant
uvicorn backend.app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Making Changes

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b fix/my-fix        # bug fix
   git checkout -b feat/my-feature   # new feature
   ```

2. **Write code** following the standards below.

3. **Add or update tests.** The suite must stay at 100% statement and branch coverage. Every new function/class needs a docstring.

4. **Run the full quality gate locally** before pushing (see [Quality Gates](#quality-gates)).

5. **Push** your branch and open a pull request against `main`.

### Code standards

- **Python:** `ruff` (line length 100, all E/W/I/UP/B rules) + `mypy` strict mode.
- **Docstrings:** Google-style on every public function, class, and module. No inline explanatory comments — put the *why* in the docstring.
- **Naming:** snake_case for variables/functions, PascalCase for classes, UPPER_SNAKE_CASE for module-level constants.
- **Error handling:** Catch specific exceptions; always log with `exc_info=True` before re-raising; never swallow exceptions silently.
- **Security:** No hardcoded secrets. Validate all external input at system boundaries. Use parameterised queries.

---

## Quality Gates

CI runs on every push and PR. All gates **hard-block** merge:

| Gate | Command | Requirement |
|------|---------|-------------|
| Lint | `ruff check backend ingestion tests` | 0 violations |
| Type-check | `mypy backend ingestion router db` | 0 errors |
| Tests | `pytest -q --cov=backend --cov=ingestion --cov=router --cov=db --cov-fail-under=80` | all pass, ≥ 80% coverage (suite currently holds 100%) |
| SAST | `bandit -c pyproject.toml -r backend ingestion router db` | 0 findings |
| SCA | `pip-audit` | 0 known vulnerabilities |
| Secrets | `detect-secrets` baseline diff | 0 new secrets |
| Frontend security | `npm audit --omit=dev --audit-level=low` | 0 vulnerabilities |

Run everything locally with:

```bash
make lint type test      # backend
cd frontend && npm run test && npm audit --omit=dev
```

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

<optional body — explain the WHY, not the WHAT>
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `security`

Examples:
```
feat(router): add Cohere reranking support
fix(api): guard against empty document_ids list before routing
docs(readme): add Docker Compose quickstart
```

One logical change per commit. Do not mix bug fixes with refactoring.

---

## Pull Request Process

1. Fill in the pull request template completely.
2. Ensure all CI checks pass.
3. Request a review from a maintainer.
4. Address review comments promptly.
5. A maintainer will merge once approved and all checks are green.

**By submitting a pull request you confirm that your contribution is your original work and that you agree to license it under the Apache-2.0 License.**
