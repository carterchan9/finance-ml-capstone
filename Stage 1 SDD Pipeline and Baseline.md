# Stage 1 SDD: Pipeline and Baseline

Oct 10, 2026 · @Carter

Detailed design for stage 1 of the capstone roadmap (Finance ML Engineer Capstone Roadmap.md). Contracts, the data model, the locked decisions and the tech stack live in the system SDD (Capstone System SDD.md) and are not repeated here; this document says how stage 1 uses them. Status: decisions confirmed on 2026-10-13, ready to build.

## Goal, scope and deliverables

Stage 1 builds the data foundation and the baseline for the whole capstone: a reproducible pipeline that generates a population of simple strategies from public price data, labels how much each one decayed out of sample, and trains models to predict that decay using time-ordered validation only.

**In scope**

- Price ingestion and caching
- A generator for rule-based strategies and their daily returns
- Samples built at rolling origin dates, with features from the in-sample window and a decay label from the out-of-sample window
- Walk-forward splits with a purge gap, defined once for all later stages
- Naive, linear and gradient-boosted models, scored with the metrics fixed in the system SDD
- An evaluation report and a written analysis of tradeoffs

**Out of scope**

- Neural networks (stage 2)
- Serving, scheduling or live data (stages 3 and 4)
- Transaction costs, shorting, leverage and multi-asset portfolios
- Extensive hyperparameter search; a small, documented grid is enough

**Deliverables**

- Populated tables: prices, strategies, samples, features, labels and splits
- Trained models with model\_runs and model\_registry entries, tagged feature schema v1 and label v1
- Fixed split definitions that stages 2 and 4 reuse
- An evaluation report with every metric next to every baseline, confidence intervals, and failure examples
- The stage build log, interview notes, and updates to the system SDD

## Inherited decisions and stage 1 specifics

Stage 1 uses the system SDD's locked decisions as written: decay label, data source, universe, date range, window lengths, split scheme and primary metrics. If one of those changes there, this document changes too. The choices below are specific to stage 1 and were decided on 2026-10-13.

| Choice | Proposed default | Why |
| --- | --- | --- |
| Return frequency | Daily simple returns from adjusted close prices. | Matches the data source and is easy to verify by hand. |
| Positions | Long or flat only, one position per strategy, no leverage or shorting. | Keeps each strategy simple enough to reason about and test. |
| Signal timing | The signal computed at the close of day t sets the position held on day t+1. | Prevents lookahead: a strategy never trades on the return it used to decide. |
| Moving-average crossover | Long when the fast average is above the slow average, otherwise flat. Fast in {5, 10, 20, 50}, slow in {50, 100, 150, 200}, fast shorter than slow (15 settings). | Classic trend rule with a small grid. |
| Momentum | Long when the trailing return is positive, otherwise flat. Lookback in {20, 60, 120, 250} days (4 settings). | Second trend-style rule with different timing. |
| Mean reversion | Long when price is a set number of standard deviations below its trailing mean, flat once it returns to the mean. Window in {20, 50}, threshold in {1, 1.5, 2} (6 settings). | A rule with the opposite behavior to the other two. |
| Origin frequency | Quarterly origin dates, from the first point with a full in-sample window to one out-of-sample window before the end of the data. | Gives many samples per strategy while keeping the label window at one year. |
| Sizing estimate | 50 tickers, 25 settings and 57 origins, so roughly 71,000 samples before exclusions. | Enough data for gradient-boosted trees without making runs slow. |

Quarterly origins make one strategy's label windows overlap each other, which is why the validation design groups samples by origin date and purges between train and test.

## Pipeline design

Nine steps run in sequence. Each step reads the outputs of previous steps and writes one set of tables, allowing any step to be rerun independently. Each step is implemented as a separate function with its own tests. The complete pipeline can be executed with one command: `python -m src.pipelines.run_stage1 --config config/stage1.toml`, which runs from cached prices. Configuration files in config/ set all windows, thresholds, and file paths.

