# Flyweight

Flyweight is a browser fighting game where one fighter — the **Fly Brain** — is
controlled by a recurrent artificial network built on the wiring of a real
fruit fly (*Drosophila melanogaster*) connectome (FlyWire FAFB v783). The
other fighter is either you or a **Bot** driven by ordinary rule-based game
logic.

It exists to ask one question honestly: *does constraining a game controller
to biological wiring do anything measurable, compared to an ordinary network
or a hand-written rule-based bot of similar size?* The project is built to
let you compare those controllers directly, not to convince you the answer
is yes.

## What this is

- A real, hash-verified FlyWire v783 connectivity graph (138,639 neurons,
  ~15.1M directed synaptic rows) reduced to a deterministic, documented
  1,536-neuron / 170,489-edge subgraph (seed `783`) that sits between an
  artificial sensory encoder and an artificial motor decoder.
- A from-scratch TypeScript fighting-game simulation (movement, blocking,
  crouch, combos, counters, hit-stun, knockback) shared by the renderer,
  the headless trainer, and replay playback.
- A from-scratch NumPy/SciPy recurrent update over that graph, exposed to
  the browser over a local FastAPI/WebSocket service, with a lightweight
  Cross-Entropy Method trainer that adapts only the input/output adapters.
- A visible, honest decision trace for both fighters: what each one could
  see, what changed in the network or rule set, what action it chose, and
  whether that action worked.

## What this is **not**

- Not a conscious fly, not a full biological brain emulation, not a claim
  that the fly connectome is "smarter." The connectome supplies fixed
  wiring and connection topology; the dynamics running on it are an
  engineering approximation, not a biophysical simulation.
- Not proof that biological topology helps gameplay — that is the open
  question the built-in **Research controller** comparisons (real /
  degree-randomized / weight-shuffled / ordinary recurrent / rule / random)
  are there to test, not to answer for you.
- The demo/offline bot never fabricates neural activity. When the Fly Brain
  engine is offline or a rule-based baseline is selected, the interface
  says so explicitly and shows zero active neurons — it never fakes a
  "brain activity" display.

## Architecture

```
apps/web/         Vite + React + TypeScript frontend, Phaser/Canvas arena,
                   live decision panels, brain visualization, replay viewer.
packages/protocol/ Versioned WebSocket message + action-space types shared
                   by the frontend and the brain service.
packages/sim/      Deterministic combat engine (core.ts) reused by the
                   browser, the headless Node bridge, and training.
services/brain/    FastAPI + WebSocket brain service: connectome loading,
                   the recurrent controller, the CEM trainer, checkpoint
                   storage, and production config/limits.
scripts/           Data download/preprocessing, dev/build task runner,
                   reproduction, supply-chain inventory, size reporting.
docs/              Provenance, baseline notes, screenshots, generated
                   audit artifacts.
data/, checkpoints/, replays/  Local-only, git-ignored outputs.
```

Game rules live in one place (`packages/sim/core.ts`) and are reused by the
renderer, the headless self-play bridge, and replay verification, so a
replay can be checked bit-for-bit against a fresh simulation of the same
seed and action log.

## Fly Brain vs. Bot vs. You

| Side | Label | Controller |
|---|---|---|
| Right, purple, ✳ | **Fly Brain** | FlyWire-derived recurrent network (or an explicitly labelled research/offline substitute — see Research details in-app) |
| Left, green, ◆ | **Bot** or **You** | Rule-based spacing/attack logic (Easy/Medium/Hard), or your own keyboard input |

The identity, color and label are consistent everywhere in the UI (nav,
health bars, decision panels, replay captions). The interface never implies
the Fly Brain is active when a fallback or rule baseline is actually
running.

## Modes

- **Play** — you fight the Fly Brain.
- **Watch** — the Bot fights the Fly Brain; useful for observing the
  decision trace without playing.
- **Train** — run a headless Cross-Entropy Method training experiment
  against the frozen connectome; produces a candidate checkpoint, never
  overwrites the canonical model.
- **Replays** — load a saved match and step through it frame by frame;
  replays store the verified action log, not recorded brain activity, and
  say so on screen.

## Controls

`A`/`D` move, `W` jump, `S` block, `C` crouch/guard-low, `J` light punch,
`K` heavy punch, `L` dodge, `Space` pause. Direction/timing modifiers add
depth without new keys: forward+`J` advancing punch, `C`+`J` low kick
(beats standing guard), `S`+`K` shove (beats guard, dodgeable), a jump then
`J`/`K` air strike, and `J, J, K` a combo finisher. Blocking just before a
hit opens a counter/punish window. The in-game **Controls** overlay (⌨)
lists all of this and can be opened at any time.

## Fixed vs. trainable

- **Fly wiring: fixed.** The connectome topology and biological connection
  signs/strengths never change during play or training.
- **Adapters: trainable.** Only the artificial sensory encoder and motor
  readout can adapt, and only in Train mode, against a frozen evaluation
  suite. A trained candidate becomes selectable in the match setup only
  after evaluation; the browser can never overwrite the canonical model.

## Running locally

Requirements: Node 22.12+ (Node 24 recommended per `package.json` engines),
Python 3.11 or 3.12, no GPU/Docker/WSL required.

**Quick start:**

