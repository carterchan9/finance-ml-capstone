# Finance ML Engineer Capstone Roadmap

Oct 9, 2026 · @Carter

## How to read this

This roadmap describes a finance ML system built in six progressive stages. Each stage builds upon the previous stage's output, so by stage 6 you are hardening a system you have built and understand, rather than assembling unrelated components.

What defines this roadmap:

- **One domain, one repo.** Everything lives inside a strategy validation and live decay monitoring system for independent quant traders and small funds.
- **Stages feed each other.** Stage 1's features, splits and baseline become the benchmark for stage 2, the model behind stage 3's API, and the training job inside stage 4.
- **Every stage ends with a checkpoint.** You move on only when you can explain the stage out loud without Claude Code open.
- **Stage 5 carries its own evaluation** with a small hand-labeled test set, a naive baseline and confidence intervals, so the LLM layer is measured rather than assumed.
- **Time-series validation is built into stage 1**, because walk-forward splits and leakage are central to finance ML.

Design details (stage contracts, data model, locked decisions, tech stack, repository and docs layout) live in the system SDD (Capstone System SDD.md); this document is the outline.

## The system

The system takes a strategy's return history and answers two questions: how credible is this backtest before money goes in, and is live performance drifting away from it afterwards. Stages 1 to 4 build the credibility model and the monitor, stage 5 explains their output, and stage 6 hardens all of it.

```
Market Data
    ↓
Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5
    ↑                                         ↓
    └───────────────────── Stage 6 ────────────────────┘
```
(Wraparound visualization: Stage 6 encompasses/monitors the entire process)

In words: market data feeds stage 1, each stage feeds the next from stage 1 through stage 5, and stage 6 wraps all of them.

The repository layout, including the docs folder, is defined in the system SDD at docs/01-system-sdd.md.

## Before stage 1: Setup

Setup gets your tools, repository and workflow running so stage 1 can start, and it is where you learn the terminal and GitHub basics by using them.

- **Terminal basics.** Learn only `pwd`, `ls`, `cd`, `mkdir`, `cat`, `mv` and `rm` first, and ask Claude to explain any command before you run it.
- **Tools.** Install Python 3.11 or later, Git and Claude Code, create a GitHub account, and set your git name and email.
- **Repository.** Create the repository on GitHub, clone it, and create a virtual environment.
- **Skeleton.** Create the folder layout from the system SDD, including `docs/`, and add a first `CLAUDE.md` using the starter below, and add a .gitignore that excludes data/ and .venv/.
- **First workflow loop.** Make a branch, commit a small change, push it, open a pull request, and merge it.
- **Done when you can explain:** what each command you ran did, why you use a virtual environment, and how a branch and a pull request work.

**CLAUDE.md starter**

Claude Code reads this file at the start of every session. Update the current stage as you go.

```text
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
```

## Stage 1: Tabular and time-series pipeline

Stage 1 builds the data foundation and the baseline every later stage is measured against: a pipeline that predicts how much a strategy's performance decays out of sample, validated only with time-ordered splits.

- **Input:** public daily price data, plus a generator that produces a large population of simple rule-based strategies (rule families, tickers and parameter grids are fixed in the system SDD and the stage 1 SDD). Each strategy gets an in-sample period and a later out-of-sample period.
- **Build:** cleaning and storage in SQL tables; features from the in-sample returns (Sharpe, drawdown, turnover, number of parameter combinations tried); a decay label from the out-of-sample period; model selection with walk-forward validation and purging between train and test windows.
- **Baselines:** naive references (zero decay and mean decay), a regression on in-sample Sharpe alone, and a ridge regression on all features. Gradient-boosted trees must beat both on the same splits to count.
- **Outputs:** a versioned feature table, a trained baseline model, fixed split definitions that every later stage reuses, and a written evaluation of tradeoffs.
- **Why this stage first:** generating thousands of strategies and keeping the winners is exactly the selection bias the product exists to detect, so you meet the core problem hands-on.
- **Done when you can explain:** why random k-fold leaks future information here, how purging works, and how to reproduce one reported metric from scratch.