| Step | What it does | Reads | Writes | Module under src/ |
| --- | --- | --- | --- | --- |
| 1. Ingest | Downloads daily adjusted prices for the universe, caches the raw pull with its date, and checks for gaps | External data source | prices, raw files in data/ | ingest/prices.py |
| 2. Strategy generator | Builds each strategy's daily position and return series from the rules and parameter grids | prices, config | strategies, return series in data/ | ingest/strategies.py |
| 3. Sample builder | Creates one sample per strategy per origin date, with its in-sample and out-of-sample windows | strategies, return series, config | samples | features/samples.py |
| 4. Feature builder | Computes features from the in-sample window only | return series, samples | features (schema v1) | features/build.py |
| 5. Label builder | Computes out-of-sample Sharpe, decay and the decayed flag from the out-of-sample window only | return series, samples | labels (v1) | features/labels.py |
| 6. Split builder | Creates walk-forward folds with the purge gap, grouped by origin date | samples | splits | models/splits.py |
| 7. Trainer | Fits the baselines and the gradient-boosted model per fold, with nested tuning | features, labels, splits | model\_runs, model files | models/train.py |
| 8. Evaluator | Computes metrics, baseline comparisons and confidence intervals, and writes the report | predictions, labels, splits | metrics in model\_runs, report files | models/evaluate.py |
| 9. Registry | Records the chosen model with its versions and git commit | model\_runs | model\_registry | models/registry.py |

## Features and label

Features are computed using returns up to and including the origin date only (no future data). Labels use returns after the origin date only. This feature list defines schema v1; any change to the features bumps the schema version.

| Feature | Definition | Why it is included |
| --- | --- | --- |
| Annualized return | Mean daily return in the in-sample window, times 252 | Basic performance level |
| Annualized volatility | Standard deviation of daily returns, times the square root of 252 | Basic risk level |
| In-sample Sharpe | Annualized return divided by annualized volatility, risk-free rate ignored | The main performance claim being tested |
| Max drawdown | Largest peak-to-trough fall in cumulative return | Tail risk the Sharpe ratio hides |
| Hit rate | Share of in-market days with a positive return | Separates steady strategies from lucky ones |
| Exposure | Share of days holding a position | A strategy rarely in the market has few observations |
| Turnover | Number of position changes per year | Proxy for how sensitive the strategy is to trading costs |
| Skewness | Skewness of daily strategy returns | Detects return profiles driven by a few large days |
| Excess kurtosis | Excess kurtosis of daily strategy returns | Detects fat tails |
| Sharpe rank in grid | Percentile of this sample's in-sample Sharpe among all settings of the same family on the same ticker at the same origin | Captures selection: the best of many settings is more likely to be luck |
| Underlying volatility | Annualized volatility of the ticker's own returns in the in-sample window | Separates strategy risk from market risk |
| Family | Which rule family the strategy belongs to (categorical) | Families may decay differently |

**Label (version 1)**

- **Out-of-sample Sharpe:** annualized Sharpe of the strategy's daily returns over the one-year window after the origin.
- **Decay:** out-of-sample Sharpe minus in-sample Sharpe. This is the regression target.
- **Decayed flag:** out-of-sample Sharpe below half of in-sample Sharpe, with the threshold in config. It is defined only when in-sample Sharpe is positive, and samples without a flag are excluded from the AUC.

## Validation design

The central lesson of stage 1 is that validation must respect time: samples are split by origin date (never randomly), with a purge gap between the last training origin and the first test origin to prevent lookahead bias.

