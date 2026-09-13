# Combat V2 Plan

Combat V1/V2 source, replays and checkpoints remain reproducible. This plan
does not change existing simulation/action/replay versions.

Future combat-depth work must introduce explicit new versions for simulation,
action space and replay schema before any implementation is used for
training or evaluation.

## Design Goals

- Keep the game understandable to humans.
- Add depth through context and timing rather than a large key list.
- Preserve deterministic replay verification.
- Keep benchmark opponents legal under the same observable rules.
- Never reinterpret old checkpoints or results.

## Input Philosophy

- `J`: light attack
- `K`: heavy attack
- `S`: guard
- `L`: dodge
- direction + attack: contextual movement attack
- timed guard: parry/perfect block
- simple sequences: combo paths

## Candidate Mechanics

- parry/perfect block
- guard break
- stamina or guard meter
- feint
- throw/shove refinement
- whiff punish windows
- knockdown and recovery
- corner escapes
- combo scaling
- directional/contextual moves

## Required Versioning

Any implementation must create new identifiers such as:

- `combat-v3` or another explicit simulation version
- protocol/action-space version beyond current v2 if actions change
- replay engine identifier beyond `combat-v2`
- reward version beyond `combat-v2-reward-1`
- checkpoint compatibility metadata that prevents old adapters from being
  silently evaluated under new action semantics

## Tests Before Use

- deterministic transition tests
- replay integrity tests
- action availability limits
- benchmark opponent legality
- human controls coverage
- trainer/evaluator version rejection for incompatible checkpoints
