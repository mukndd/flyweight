# Flyweight v0.7 Research Platform Foundation

This phase makes Flyweight local-first research infrastructure, not a claim
that the FlyWire graph is superior. The biological topology remains fixed;
training is still CEM over artificial encoder/readout/bias adapters only.

## Local Registry

`services.brain.research_registry` stores versioned metadata in SQLite at
`checkpoints/research.sqlite` by default. The schema is shaped so it can be
mapped to PostgreSQL/Supabase later without requiring cloud credentials now.

Tracked entities:

- experiments
- runs
- candidates
- champions
- checkpoints
- evaluations
- ladder_certifications
- topology_conditions
- daily_reports
- human_matches
- leaderboard_entries

Promotion/champion rows are append-only. Candidate status may move through
`training`, `failed`, `rejected`, `promising`, `validated`,
`certification_failed`, `promoted`, and `archived`, with structured reasons
where available.

## Benchmark Ladder

`services.brain.ladder` defines `combat-ladder-v1` with `L01-v1` through
`L10-v1`. Difficulty is produced only through legal game policy knobs:
reaction timing, spacing, aggression, defense, counter timing and profile
variation. No level changes damage, sees hidden future state, teleports, or
uses impossible actions.

Certification records include level version, checkpoint hash, scenario
suite, matches, wins, win rate, Wilson 95% CI, damage differential,
scenario-family performance, responsiveness checks, anomaly flags, commit
and graph hash.

## Topology Controls

`services.brain.topology_experiments` defines the fair comparison conditions:

- `REAL_CONNECTOME`
- `DEGREE_PRESERVING_RANDOMIZED`
- `WEIGHT_SHUFFLED`
- `MATCHED_RANDOM_RECURRENT`
- `DIRECT_BASELINE` (reserved interface, not concluded)
- `RULE_BASELINE`
- `RANDOM_ACTION_BASELINE`

All trainable conditions share the same observation/action space, reward
version, scenario version, trainer budget and held-out suite in the planned
config. Unavoidable differences are recorded explicitly.

## Autonomous Loop

`services.brain.research_loop` provides:

- `npm run research:once`
- `npm run research:run`
- `npm run research:daily`

The loop chooses only from bounded, predefined experiment dimensions. It
does not accept code, shell commands, expressions, reward functions, module
paths or URLs from the database or browser.

A bounded local dry run can be executed with:

```bash
npm run research:once
```

This creates an experiment, registers topology conditions, trains a tiny CEM
candidate, evaluates it against the ladder, records certification success or
failure, writes lineage, creates a daily JSON report, and exits. It does not
fake promotions.

## Dashboard

The Research tab reads persisted local state from read-only brain-service
endpoints:

- `/research/overview`
- `/research/lineage`
- `/research/ladder`

The UI distinguishes live process state from last completed research result
and editable next-run configuration.

## Human Challenge

The foundation is anonymous and deliberately small. Server-issued sessions
record champion/checkpoint identity and seed. Match results must be derived
from replay verification; a client-sent claim is insufficient. Human games
are tagged `HUMAN_EXHIBITION` and are not training data.
