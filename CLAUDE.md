# Project Context for Claude

## 1. Project Overview

The codebase is **FLAPPY ADAPT**, a Python/Pygame Flappy Bird prototype for experimenting with dynamic difficulty adjustment (DDA). The repository name is `FLAPPY_BIRD_DDA`. It is not currently a stickman fighting game: there are no combat, health, dodge, enemy, or boss systems.

The implemented research direction is to vary the pipe gap in response to gameplay outcomes and compare fixed, rule-based, and model-assisted difficulty controllers.

## 2. Actual Current Project Status

- A playable, keyboard-controlled Flappy Bird game and headless simulation loop exist.
- Fixed, reactive, per-obstacle ML-assisted, and multi-attempt controllers are present.
- Training data, historical session logs, an experiment-results CSV, a plot, and a pickle model file are present.
- The active ML training/inference code is a **binary per-obstacle success predictor**. It does not learn a combat strategy or directly classify a player's general skill.
- The checked-in training data was generated using only the high-skill scripted bot. Existing experiment results also cover only that bot.
- The multi-attempt path is incomplete as a research pipeline: its separate training script expects absent attempt-history data and saves a model the game does not load by default.
- There is no README, test suite, project/build configuration, or dedicated test directory in the inspected repository.
- Do not describe the intended stickman project as implemented; this checkout is a Flappy Bird DDA prototype.

## 3. Project Goals and Intended Research Direction

The implementation suggests an experiment in adapting obstacle difficulty toward a target success rate, and comparing adaptation against fixed and reactive baselines. The code does not document a broader validated research protocol. Human input is supported, but the training dataset is scripted-bot data; no verified human-player training set or user-specific learned profile was found.

If the intended project has since changed to a stickman fighter, first clarify whether this repository is the correct starting point. Do not silently retrofit that game into the current Flappy Bird code.

## 4. Technology Stack

- Python; the inspected runtime is Python 3.12.10.
- `pygame-ce` for 2D drawing, keyboard events, and the game loop.
- `numpy`, `scikit-learn` (logistic regression), and `joblib` for the per-pipe model pipeline.
- `pandas` is listed in requirements but is not imported by the inspected source.
- Python standard library modules provide CSV/JSON persistence, CLI parsing, timing, and statistics.
- `matplotlib` is an optional plotting dependency in `experiments/analyze.py`; it is not in `requirements.txt`.
- `data/model.pkl` is a pickle/joblib artifact. Its contents were not loaded during this audit.

Dependencies are listed without version pins in [requirements.txt](requirements.txt). The game draws its bird, pipes, and HUD directly; no external image/audio assets or scene files were found.

## 5. Repository Structure

- `main.py` — CLI entry point and controller selection.
- `game/` — game loop, bird and pipe objects, constants, and CSV logging.
- `controllers/` — fixed, reactive, per-pipe ML-assisted, and multi-attempt difficulty logic.
- `ml/` — scripted bots, per-pipe features, data generation/model training, diagnostics, and sanity-check script.
- `experiments/` — scripted-controller experiment runner and result analysis/plotting.
- `data/training_data.csv` — 2,061 event rows.
- `data/model.pkl` — 1,178-byte model artifact; not inspected by deserialization.
- `data/experiment_results.csv` — 30 episode rows.
- `data/logs/` — 338 CSV session logs; all inspected log headers use the same 16-field schema.
- `data/plots/score_comparison.png` — stored experiment plot.
- `ml/train_skill_model` — extensionless, separate attempt-cycle model training script.

No README or `.md` documentation existed before this file was created. Python bytecode/cache files are present in the repository inventory; avoid treating them as source.

## 6. Important Files, Classes, and Functions