## Stage 2: Deep learning sequence model

Stage 2 trains a PyTorch model on the raw return series from stage 1 and tests honestly whether it beats the stage 1 baseline on the identical splits. Losing to gradient-boosted trees on small tabular data is a legitimate, reportable result.

- **Input:** stage 1's strategy population, split definitions and baseline scores.
- **Build:** one architecture only (a 1D CNN, GRU or small transformer over the return sequence), a hand-written training loop with a validation loop, early stopping, and checkpointing. Log every run in Weights & Biases.
- **Experiments:** compare architectures and hyperparameters against the stage 1 baseline, always on the same time-ordered splits, with several random seeds so one lucky run isn't reported.
- **Outputs:** a trained model with an experiment table, learning curves, and a short written comparison of deep learning versus the stage 1 baseline, including cost and training time.
- **Done when you can explain:** every part of the training loop, why the loss curves look the way they do, and when you would choose the simpler model.

Use Claude Code's Learning output style here, so you write the loop's core pieces yourself.

## Stage 3: Serving layer

Stage 3 turns the best stage 1 or stage 2 model into a live service: submit a strategy's returns and get back a validation report as JSON.

- **Input:** the best trained model from stages 1 and 2, with its feature code and split metadata.
- **Build:** a FastAPI service with a validation endpoint that takes a return series, computes the same features as training, and returns decay-risk scores alongside the baseline's score. Package it in Docker and deploy to AWS or GCP.
- **Model versioning:** store each model file with metadata (training data window, split definition, metrics) so any report can be traced to the exact model that produced it.
- **Monitoring:** latency, error rate, and input drift on the submitted return series compared with the training distribution.
- **Outputs:** a deployed endpoint, a container image, a simple dashboard, and a note on cost and failure modes.
- **Done when you can explain:** the full request path from upload to response, why training and serving must share feature code, and what each monitored metric would tell you if it moved.

## Stage 4: Scheduled ingestion, retraining and decay monitoring

Stage 4 makes the system run on its own: new data arrives on a schedule, live strategy performance is compared with what the backtest promised, and models retrain when they should. This is the live decay monitoring half of the product.

- **Input:** the stage 3 service and model registry, plus a feed of new prices and strategy returns.
- **Build:** an orchestrated pipeline in Airflow or Dagster that ingests data, recomputes features, runs statistical drift checks of live results against backtest expectations, retrains on a schedule, and promotes a new model only if it beats the current one on held-out walk-forward splits.
- **Reliability:** every step must be idempotent, retry on failure, and write results to the model registry only after validation passes.
- **Outputs:** a scheduled pipeline, a decay alert for each monitored strategy, a retraining log, and a record of every promotion decision.
- **Done when you can explain:** what happens if the job dies halfway through and is re-run, why promotion is gated, and how a drift alert differs from normal variance.

## Stage 5: RAG explanation layer

Stage 5 adds a retrieval-augmented layer that answers "why was this strategy flagged?" in plain language, grounded in the strategy's own validation report and the methodology documentation. Before building it, write the one-sentence justification: if you cannot say what question it answers that the report cannot, shrink it to the smallest version.

- **Input:** stage 3 reports, stage 4 decay alerts, and a document corpus (methodology notes, and optionally company filings for context).
- **Build:** chunking, embeddings, a vector database, retrieval, and a versioned prompt that must cite the report section or document each claim comes from.
- **Evaluation:** a small evaluation built inside this stage, with hand-built ground truth, a naive baseline (for example, always returning the first retrieved chunk), grounding checks for unsupported claims, and confidence intervals on every reported accuracy.
- **Outputs:** a question-answering endpoint added to the stage 3 API, an evaluation report, and a list of failure examples.
- **Done when you can explain:** how chunk size changed retrieval quality, how you measured grounding, and where the layer still makes things up.

