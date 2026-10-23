# Stage 1 Build Prompt

Oct 13, 2026 · @Carter

The prompt to give Claude Code to build stage 1, based on the stage 1 SDD (Stage 1 SDD Pipeline and Baseline.md) and the system SDD (Capstone System SDD.md). It stays short on purpose: the detail lives in the SDDs, so this prompt only points to them and sets the working rules.

## Before you run it

The prompt assumes these six things are already done.

- [ ] Setup is finished: Python 3.11 or later, Git, the GitHub repository cloned, a virtual environment active, and Claude Code installed.
- [ ] The repository has the folder layout from the system SDD, including `config/`, `src/`, `tests/` and `docs/`.
- [ ] Both SDDs are exported as Markdown into the repository at `Capstone System SDD.md` and `Stage 1 SDD Pipeline and Baseline.md`, then committed. Copying the text into those files also works.
- [ ] `CLAUDE.md` sits in the repository root with the project goal, the folder layout, your skill level, and the rules "explain decisions, prefer simple code, always add tests."
- [ ] You start Claude Code from the repository root and switch to the Learning output style with `/output-style learning`.
- [ ] You start in plan mode (Shift+Tab), so Claude proposes before it edits.

## The prompt

Paste everything in this block into Claude Code as your first message.

```text
You are helping me build Stage 1 of my finance ML capstone. I am new to programming and am learning ML engineering by building this, so teaching matters as much as the code.

READ FIRST, in this order, before changing anything:
1. CLAUDE.md
2. Capstone System SDD.md (contracts, data model, locked decisions, cross-cutting rules)
3. Stage 1 SDD Pipeline and Baseline.md (this stage's design, build plan, acceptance tests)

TASK
Build Stage 1 exactly as the stage 1 SDD specifies, one milestone at a time, in the order of its Build plan table (milestones 1 to 8). The SDDs are the source of truth. If something is ambiguous, missing or looks wrong, stop and ask me. Do not decide silently, and do not edit the SDDs.

HOW WE WORK
- Plan first: At the start of each milestone, provide a brief plan (identifying files, functions, and tests needed) and wait for my approval before proceeding.
- Hand-write first: For each milestone's "Hand-write first" item, do not implement it yourself. Instead, leave a TODO(human) comment in the code describing what should be implemented, what I should write, and any considerations. Wait for me to complete this item, then review my implementation critically before continuing.
- Tests: Write the milestone's acceptance tests alongside the implementation code. Run the tests and show me the output. A milestone is not considered complete until its acceptance tests pass.
- Git: Use one branch per milestone (e.g., m3-metric-functions), make small, focused commits with clear messages, and submit a pull request at the end. I will review and merge the pull request myself.
- Explain: After completing each work chunk, explain the key decisions in plain language and describe what I should be able to explain about the implementation.
- Stop at milestones: At the end of each milestone, summarize what has been implemented, what tests have passed, and what I should understand about the work completed. Wait for me to say "continue" before proceeding to the next milestone.
- Exercise caution: Before running any command that deletes files, installs packages, or accesses resources outside this repository, ask for my explicit approval.

RULES THAT MUST HOLD (from the SDDs)
- Use exactly the contracts, data model, locked decisions, and metrics defined in the system SDD (Capstone System SDD.md). Do not invent new tables, columns, or metrics.
- No lookahead: A signal calculated at the close of day t determines the position held on day t+1. Features must use data only up to and including the origin date. Labels must use data only after the origin date.
- Splits must come exclusively from the splits table. No origin date should appear on both sides of any split, and the purge gap between training and test origins must be at least one year.
- Configuration over hardcoding: Windows, thresholds, tolerances, file paths, and the ticker list must reside in configuration files, not be hardcoded in source code.
- Fixed random seeds: Every execution must record the git commit, data version, feature schema version, label version, and split ID.
- Data caching: Prices are cached raw with their pull date, and the pipeline must be able to rerun from the cache without requiring network access.
- Honest metric reporting: Report every performance metric alongside the baseline scores, using block-bootstrap intervals that resample complete origin dates (not individual samples).
- Code clarity: Favor simple, readable code over clever solutions. Include type hints and a concise docstring for every function.
- Documentation updates: Modify only the files docs/stages/stage-1-pipeline/build-log.md and interview-notes.md. At the end of each milestone, additions to the build log should document what was built, key decisions made, and any points of confusion. Leave all other files in the docs/ directory unchanged.

START
Read the three files referenced above, then give me your plan for milestone 1 (ingest) and wait for my OK.
```

**Why it is written this way**

- **Single source of truth:** By referencing the SDDs instead of duplicating their content, there is only one version of each fact to maintain and update.
- **Learning through doing:** The hand-write-first requirement ensures you actively learn by implementing core components yourself, rather than passively accepting code you cannot explain.
- **Incremental review:** Stopping after each milestone allows for careful review of small, manageable pull requests, keeping checkpoint questions answerable and maintaining steady progress.

## Follow-up prompts

Use these between milestones, pasted as they are. In the review prompt, replace the file path first.

**Continue to the next milestone**

```text
Continue to the next milestone. First re-read Stage 1 SDD Pipeline and Baseline.md for that milestone, then give me your plan and wait for my OK.
```

**Review code you wrote by hand**

```text
I have finished the hand-write-first piece for this milestone, in <file path>. Review it critically as a skeptical senior engineer: correctness against the Stage 1 SDD, edge cases, readability, and anything I should be able to explain. List what is wrong or risky first. Do not rewrite it for me. Point at the lines and explain, and let me fix it.
```

**Checkpoint quiz at the end of the stage**

```text
Quiz me on the seven checkpoint questions at the end of Stage 1 SDD Pipeline and Baseline.md, one at a time. After each answer, grade it honestly, say what I missed, and ask a follow-up if my answer was shallow. Do not give me the answer before I try.
```

**When something goes wrong**

```text
Stop and summarize: what you were asked to do, what you did, what failed, and your best explanation of why. Make no further changes until I reply.
```

## Reusing it for later stages

Each stage keeps its own copy of this document at `docs/stages/stage-<n>-<name>/build-prompt.md`. Only four things change between stages:

- The stage number and name in the first line of the prompt.
- The stage SDD path in the READ FIRST list.
- The first milestone named in the START section.
- The checkpoint quiz prompt, which should name that stage's SDD file and its number of checkpoint questions.

Everything else stays the same, including the working rules and the rules taken from the SDDs. Add a new line to RULES THAT MUST HOLD only when a stage introduces a rule that every later stage must keep, and add that rule to the system SDD at the same time.
