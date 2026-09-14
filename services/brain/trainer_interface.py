"""Thin trainer interface around the current CEM implementation."""
from __future__ import annotations

from dataclasses import dataclass

from . import trainer

TRAINER_INTERFACE_VERSION = "trainer-interface-v1"


@dataclass(frozen=True)
class TrainerConfig:
    seed: int
    generations: int
    population: int
    seconds: int
    difficulties: tuple[str, ...] = ("easy", "medium", "hard")
    elite_fraction: float = 1 / 3
    sigma_init: float = .4
    sigma_floor: float = .04
    checkpoint_every: int = 1
    topology: str = "real"

    def as_kwargs(self):
        return {
            "seed": self.seed,
            "generations": self.generations,
            "population": self.population,
            "seconds": self.seconds,
            "difficulties": list(self.difficulties),
            "elite_fraction": self.elite_fraction,
            "sigma_init": self.sigma_init,
            "sigma_floor": self.sigma_floor,
            "checkpoint_every": self.checkpoint_every,
            "topology": self.topology,
        }


class CEMTrainer:
    name = "CEMTrainer"
    version = "cem-adapters-v1"

    def __init__(self, graph, config: TrainerConfig, emit=lambda _line: None, cancelled=lambda: False):
        self.graph = graph
        self.config = config
        self.emit = emit
        self.cancelled = cancelled
        self.checkpoint = ""

    def setup(self):
        return {"trainer": self.name, "version": self.version, "interface": TRAINER_INTERFACE_VERSION}

    def train_step(self):
        self.checkpoint = trainer.train(
            self.graph,
            emit=self.emit,
            cancelled=self.cancelled,
            **self.config.as_kwargs(),
        )
        return self.checkpoint

    def checkpoint_state(self):
        return {"checkpoint": self.checkpoint}

    def resume(self, run_id):
        self.checkpoint = trainer.train(
            self.graph,
            emit=self.emit,
            cancelled=self.cancelled,
            run_id=run_id,
            **self.config.as_kwargs(),
        )
        return self.checkpoint

    def metrics(self):
        return {"checkpoint": self.checkpoint, "config": self.config.as_kwargs()}

    def evaluate(self, arrays):
        return trainer.evaluate(self.graph, arrays, self.config.seconds)

    def stop(self):
        return {"stopped": True}


FUTURE_TRAINERS = {
    "PPOTrainer": "future adapter/readout policy trainer; not implemented in this phase",
    "GeneticTrainer": "future comparative evolutionary adapter trainer",
    "MAPElitesTrainer": "future behavioural diversity archive over adapter vectors",
    "NEAT": "not a primary fixed-connectome trainer because topology evolution changes the boundary",
}
