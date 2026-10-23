# Capstone System SDD

Oct 9, 2026 · @Carter

This is the system-level design for the capstone outlined in the roadmap (Finance ML Engineer Capstone Roadmap.md). It fixes only what must stay stable across stages; each stage gets its own detailed SDD just before it is built.

## Purpose and scope

The system analyzes a strategy's return history to answer two key questions: How likely is its backtested performance to decay out of sample? Is its live performance drifting away from what the backtest promised?

While the system's primary function is to build and demonstrate ML engineering skills in a finance setting, explainability is equally important as model accuracy. Every stage must be understandable and defensible in an interview setting.

**In scope**

- A pipeline that generates a population of strategies from public price data and labels how each decayed out of sample (stage 1)
- A baseline model and a deep learning model that predict decay (stages 1 and 2)
- A served validation API (stage 3)
- A scheduled retraining and live drift pipeline (stage 4)
- A grounded explanation layer with its own small evaluation (stage 5)
- CI/CD, tests, load testing and end-to-end monitoring (stage 6)

**Non-goals**

- No trading, execution, or claims of tradable returns
- No scaling or selling the system; it is a learning and interview artifact
- No intraday, options or multi-asset data in the first version
- No paid or proprietary data
- No LLM fine-tuning or reinforcement learning, and distributed training only as an optional stage 6 stretch

## Stage contracts

Seven interfaces must stay stable across stages, because changing one forces rework in every stage that uses it. The first five are fixed by stage 1 or 2; the last two are provisional until their own stage SDDs.

| Contract | Defined in | Used by | Rule |
| --- | --- | --- | --- |
| Label definition | Stage 1 | Stages 2, 4 | One definition of decay for the whole system. Changing it creates a new label version and makes earlier comparisons invalid. |
| Feature schema | Stage 1 | Stages 2, 3, 4 | One feature module computes features for training and serving. Any change bumps the schema version. |
| Split definitions | Stage 1 | Stages 2, 4 | Walk-forward origins and the purge gap are fixed in stage 1. Later stages reuse them and never define their own. |
| Evaluation protocol | Stage 1 | Stages 2, 4 | Primary metrics and baselines are fixed under the locked decisions. Every model is scored the same way on the stage 1 splits. |
| Model registry entry | Stages 1, 2 | Stages 3, 4 | Records model id, feature schema version, label version, split id, data version, metrics and git commit. |
| Validation API request and response | Stage 3 | Stages 4, 5 | Provisional. Request: dated return series plus metadata. Response: scores, baseline score, model id, warnings. |
| Drift event record | Stage 4 | Stage 5 | Provisional. Strategy id, detection date, test used, test statistic, model id. |

## Data model

Ten tables hold everything the system stores. Start with SQLite and write the schema so it moves to Postgres unchanged if stage 4 needs it.

| Table | Key columns | Written by | Read by |
| --- | --- | --- | --- |
| prices | ticker, date, adjusted close, volume | Stage 1 (stage 4 appends) | Stages 1, 4 |
| strategies | strategy id, family, parameters, ticker | Stage 1 | Stages 1, 2 |
| samples | sample id, strategy id, origin date, in-sample window, out-of-sample window | Stage 1 | Stages 1, 2, 4 |
| features | sample id, feature schema version, feature values | Stage 1 | Stages 2, 3, 4 |
| labels | sample id, label version, out-of-sample Sharpe, decay, decayed flag | Stage 1 | Stages 1, 2, 4 |
| splits | split id, fold, sample id, role (train or test), purge gap | Stage 1 | Stages 1, 2, 4 |
| model\_runs | run id, stage, model type, git commit, data version, split id, parameters, metrics, created at | Stages 1, 2, 4 | Stages 3, 4 |
| model\_registry | model id, run id, status, promoted at | Stages 1, 2, 4 | Stages 3, 4 |
| reports | report id, model id, scores, created at | Stage 3 | Stage 5 |
| drift\_events | event id, strategy id, detected at, test, statistic, model id | Stage 4 | Stage 5 |

Every row of features, labels and model\_runs must be traceable to a data version and a git commit, so any reported number can be reproduced.

## Repository layout

One repository holds all stages, and the layout is fixed now so later stages add files without moving anything. The repository name is a placeholder.