```bash
npm install
python -m venv .venv && .venv/Scripts/activate   # or .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt

npm run setup:brain   # one-time: fetch + verify + preprocess the real FlyWire v783 data (~131 MB)
npm run dev           # starts the brain service, waits for it to be healthy, then starts the frontend
```

Open the printed local URL. `npm run dev` runs one command and manages both
processes for you — starts the Python brain service, waits for its
`/health` check before opening the frontend, streams both logs to one
terminal, and shuts both down together on Ctrl+C. If it detects a
compatible brain service already running on port 8000, it reuses it
instead of starting a second one; if the port is occupied by something
else, it fails clearly rather than connecting to it.

`npm run dev` requires the **real** connectome data prepared by
`npm run setup:brain` and will refuse to start (with a clear message)
rather than silently falling back to a synthetic graph. For UI-only
development without the real dataset, pass `--synthetic` to both commands
(`npm run setup:brain -- --synthetic`, `npm run dev -- --synthetic`) — the
interface always labels this fixture as synthetic, never as the Fly Brain.

If the brain service is genuinely unreachable at runtime (e.g. it crashes
after startup), the frontend stays playable using an explicitly labelled
offline demo bot — it does not pretend the Fly Brain is connected.

### Advanced: running the two services separately

```bash
npm run dev:brain   # brain service only, foreground, console logs
npm run dev:web     # frontend only (Vite)
npm run eval:brain -- --seconds 12          # evaluate the current/a checkpoint
npm run train:brain -- --preset starter     # short CEM training run (see below)
npm run train:brain -- --preset serious     # long, unattended CEM training run
npm run research:once                       # tiny bounded local research cycle
npm run research:daily                      # regenerate the local daily report
```

The **Research** tab reads persisted local research state from the brain
service and shows champion lineage, ladder progress, topology-control
status, daily report metrics and human challenge status. See
`docs/RESEARCH_PLATFORM_FOUNDATION.md` for the local registry and
orchestrator details.

### Environment variables

See `.env.example`. Frontend: `VITE_BRAIN_URL` (brain WebSocket base URL;
defaults to `http://127.0.0.1:8000` in dev). Backend: `FLYWEIGHT_ENV`,
`PORT`, `FLYWEIGHT_BIND_HOST`, `FLYWEIGHT_PUBLIC_ORIGINS`,
`FLYWEIGHT_ALLOWED_HOSTS`, `FLYWEIGHT_DATA_DIR` — all validated at startup
(see `services/brain/config.py`); invalid or missing production values fail
closed rather than defaulting to something permissive.

## Testing

```bash
npm run test     # Vitest (combat + protocol unit tests)
npm run lint      # ESLint + type-check
npx playwright test               # end-to-end browser flows
.venv/Scripts/python -m pytest services/brain/tests   # brain service tests
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m bandit -r services -x services/brain/tests
```

See `BUILD_REPORT.md` for the latest verified results.

## Reproducibility

Every match, replay and training run records its seed, action-space
version, difficulty, Fly Brain/research-controller mode and checkpoint id.
`scripts/reproduce.py` replays a saved match's action log through a fresh
simulation and checks it reaches an identical result. Replays and
checkpoints are validated (bounded sizes, explicit schemas, no pickle, no
executable content) before being loaded — see `services/brain/checkpoints.py`
and the replay validation in `packages/protocol`.

## Data sources and attribution

- FlyWire FAFB v783 connectivity and neuron completeness data, and the
  MIT-licensed reference pipeline: https://github.com/philshiu/Drosophila_brain_model
- Zenodo connectivity record: https://zenodo.org/records/10676866
- Scientific reference: https://www.nature.com/articles/s41586-024-07763-9
- FlyWire neuron annotations: https://github.com/flyconnectome/flywire_annotations

Every downloaded file's source URL, byte size, SHA-256 hash and download
timestamp is recorded in `docs/source-lock.json`. No GPL-licensed code was
copied into this project. Raw and processed connectome data are not
committed to this repository (see `.gitignore`); re-run
`scripts/download_data.py` to fetch them.

## Limitations

- The subgraph is a documented, seeded selection of ~1.1% of the full
  connectome, not the whole brain.
- The recurrent update is a fast engineering approximation, not a
  spike-accurate biophysical simulation (a separate, slower leaky
  integrate-and-fire research model exists in `scripts/lif_experiment.py`
  for short validation runs, decoupled from game framerate).
- Early two-generation CEM pilots (trivial training budget) reached 0%
  held-out win rate. A `--preset serious` run (20 generations, population
  12, all three difficulties, ~3m44s wall clock) reached a **100% held-out
  win rate** (mean reward 45.0, 9-episode evaluation-v2 suite) and was
  promoted through the existing evaluation gate — see
  `docs/RESUME_BASELINE.md` for the full numbers, including an honest
  open question about the trained policy converging to seed-insensitive
  behaviour against medium/hard opponents that a future session should
  investigate before treating this as a settled result.
- No production deployment exists yet; see `AGENTS.md` for the current
  authorization state and `BUILD_REPORT.md` for what remains before a
  public deployment would be appropriate.

## License

The code in this repository does not yet carry a license file pending an
explicit licensing decision by the project owner. The imported reference
pipeline and FlyWire data retain their own upstream licenses (MIT for the
reference pipeline; see `docs/source-lock.json` and the upstream `LICENSE`
file fetched alongside it).
