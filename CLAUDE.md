# Finance ML Engineer Capstone

Goal: a strategy validation and live decay monitoring system, built in six stages, as my ML engineering capstone. Current stage: 1 (pipeline and baseline).

Before changing code, read docs/01-system-sdd.md and the current stage's SDD in docs/stages/. The SDDs are the source of truth. If they are ambiguous or look wrong, ask me. Do not edit anything in docs/ except the current stage's build-log.md and interview-notes.md.

## About me
I am a beginner programmer learning ML engineering by building this. Explain decisions, prefer simple code, and always add tests. Do not write code I am meant to hand-write: leave a TODO(human) and wait.

## Rules
- Follow the system SDD's contracts, data model, locked decisions and tech stack. Do not add libraries without asking.
- No lookahead. Features use data up to the origin date only, labels use data after it only, and splits come only from the splits table.
- Windows, thresholds, tolerances, paths and tickers live in config/*.toml, not in code.
- Fixed random seeds. Record git commit, data version, feature schema version, label version and split id on every run.
- Type hints and a short docstring on every function.
- Git: one branch per milestone, small commits, pull requests, never push to main directly.
- Ask before anything that deletes files, installs packages, or touches files outside this repository.
- No secrets or raw data in git.

## Commands
- Tests: pytest
- Lint and format: ruff check . and ruff format .
- Stage 1 pipeline: python -m src.pipelines.run_stage1 --config config/stage1.toml