```text
fin-ml-capstone/
  data/                 raw and processed data (kept out of git)
  config/               windows, thresholds, tolerances and paths (stage 1 onward)
  src/
    ingest/             price and returns loaders (stages 1, 4)
    features/           feature code shared by training and serving (stage 1)
    models/             baseline, sequence model, registry (stages 1, 2)
    serving/            FastAPI app (stage 3)
    pipelines/          batch runners and scheduled jobs (stages 1, 4)
    explain/            RAG layer (stage 5)
  tests/                unit and integration tests
  .github/workflows/    CI/CD (stage 6)
  docs/                 see Documentation structure
  CLAUDE.md             project rules for Claude Code
  README.md             what the project is and how to run it
```

## Tech stack

The first version uses this stack, chosen to be common, well documented and easy to learn. Claude Code must not add libraries beyond it without asking.

| Area | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11 or later |  |
| Data and numerics | pandas, numpy, scipy |  |
| Models | scikit-learn: Ridge and HistGradientBoostingRegressor | PyTorch is added in stage 2 |
| Price data | yfinance with auto\_adjust turned on | Adjusted prices handle splits and dividends, not spin-offs |
| Storage | SQLite through the standard library sqlite3, with hand-written SQL and no ORM | One file at data/capstone.db, kept out of git |
| Configuration | TOML files in config/, read with the standard library tomllib | No extra dependency |
| Tests | pytest |  |
| Lint and format | ruff |  |
| Plots | matplotlib | For the evaluation report |
| Dependencies | requirements.txt with pinned versions, installed into the virtual environment | Reproducible installs |
| Entry point | python -m src.pipelines.run\_stage1 --config config/stage1.toml | One runner per stage, placed in src/pipelines/ |

## Decisions to lock before stage 1

These eight choices are expensive to change later because every stage inherits them. Each row was decided on 2026-10-13. If you change one, update the stage 1 SDD to match.

| Decision | Proposed default | Why |
| --- | --- | --- |
| Decay label | Regression target: decay = out-of-sample Sharpe minus in-sample Sharpe. Classification variant: decayed = out-of-sample Sharpe below half of in-sample Sharpe, with the threshold in config. | A difference stays defined when Sharpe is negative or near zero; a ratio does not. |
| Data source | Free daily adjusted prices (for example via yfinance), cached raw with the pull date. | No cost, and caching keeps results reproducible. |
| Universe | A fixed list of 20 liquid ETFs and 30 US large caps, listed below the table, chosen once and recorded. | Keeps scope small. Known limitation to document: survivorship bias, since today's large caps are the ones that survived. |
| Date range | Fixed window: 2008-01-01 through 2025-12-31 (18 years), so every pull uses the same end date. | Gives enough origin dates for several walk-forward folds after the purge gap. |
| Strategy generator | A few rule families (moving-average crossover, momentum, mean reversion), each swept over a parameter grid per ticker. | Produces thousands of samples with known structure and exposes selection bias directly. |
| Window lengths | In-sample and out-of-sample lengths set in config. Starting guess: 3 years in-sample, 1 year out-of-sample. | The out-of-sample length is the label horizon and sets the purge gap. |
| Split scheme | Rolling walk-forward on origin date. Train and test origins are separated by a purge gap at least as long as the out-of-sample window, and samples are grouped by origin date. | Strategies from the same origin share one out-of-sample period, so they are not independent. Grouping and purging prevent leakage. |
| Primary metrics | MAE and Spearman rank correlation between predicted and realized decay, and AUC for the decayed flag. Each is reported next to the baseline's score, with a confidence interval or a spread across folds. | Ranking strategies by decay risk is the product's use case, so a rank metric sits next to an error metric. |

**Universe (decided 2026-10-13)**

- **ETFs (20):** SPY, QQQ, IWM, DIA, EFA, EEM, TLT, IEF, LQD, HYG, GLD, SLV, XLE, XLF, XLK, XLV, XLY, XLP, XLI, XLU
- **US large caps (30):** AAPL, MSFT, AMZN, GOOGL, JPM, JNJ, XOM, WMT, PG, KO, PEP, CVX, LLY, LOW, CSCO, INTC, ORCL, VZ, HD, MCD, DIS, BAC, WFC, CAT, BA, UNH, TXN, NKE, COST, AMGN
- **Excluded on purpose:** companies with major spin-offs inside the window (for example MMM, ABT, IBM, MRK, PFE), because free adjusted prices do not handle spin-offs reliably.
- **History check:** all 50 should have full history across the window. The ingest gap check confirms this, and any failure is swapped for a similar liquid ticker and logged in the change log.