- [main.py](main.py): `build_controller(name)` creates a controller. CLI choices: `fixed`, `reactive`, `ml_adaptive`, and `multi_ml`.
- [game/game.py](game/game.py): `FlappyGame` owns initialization, episode reset, collision/pass processing, logging, rendering, and `run_episode()`. `play_human()` is the interactive loop.
- [game/bird.py](game/bird.py): `Bird.reset()`, `jump()`, `update()`, collision rectangle, and drawing.
- [game/pipe.py](game/pipe.py): randomized gap center, fixed-speed movement, collision rectangles, and drawing.
- [game/config.py](game/config.py): screen size, FPS, physics, pipe speed/spawn cadence, gap bounds, colors, and log directory.
- [game/logger.py](game/logger.py): CSV field schema and per-session logger.
- [controllers/base.py](controllers/base.py): `DifficultyController` contract, `on_pipe_outcome(outcome)`, and `reset()`.
- [controllers/fixed.py](controllers/fixed.py): returns a constant gap.
- [controllers/reactive.py](controllers/reactive.py): adjusts gap after success/failure streak thresholds.
- [controllers/ml_adaptive.py](controllers/ml_adaptive.py): loads a classifier, searches candidate gaps for a probability near `target_success`, and falls back to recent success-rate rules if no model is available.
- [controllers/multiattempt.py](controllers/multiattempt.py): aggregates attempt records, adjusts difficulty after a cycle, and persists history/decisions.
- [ml/features.py](ml/features.py): shared 10-value feature vector (`FEATURE_NAMES`) for per-pipe training and inference.
- [ml/train.py](ml/train.py): scripted data collection, logistic-regression training, metric printing, and model saving.
- [ml/bots.py](ml/bots.py): low-, medium-, and high-skill scripted policies.
- [experiments/run_experiment.py](experiments/run_experiment.py): headless comparison of fixed/reactive/ML controllers.
- [experiments/analyze.py](experiments/analyze.py): reads the results CSV and prints summaries; optionally generates the plot.
- [ml/train_skill_model](ml/train_skill_model): separate random-forest training script for attempt-cycle history.

## 7. Game Architecture and Gameplay Flow

`main.py` selects a controller and calls `play_human()`. `FlappyGame` creates `Bird`, spawns `Pipe` objects every `PIPE_SPAWN_INTERVAL` frames, advances physics, checks screen-edge and pipe collisions, and records each pass or collision. A pass/failure outcome is sent to the selected controller; the returned gap affects subsequently spawned pipes. The HUD displays score, current gap, and controller name.

`play_human()` uses **SPACE** to flap/jump and **Q** or the window close event to quit. A collision ends the current attempt and starts a fresh one. The game is 480×640 at 60 FPS, with gravity `0.5`, jump velocity `-9.0`, pipe speed `3.0`, and default gap `165`; see [game/config.py](game/config.py).

The headless path can run scripted agents through `FlappyGame.update()`. Game objects are drawn procedurally; there are no scene/component frameworks.

## 8. Machine Learning Architecture

The active model path is:

1. `ml.train.collect_dataset()` runs `BotHighSkill` against fixed gaps and captures obstacle outcomes.
2. `ml.features.extract_features()` builds 10 numeric inputs.
3. `ml.train.train_model()` fits a balanced `LogisticRegression`, using an event-level stratified random train/test split.
4. The model bundle is saved to `data/model.pkl` with `model` and `feature_names`.
5. `MLAdaptiveController` loads the bundle and uses `predict_proba()` for candidate gaps. It selects the gap whose predicted pass probability is nearest the target (default `0.6`), then limits the gap change to at most 8 pixels per outcome.
6. If loading/inference is unavailable, the controller adjusts gap using recent success rate; this fallback is hard-coded, not ML.

The stored CSV has 2,061 rows: 1,883 positive and 178 negative labels; its `bot` value is only `high`. This is imbalanced event data despite `class_weight="balanced"` in training. A random split across correlated events from the same bot/episodes can overstate generalization.

## 9. Dataset and Feature Definitions

`data/training_data.csv` columns are the 10 model features, followed by `success`, `gap`, and `bot`. `success` labels whether an individual pipe was passed (`1`) or the run ended in a collision (`0`). `gap` and `bot` are metadata, not model features.

The feature vector is defined in [ml/features.py](ml/features.py):

1. `gap_size / 240`
2. `bird_y_at_pass / 640`
3. clamped `bird_vel_at_pass / 10`
4. consecutive successes / 10 (upper-clamped)
5. consecutive failures / 10 (upper-clamped)
6. recent 3-event success rate
7. recent 5-event success rate
8. recent 10-event success rate from supplied history
9. recent-3 minus recent-5 trend
10. total pipes passed / 20 (upper-clamped)

Training uses eight fixed gap values `[90, 110, 130, 150, 170, 190, 210, 240]`, 40 episodes per gap, and only `BotHighSkill`. The observed CSV has gaps at all eight values. Data is synthetic bot gameplay, not an externally sourced dataset.

## 10. Model Training and Inference

- Primary command: `python -m ml.train`. It regenerates `data/training_data.csv` and overwrites `data/model.pkl`; it also prints accuracy, ROC-AUC, a classification report, and coefficients. No training command was run during this audit, so no metrics are claimed.
- Inference for `ml_adaptive` is performed in `controllers/ml_adaptive.py` on each pipe outcome. `data/model.pkl` exists, but its serialized contents and real inference behavior were not verified because the artifact was not deserialized.
- The separate extensionless [ml/train_skill_model](ml/train_skill_model) script expects `data/attempt_history.json`, at least 20 complete cycle-pair samples, and writes `data/skill_model.pkl`. Neither file exists in the inspected repository. The default `multi_ml` controller instead loads `data/model.pkl`, so this separate training output is not wired into the normal CLI path.