## Stage 6: Production hardening and interview walkthrough

Stage 6 adds no new features. It makes the system you already built reliable, tested and explainable end to end, which is what you present in interviews.

- **Input:** the whole system from stages 1 to 5.
- **Build:** CI/CD (tests, linting, image build and deploy on every merge), unit and integration tests, load testing of the API under stress, end-to-end monitoring across the service and the scheduled pipeline, and a runbook for the failures you actually saw.
- **Optional stretch:** a small distributed or multi-GPU training run, only if the earlier stages are solid.
- **Outputs:** a passing CI pipeline, a load test report, a system diagram, a failure-mode list, and a 20-minute walkthrough script covering the problem, data, validation design, models, serving, monitoring, failures, and what you would do with more time.
- **Done when you can explain:** any stage's design decisions and tradeoffs from memory, and answer "what breaks first under load, and how do you know?"

## Definition of done

The capstone is complete when all of the following conditions are met:

- Every stage's checkpoint has been passed, and the system SDD (Capstone System SDD.md) matches what was actually built.
- The validation API is deployed and serves reports from the best model, scored against the naive baseline on the stage 1 splits, with results reported honestly regardless of whether the model outperforms the baseline.
- The scheduled pipeline runs unattended, detects performance decay, and retrains models with gated promotion (only promoting if the new model outperforms the current one).
- The explanation layer (stage 5) has a measured evaluation report with confidence intervals and documented failure examples.
- Continuous Integration passes on every code merge, and a load test report exists for the API.
- The repository README and docs folder enable a stranger to understand, build, and run the system.
- You have delivered the 20-minute system walkthrough aloud to another person at least once, including discussion of failures encountered and potential improvements.

## Parallel tracks and known gaps

These run alongside the six stages. None of them are built into the system.

**Parallel tracks**

- **Coding interview prep.** Ongoing from now, ramping up before interview cycles.
- **ML system design study.** Reading and practice, for example Chip Huyen's *Designing Machine Learning Systems*.
- **A/B testing and experimentation.** Course or reading, since it is hard to practice solo without real traffic.

**Known gaps, closed with courses rather than extra projects**

- Time-series forecasting models beyond validation (stage 1 covers walk-forward splits and leakage, not forecasting methods)
- Unsupervised learning, including anomaly detection (stage 4's drift checks touch it lightly)
- SQL depth and big-data tooling such as Spark (stage 1 uses SQL tables, but not at scale)
- Recommender systems
- Fine-tuning LLMs (LoRA, instruction tuning); stage 5 teaches using LLMs, not training them
- Reinforcement learning, optional unless you target RL-heavy teams

## Working rules

The system is designed holistically but built incrementally, one stage at a time. No stage begins until the previous stage's checkpoint has been passed.

1. **Branch per feature:** Use one git branch and one pull request for each meaningful component of a stage. Review your own pull request before merging.
2. **Plan before coding:** Enter plan mode, read the stage proposal, and push back on any aspects you cannot explain.
3. **Build small, then explain:** After implementing each code chunk, explain it in your own words. Use the Learning output style for stages 1 and 2, then switch to Explanatory once you're fluent.
4. **Test continuously:** Write tests for every metric and feature function as you develop them. Attempt to write the first test yourself before generating additional tests.
5. **Checkpoint to advance:** Treat each stage's "done when you can explain" requirements as advancement gates, not mere suggestions.
6. **Maintain current documentation:** Keep the stage SDD, build prompt, build log, experiment tracker (for training stages), interview notes, system diagram, and walkthrough up to date. Update these documents at the end of each stage as specified in the system SDD.
7. **Maintain CLAUDE.md:** Keep the repository's CLAUDE.md file current with the project goal, folder layout, your skill level, and the core rules: explain decisions, prefer simple code, and always add tests.