## Known risks and limitations

These are stated up front so they are documented, not discovered later in an interview.

- **Survivorship bias.** A universe of today's large caps and ETFs overstates historical performance and understates failures.
- **Selection bias is part of the design.** Sweeping parameter grids and keeping the winners is the problem being studied, so results apply to this strategy population, not to every real-world strategy.
- **Samples are not independent.** Strategies sharing an origin date share one out-of-sample period, and there are only a limited number of independent origins, so uncertainty is wide. Report confidence intervals and say so.
- **Free data quality.** Free price data can have gaps and adjustment errors. Cache it, spot-check a few series against a second source, and record what you found.
- **No transaction costs in version 1.** Strategy returns ignore costs and slippage, so decay estimates are optimistic.
- **Simple strategy families.** Moving-average, momentum and mean-reversion rules stand in for real strategies and may not behave like them.
- **Small evaluation set in stage 5.** The hand-labeled test set is small, so its results carry wide intervals.

## Cross-cutting rules

These rules apply to every stage and ensure results are reproducible, defensible, and maintain rigor:

- **Reproducibility:** Use fixed random seeds, cache raw data with its pull date, and record the git commit, data version, feature schema version, and split ID for every run.
- **No leakage:** Verify through testing that no feature uses data after its origin date, and that training and test origins are separated by the purge gap.
- **Baselines always:** Report every metric alongside the naive baseline's score on the same splits, including confidence intervals or spread across folds and seeds.
- **Versioning:** Assign version numbers to label definitions, feature schemas, and models; create new versions rather than modifying existing ones when changes occur.
- **Testing:** Write unit tests for every feature and metric function (using test-first approaches when practical), and add integration tests once stage 3 is implemented.
- **Logging:** Record all training runs in the model_runs table; incorporate Weights & Biases tracking from stage 2 onward.
- **Configuration over hardcoding:** Store windows, thresholds, tolerances, and file paths in configuration files rather than hardcoding them in source code.
- **Git workflow:** Use one branch and one pull request per feature, with review before merging. Never store secrets or raw data in the repository.
- **Documentation:** Keep all documents in the repository under docs/ as Markdown files, updating them at the end of each stage as specified in this document.

## Documentation structure

All project documents live in the repository under `docs/` as Markdown, because Claude Code can read them and git versions them; the repository copy is the source of truth. This SDD sits at the top as the living reference.

Current document structure (as implemented):
```
docs/
  Finance ML Engineer Capstone Roadmap.md         # capstone outline (00-roadmap.md equivalent)
  Capstone System SDD.md                          # this document, updated at each stage boundary
  Stage 1 SDD Pipeline and Baseline.md            # stage 1 detailed design
  Stage 1 Build Prompt.md                         # stage 1 build prompt
  # Additional documents would be added here as the project progresses
```

Target structure (for future organization):
```
docs/
  README.md                           # index, reading order, and current stage
  00-roadmap.md                       # capstone outline (rarely changes)
  01-system-sdd.md                    # this document, updated at each stage boundary
  stages/
    stage-1-pipeline/
      sdd.md                          # detailed design, frozen once the stage passes its checkpoint
      build-prompt.md                 # the prompt given to Claude Code for this stage
      build-log.md                    # running journal, decisions, things that confused you
      interview-notes.md              # concepts, likely questions, failure modes, what you would change
      experiments.md                  # training stages only (1, 2, and 4 if it retrains)
    stage-2-deep-learning/
      # (same files as stage-1-pipeline)
    ...                               # one folder per stage
  interview/
    walkthrough.md                    # the 20-minute system walkthrough, drafted a stage at a time
    diagrams/                         # system diagram and per-stage diagrams
```

**Rules**

1. **One home for each fact.** Contracts, the data model and the locked decisions live only in this SDD. Stage SDDs link to them instead of copying them.
2. **Stage SDDs freeze at the checkpoint.** A later change is recorded as a dated amendment at the bottom of that stage SDD, and this SDD is updated if a contract changed.
3. **Build prompts stay short.** Each one points at its stage SDD and `CLAUDE.md`, states the task and acceptance tests, asks for the Learning output style, and says to stop at each checkpoint. The detail belongs in the SDD, not the prompt.
4. **`CLAUDE.md` at the repo root** names the docs folder, the current stage, and the instruction to read this SDD and the current stage SDD before changing code.
5. **Number files and folders** so the reading order is obvious.

