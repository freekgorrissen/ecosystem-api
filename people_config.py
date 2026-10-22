import json
import re
from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Mode = Literal["car", "train", "bus", "bike", "walk"]

NS_STATION_CODE = re.compile(r"^[A-Z]{2,6}$")


class CommuteLeg(BaseModel):
    """One leg of a commute, written in the to-work direction"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Mode
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    # Time needed to switch from this leg to the next one (parking, walking to the platform, ...)
    transfer_minutes: int = Field(default=0, ge=0, le=120)

    @model_validator(mode="after")
    def check_train_station_codes(self) -> "CommuteLeg":
        if self.mode == "train":
            for code in (self.from_, self.to):
                if not NS_STATION_CODE.match(code):
                    raise ValueError(f"train legs need NS station codes like 'UT', got '{code}'")
        return self


class Commute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    legs: List[CommuteLeg] = Field(min_length=1)


class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    commutes: List[Commute] = Field(min_length=1)

    @model_validator(mode="after")
    def check_unique_commute_ids(self) -> "Person":
        ids = [commute.id for commute in self.commutes]
        duplicates = sorted({commute_id for commute_id in ids if ids.count(commute_id) > 1})
        if duplicates:
            raise ValueError(f"commute ids must be unique, duplicated: {', '.join(duplicates)}")
        return self


class PeopleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    people: Dict[str, Person] = Field(min_length=1)


def load_people_config(path: str) -> PeopleConfig:
    """Load and validate the people config, failing loudly so a broken file stops the app at startup"""
    try:
        with open(path, encoding="utf-8") as config_file:
            data = json.load(config_file)
    except FileNotFoundError:
        raise ValueError(f"People config not found at '{path}' (set PEOPLE_CONFIG)") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"People config '{path}' is not valid JSON: {e}") from None

    try:
        return PeopleConfig.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"People config '{path}' is invalid:\n{e}") from None