## 11. Gameplay Data Collection

`GameLogger` writes one row per obstacle pass or collision to `data/logs/session_<id>_<controller>.csv`. Fields include episode/pipe index, gap size/center, bird position/velocity, success, recent success streak/rates, survival time, pipes passed, and controller. Existing logs use a common header.

`ml.train` captures events by wrapping this logger and writes the training dataset. `experiments.run_experiment` wraps it to track gap changes and writes episode-level experiment rows. Multi-attempt control separately writes JSON history and decisions to `data/attempt_history.json` when run; that file is currently absent.

## 12. Difficulty Adaptation and AI Opponent

- `fixed`: always returns its configured gap (`165` in the CLI).
- `reactive`: decreases gap after a success streak and increases it after a failure streak; defaults to 12-pixel steps and a threshold of three.
- `ml_adaptive`: per-outcome model-probability search toward target success `0.6`; uses a rule-based fallback if needed.
- `multi_ml`: holds the gap constant during each attempt, aggregates five attempts by default, adjusts at cycle boundaries, and applies the pending change at the next attempt. Its fallback derives skill from success rate/trend.

These are obstacle-difficulty controllers, not fighting-game opponents. No opponent combat AI exists. The multi-attempt code passes synthetic/default per-pipe inputs to the per-pipe model and interprets its probability as cycle skill; this target/feature mismatch needs resolution before treating it as a valid skill model.

## 13. Setup and Installation

From the repository root, use Python 3 and install [requirements.txt](requirements.txt):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The audited environment was Python 3.12.10 with `pygame-ce` 2.5.8. Requirements are unpinned. No installation was performed for this audit.

## 14. Commands to Run, Test, and Train

```powershell
python main.py --controller fixed
python main.py --controller reactive
python main.py --controller ml_adaptive
python main.py --controller multi_ml
python main.py --controller fixed --session my-session
python -m ml.train
python -m ml.sanity_check
python -m experiments.run_experiment
python -m experiments.analyze
python ml/diag.py
python ml/debug_bot.py
```

There is no configured automated test suite. Be aware that `ml.sanity_check` and game runs write logs; `ml.train` overwrites the dataset/model; the experiment runner overwrites `data/experiment_results.csv`; and analysis may overwrite the plot. The extensionless cycle trainer is not part of the usual CLI flow and requires its missing history input.

Audit validation performed: all 23 `.py` files parsed with Python's AST; `python main.py --help` succeeded; 13 core modules imported; one seeded, in-memory headless simulation ran through 345 frames and two pipe passes before the game loop returned its terminal signal. A no-op logger prevented test logs. No GUI session, full test suite, model deserialization, model training, or experiment rerun was performed.

## 15. Implemented Features and Verification Status

Status labels reflect this audit, not source-code presence alone:

| Feature | Status | Evidence / limitation |
|---|---|---|
| Flappy Bird physics, pipes, collisions, score, and headless update loop | IMPLEMENTED AND VERIFIED | One seeded headless run completed two passes and reached a terminal update; not exhaustive. |
| Human keyboard loop and HUD | IMPLEMENTED BUT UNVERIFIED | Code and CLI imports exist; interactive GUI was not opened. |
| Fixed and reactive gap controllers | IMPLEMENTED BUT UNVERIFIED | Code and stored experiment rows exist; experiment was not rerun. |
| Per-pipe ML dataset/training/inference pipeline | IMPLEMENTED BUT UNVERIFIED | Trainer, CSV, and model file exist; training/inference and pickle contents were not verified. |
| Session CSV telemetry | IMPLEMENTED BUT UNVERIFIED | Logger source and 338 existing logs inspected; no new log-writing game test was run. |
| Multi-attempt adaptation and persistence | PARTIALLY IMPLEMENTED | Controller source exists; required history/model integration is incomplete and behavior was not run. |
| Cycle-level skill model training | BLOCKED | `data/attempt_history.json` is absent; its `skill_model.pkl` output is not connected to the default controller. |
| Stickman fighter, combat, health, dodge, enemy/boss AI | NOT IMPLEMENTED | No meaningful implementation found. |
| Human-player ML training/evaluation dataset | NOT IMPLEMENTED | Training CSV contains only scripted `high` bot rows; logs alone do not establish a curated human dataset. |
| Automated tests | NOT IMPLEMENTED | No test files or test-runner configuration found. |

## 16. Known Bugs and Limitations

