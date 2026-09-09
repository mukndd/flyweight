import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .limits import MAX_MESSAGE_BYTES


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    v: Literal[2]


class Reset(Message):
    type: Literal["reset"]
    seed: int = Field(ge=0, le=2**32-1)
    topology: Literal["real", "degree_randomized", "weight_shuffled", "ordinary", "rule", "random"]


class Observation(Message):
    type: Literal["observation"]
    seq: int = Field(ge=0, le=5400)
    values: list[Annotated[float, Field(ge=-1, le=1)]] = Field(min_length=20, max_length=20)


class Simple(Message):
    type: Literal["health", "train_stop", "checkpoint_list"]


class Train(Message):
    type: Literal["train_start"]
    seed: int = Field(ge=0, le=999_999)
    generations: int = Field(ge=1, le=20)
    population: int = Field(ge=4, le=12)
    episode_seconds: int = Field(ge=6, le=30)


class Load(Message):
    type: Literal["checkpoint_load"]
    id: str = Field(pattern=r"^candidate_[a-z0-9_]{1,60}$", max_length=70)


PARSER = TypeAdapter(Annotated[Reset | Observation | Simple | Train | Load, Field(discriminator="type")])


def parse_message(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("Message size/type")
    def reject_constant(_):
        raise ValueError("Non-finite JSON")
    obj = json.loads(raw, parse_constant=reject_constant)
    if not isinstance(obj, dict) or type(obj.get("v")) is not int or obj["v"] != 2:
        raise ValueError("Protocol version")
    return PARSER.validate_python(obj)