The five working documents map onto this layout: the project brief is the stage SDD plus its build prompt, the build log and experiment tracker are per stage, the interview prep pack is each stage's interview notes, and the system diagram and walkthrough live in `interview/`.

**What to update at the end of each stage**

- **Stage contracts and data model**, if the feature schema, label definition, splits or any table changed, with the version bumped.
- **Decisions to lock**, if a proposed default turned out wrong, with a line saying why.
- **Open questions**, ticking off what was resolved and adding what the stage turned up.
- **Later stages table**, if what you learned changes the next stage's scope.
- **Change log**, one line per change.

Purpose, non-goals and cross-cutting rules change only if the project's direction changes or a rule was missing. "SDD updated" is part of every stage's checkpoint, so a stage is not done until this document matches what was built. Batch the updates at the stage boundary, except a contract change that a later stage already depends on.

## Later stages

Only stage 1 gets a detailed SDD now. Each later stage's SDD is written after the previous checkpoint passes, using what that stage taught you.

| Stage | Scope in one line | Detailed SDD written |
| --- | --- | --- |
| 1. Pipeline | Strategy generation, features, decay label, walk-forward validation, baseline model | Drafted; decisions confirmed, ready to build |
| 2. Deep learning | Sequence model compared against the stage 1 baseline on the same splits | After the stage 1 checkpoint |
| 3. Serving | Validation API, Docker, cloud deploy, monitoring | After the stage 2 checkpoint |
| 4. Automation | Scheduled ingestion, live drift checks, retraining, gated promotion | After the stage 3 checkpoint |
| 5. RAG layer | Grounded explanations with their own small evaluation | After the stage 4 checkpoint |
| 6. Hardening | CI/CD, tests, load testing, end-to-end monitoring, interview walkthrough | After the stage 5 checkpoint |

**Standard stage SDD sections**

Every stage SDD uses these sections in this order, so the set stays consistent from stage to stage. A section that does not apply is kept and marked "Not applicable".

1. Goal, scope and deliverables
2. Inherited decisions and stage specifics
3. Design: components and what each reads and writes
4. Data, features or interfaces specific to the stage
5. Validation or evaluation design
6. Models, baselines and metrics, or the stage's equivalent
7. Build plan: milestones, what to hand-write first, acceptance tests
8. Edge cases and risks
9. Success criteria and checkpoint questions
10. Open items and amendments

## Open questions

The first two were decided on 2026-10-13; the rest can wait for their stage's SDD.

- [x] Confirm or change the eight proposed defaults (decided 2026-10-13, see the table)
- [x] Which exact tickers and ETFs make up the universe? (decided 2026-10-13, see the universe list)
- [ ] AWS or GCP for the stage 3 deployment? (decide at the stage 3 SDD)
- [ ] Which sequence architecture for stage 2: 1D CNN, GRU or small transformer? (decide at the stage 2 SDD)
- [ ] Is SQLite enough, or does stage 4 move to Postgres? (decide at the stage 4 SDD)
- [ ] Does the stage 5 corpus include company filings, or only methodology notes and validation reports? (decide at the stage 5 SDD)

## Change log

Add one line here for every change to contracts, decisions or scope, newest first.

| Date | Stage | Change | Why |
| --- | --- | --- | --- |
| 2026-10-13 | Before stage 1 | Added a tech stack section and the standard stage SDD sections; replaced document links with file paths so the docs export cleanly | Claude Code needs the library choices fixed, and every stage SDD should have the same shape |
| 2026-10-13 | Before stage 1 | Locked the eight defaults, fixed the data window at 2008-01-01 to 2025-12-31, and chose the 50-ticker universe | Stage 1 could not start with unconfirmed defaults, and a fixed end date keeps data pulls reproducible |
| 2026-10-09 | Before stage 1 | Added repository layout, evaluation protocol, primary metrics and a risks section; moved the repository layout out of the roadmap | A foundation review found that metrics were unspecified and the layout lived in two places |
| 2026-10-09 | Before stage 1 | Added the documentation structure section | One home for each fact, and docs kept in the repository so Claude Code can read them |
| 2026-10-09 | Before stage 1 | Initial system SDD drafted | A thin system-level SDD plus per-stage SDDs written just in time, instead of one comprehensive SDD up front |