- In `ml/train.py`, the logger wrapper passes `game.success_history + [record["success"]]`, but `FlappyGame` appends the current result to `success_history` before calling the logger. The supplied history therefore duplicates the current outcome, affecting the recent-10 feature and introducing outcome leakage.
- `experiments.run_experiment` measures `survival_time_s` with wall-clock time while running unpaced headless frames. The stored 30 results range from 0.002 to 0.063 seconds; these values are runtime speed, not comparable simulated survival duration.
- 28 historical log time-field values are epoch-sized rather than elapsed durations. Treat old `survival_time`/`time_since_last_pass` data as inconsistent until cleaned or filtered.
- `GameLogger.__init__` assigns `self.path` as a string while the class also defines a method named `path`; the instance attribute shadows that method.
- `ml/train_skill_model` uses `pickle.dump`, while model loading uses joblib. Although compatible for many estimators, keep serialization/loading consistent and explicit.
- The multi-attempt controller's expected cycle-level `FEATURE_ORDER` differs from the per-pipe model's `FEATURE_NAMES`; its adapter fabricates bird position/velocity and applies attempt outcomes to an individual-pipe model. This is not a validated skill estimate.
- Random event-level train/test splitting can place highly correlated outcomes from the same scripted behavior in both partitions. No held-out player/session evaluation was found.
- The game does not set `Bird.alive` false on collision; callers rely on the returned terminal boolean and reset flow.
- No pinned dependency versions, automated tests, or documented clean setup/run instructions exist outside this file.

## 17. Missing Integrations and Incomplete Features

- The intended stickman-fighter domain does not match the current game implementation.
- There is no real player behavior model, player segmentation/profile, combat AI, or evaluation protocol.
- `data/skill_model.pkl` is never selected by `main.py`; current `multi_ml` construction points to `data/model.pkl`.
- The multi-attempt trainer is blocked by missing history and is separate from the primary training process.
- Telemetry and model data need a consistent definition of elapsed/simulated time and feature windows before training on mixed historical data.
- No formal automated regression tests cover game rules, controller bounds, feature ordering, or persistence.

## 18. Development Priorities and Recommended Roadmap

1. **Confirm product scope.** Decide whether this repository remains the Flappy Bird DDA research prototype or whether a separate stickman-game repository is intended.
2. **Stabilize telemetry semantics.** Fix duplicate-history feature construction and choose elapsed wall time vs frame-derived simulated time; document and validate historical data before reuse.
3. **Add small tests.** Cover pass/collision events, controller gap limits, feature-vector ordering, data labels, and multi-attempt state transitions.
4. **Choose one skill target/model interface.** Either train/validate per-obstacle success probability for `ml_adaptive`, or collect attempt cycles and wire an explicitly trained cycle model into `multi_ml`. Do not treat these targets as interchangeable.
5. **Improve evaluation.** Separate training and evaluation by session/bot seed; include human play only with clear consent and data provenance; compare to fixed/reactive baselines with meaningful time and success metrics.
6. **Only then extend gameplay or the research model.** Preserve the playable loop and existing data; do not claim adaptation quality or model performance without rerunnable evidence.

## 19. Coding Conventions and Project Constraints

- Keep game mechanics in `game/`, difficulty policies in `controllers/`, shared model features/training in `ml/`, and experiment scripts in `experiments/`.
- Reuse `DifficultyController.on_pipe_outcome(outcome)` for per-event policies. Multi-attempt controllers use the separate `begin_attempt()` / `end_attempt(stats)` hooks detected by `FlappyGame`.
- Use `game/config.py` for shared gameplay constants and preserve existing CSV/model feature schemas unless updating producers, consumers, and stored-data compatibility together.
- Existing code uses straightforward Python classes/functions, CSV/JSON files, and command-line scripts. Avoid adding frameworks or dependencies without a concrete need.
- Preserve existing datasets, logs, results, and model artifacts; commands may overwrite these files.

## 20. Instructions for Claude When Continuing Development

- Read the relevant source files before making changes.
- Preserve the existing architecture unless a change is justified.
- Do not rewrite the entire project unnecessarily.
- Do not replace working code with invented implementations.
- Do not claim that ML is implemented if the game only uses hard-coded rules.
- Do not fabricate datasets, model predictions, evaluation metrics, or results.
- Do not train a model until the dataset, features, target, and training procedure are understood.
- Do not introduce unnecessary frameworks or dependencies.
- Keep changes modular and explain the files affected.
- Prefer small, testable changes.
- Run relevant tests or validation commands when possible.
- Report exactly what changed, how to test it, and any remaining limitations.
- If requirements are ambiguous, inspect the code first and ask for clarification only when necessary.
- Preserve the project's research objectives while distinguishing the intended design from implemented functionality.