```
Origin Date (years from start):  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17
Fold 1 Train:                   ████████████
Fold 1 Gap:                                                       █
Fold 1 Test:                                                             ███

Fold 2 Train:                   ████████████████
Fold 2 Gap:                                                                   █
Fold 2 Test:                                                                         ███

Fold 3 Train:                   ████████████████████
Fold 3 Gap:                                                                              █
Fold 3 Test:                                                                                   ███

Fold 4 Train:                   ████████████████████████
Fold 4 Gap:                                                                                  █
Fold 4 Test:                                                                                           ███
```
(█ = included in split, each █ = 1 origin year, gaps show purge period)

Each fold trains on earlier origins, skips a one-year gap, then tests on later origins, and the test block moves forward with each fold.

**Rules**

1. **Expanding train window.** Each fold trains on every origin from the first available one up to the fold's cutoff.
2. **Purge gap.** The gap between the last training origin and the first test origin is at least one out-of-sample window (one year), so no training label covers any period at or after a test origin.
3. **Grouped by origin date.** All samples sharing an origin date go on the same side of a split, because they share one out-of-sample period and are not independent.
4. **Test folds are touched once.** They are used only for final scoring. Hyperparameters are tuned inside each fold's training portion, using an inner walk-forward split with its own purge gap.
5. **Fixed once.** Fold boundaries are stored in the splits table and reused by every later stage; stages 2 and 4 never create their own.
6. **Layout.** Four folds with two-year test blocks, as drawn above. In years of origin date from the start of the data: fold 1 trains on 3 to 8 and tests on 9 to 11; fold 2 trains on 3 to 10 and tests on 11 to 13; fold 3 trains on 3 to 12 and tests on 13 to 15; fold 4 trains on 3 to 14 and tests on 15 to 17. Each fold has a one-year gap between the end of training and the start of testing. Fold counts and block lengths live in config.

## Models, baselines and metrics

Five predictors are scored the same way on the same folds, and the gradient-boosted model counts as an improvement only if it beats both baselines by more than chance.

| Predictor | What it does | Role |
| --- | --- | --- |
| Zero decay | Predicts decay of 0, so out-of-sample Sharpe equals in-sample Sharpe | Persistence reference; MAE only, because a constant has no ranking |
| Training-mean decay | Predicts the average decay in the training folds | Second reference; MAE only |
| Baseline 1: in-sample Sharpe only | Linear regression of decay on in-sample Sharpe, fitted on the training folds | The simplest model that knows about regression to the mean |
| Baseline 2: ridge regression | Regularized linear regression on all features | Tests whether extra features help without nonlinearity |
| Gradient-boosted trees | Regression of decay on all features, with learning rate, depth and tree count tuned over a small documented grid | The stage 1 candidate model |

**Metrics**

- **MAE** of predicted versus realized decay.
- **Spearman rank correlation** between predicted and realized decay.
- **AUC** for the decayed flag, using the negative of predicted decay as the risk score.

**Uncertainty**

- Confidence intervals come from a block bootstrap that resamples whole origin dates, not individual samples, because samples sharing an origin date are not independent.
- Compare the model with each baseline using the paired difference on the same resampled origin dates, and call it better only if the interval for that difference excludes zero.
- Also report per-fold values to show the spread, and run the gradient-boosted model with five fixed random seeds.

## Build plan

Build milestones are completed sequentially, with one git branch and pull request per milestone. For each milestone, first write the "hand-write first" component yourself, then use Claude Code's Learning output style to implement the remaining components. A milestone is complete only when its acceptance tests pass.

| Milestone | What to build | Hand-write first | Acceptance test |
| --- | --- | --- | --- |
| 1. Ingest | Download prices, cache the raw pull with its date, check for gaps | The gap check | Every universe ticker is present, and a rerun uses the cache and gives identical data |
| 2. Strategies | Position and return series for every rule and parameter setting | The moving-average crossover rule | A signal on day t never affects the return on day t, and a hand-computed toy example matches |
| 3. Metric functions | Sharpe, max drawdown, turnover, hit rate, skewness, kurtosis | Sharpe and max drawdown | Results match hand-calculated values on a small toy series |
| 4. Samples, features, labels | Origin dates, windows, feature and label builders | The in-sample Sharpe feature and the label | Changing returns after the origin changes no feature, and the label uses only the out-of-sample window |
| 5. Splits | Walk-forward builder with the purge gap, grouped by origin date | The whole split builder | No train origin lies within the gap of a test origin, no origin is on both sides, and every train origin is earlier than every test origin |
| 6. Baselines and evaluator | Naive references, baseline 1, ridge, metrics, block bootstrap | MAE and Spearman computed by hand once | Metrics match a hand calculation, and a rerun with the same seed gives identical numbers |
| 7. Gradient-boosted model | Training with nested tuning inside each fold | The inner-split tuning loop | An assertion confirms test folds are never used in tuning, and runs are logged to model\_runs |
| 8. Report and write-up | Evaluation report, tradeoff analysis, registry entry, doc updates | The written analysis | One command reproduces the report from cached prices, and the checkpoint questions are answered out loud |

## Edge cases and risks

These cases will come up in the data. Each has a fixed handling rule so results stay consistent, and the number of excluded samples is always logged by reason.

| Case | Handling |
| --- | --- |
| Undefined Sharpe, for example zero volatility because the strategy was never in the market | Exclude the sample and log it. |
| Few in-market days in either window | Exclude samples below a minimum number of in-market days (config, starting guess 30). |
| Negative or near-zero in-sample Sharpe | Decay is still defined as a difference. The decayed flag is not defined, so the sample is left out of the AUC. |
| Ticker without a full in-sample window at an origin, such as a recent listing | Drop those origins for that ticker. |
| Gaps or suspicious adjusted prices | The gap check flags them. Drop or repair the series, document the choice, and spot-check a few series against a second source. |
| Overlapping label windows from quarterly origins | Handled by grouping and purging. Effective sample size is far below the sample count, so report it. |
| Best settings in a grid decay the most | Expected, not a bug: they were selected for their in-sample luck. This is the signal the model should learn. |
| Survivorship bias and no transaction costs | Documented limitations from the system SDD. Repeat them in the evaluation report. |

## Success criteria and checkpoint

Stage 1 is done when all of these are true. There is no accuracy threshold, because an honest result matters more than a flattering one.

- The full pipeline runs from cached prices with one command and reproduces the same metrics with the same seed.
- All acceptance tests pass, including the leakage tests.
- The evaluation report shows every metric for every predictor, with block-bootstrap intervals and paired differences against both baselines.
- The gradient-boosted result is reported honestly: if it does not beat the baselines, the report says so and discusses why.
- Tables, versions and registry entries conform to the system SDD's contracts, and the system SDD and its change log are updated.
- The build log and interview notes are written.

**Checkpoint: explain these without Claude Code open**

1. Why random k-fold would leak future information in this problem.
2. How the purge gap works, and what goes wrong if it is removed.
3. Why decay is defined as a difference and not a ratio.
4. Why samples sharing an origin date are not independent, and what that does to the confidence intervals.
5. How survivorship bias and selection bias show up in this dataset.
6. How to reproduce one reported metric from scratch.
7. Why the gradient-boosted model did or did not beat the baselines.

## Open items and amendments

All items below were decided on 2026-10-13. If you change one, record it as an amendment and update the system SDD where needed.

- [x] Confirm the eight proposed defaults in the system SDD
- [x] Pick the exact universe: 20 ETFs and 30 large caps, listed in the system SDD
- [x] Confirm the stage 1 choices: long or flat positions, the parameter grids, and quarterly origins
- [x] Confirm the fold layout: four folds with two-year test blocks (18 years of data gives origins from year 3 to year 17)
- [x] Confirm the starting values for the minimum in-market days (30) and the decayed-flag threshold (half of in-sample Sharpe)

**Amendments**

None yet. This document is frozen at the stage 1 checkpoint; any later change is recorded here as a dated amendment, and the system SDD is updated if a contract changed.
