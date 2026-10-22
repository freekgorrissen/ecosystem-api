"""Plans commute options leg by leg, chaining each leg onto the previous one"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, NamedTuple, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

import google_maps
import ns
from external_api import ExternalApiError
from people_config import Commute, Person

TZ = ZoneInfo("Europe/Amsterdam")
GOOGLE_TRAVEL_MODES = {"car": "driving", "bike": "bicycling", "walk": "walking"}
SCHEDULED_MODES = {"train", "bus"}
UNUSABLE_TRIP_STATUSES = {"CANCELLED", "CHANGE_NOT_POSSIBLE"}

Direction = Literal["to_work", "to_home"]


class Disruption(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = None


class LegResult(BaseModel):
    mode: str
    from_: str = Field(serialization_alias="from")
    to: str
    departure: datetime
    arrival: datetime
    service: Optional[str] = None
    disruptions: List[Disruption] = []


class CommuteOption(BaseModel):
    id: str
    name: str
    departure: Optional[datetime] = None
    arrival: Optional[datetime] = None
    total_minutes: Optional[int] = None
    legs: List[LegResult] = []
    error: Optional[str] = None


class CommuteResponse(BaseModel):
    person: str
    direction: Direction
    options: List[CommuteOption]


class Step(NamedTuple):
    """A leg in travel order, with the transfer time to the next step"""
    mode: str
    origin: str
    destination: str
    transfer_minutes: int


def plan_person(person_id: str, person: Person, direction: Direction) -> CommuteResponse:
    """Plan every commute option for one person, leaving now"""
    now = datetime.now(TZ).replace(microsecond=0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        options = list(pool.map(lambda commute: plan_commute(commute, direction, now), person.commutes))
    return CommuteResponse(person=person_id, direction=direction, options=options)


def plan_commute(commute: Commute, direction: Direction, now: datetime) -> CommuteOption:
    try:
        steps = steps_for(commute, direction)
        legs = leave_just_in_time(chain_legs(steps, now), steps)
    except ExternalApiError as e:
        return CommuteOption(id=commute.id, name=commute.name, error=str(e))

    departure, arrival = legs[0].departure, legs[-1].arrival
    return CommuteOption(
        id=commute.id,
        name=commute.name,
        departure=departure,
        arrival=arrival,
        total_minutes=round((arrival - departure).total_seconds() / 60),
        legs=legs,
    )


def steps_for(commute: Commute, direction: Direction) -> List[Step]:
    legs = commute.legs
    if direction == "to_work":
        return [Step(leg.mode, leg.from_, leg.to, leg.transfer_minutes) for leg in legs]

    # Going home runs the legs backwards. A transfer time belongs to the connection between
    # two legs, so it moves to the leg that now comes before that connection.
    reversed_legs = legs[::-1]
    return [
        Step(
            leg.mode,
            leg.to,
            leg.from_,
            reversed_legs[i + 1].transfer_minutes if i + 1 < len(reversed_legs) else 0,
        )
        for i, leg in enumerate(reversed_legs)
    ]


def chain_legs(steps: List[Step], now: datetime) -> List[LegResult]:
    """Plan each leg to start once the previous one has arrived and the transfer is done"""
    legs = []
    ready_at = now
    for step in steps:
        leg = plan_leg(step, ready_at)
        legs.append(leg)
        ready_at = leg.arrival + timedelta(minutes=step.transfer_minutes)
    return legs


def leave_just_in_time(legs: List[LegResult], steps: List[Step]) -> List[LegResult]:
    """Shift the legs before the first train or bus so you arrive just in time for it.

    Nobody leaves home now to wait 20 minutes on the platform. The car/bike/walk durations
    are kept as planned for "now"; traffic a few minutes later is close enough.
    """
    first_scheduled = next((i for i, step in enumerate(steps) if step.mode in SCHEDULED_MODES), None)
    if first_scheduled is None or first_scheduled == 0:
        return legs

    previous = first_scheduled - 1
    ready_at = legs[previous].arrival + timedelta(minutes=steps[previous].transfer_minutes)
    slack = legs[first_scheduled].departure - ready_at
    if slack <= timedelta(0):
        return legs

    shifted = [
        leg.model_copy(update={"departure": leg.departure + slack, "arrival": leg.arrival + slack})
        for leg in legs[:first_scheduled]
    ]
    return shifted + legs[first_scheduled:]


def plan_leg(step: Step, ready_at: datetime) -> LegResult:
    if step.mode == "train":
        return plan_train_leg(step, ready_at)
    if step.mode == "bus":
        return plan_bus_leg(step, ready_at)
    return plan_travel_leg(step, ready_at)


def plan_travel_leg(step: Step, ready_at: datetime) -> LegResult:
    """A car, bike or walking leg: leave when ready, arrive after Google's estimate"""
    # Google rejects departure times in the past
    departure_time = max(ready_at, datetime.now(TZ))
    route = google_maps.directions(
        step.origin,
        step.destination,
        GOOGLE_TRAVEL_MODES[step.mode],
        departure_time=int(departure_time.timestamp()),
    )
    # Only car routes have a traffic estimate
    duration = route.get("duration_in_traffic", route["duration"])["value"]
    return LegResult(
        mode=step.mode,
        from_=step.origin,
        to=step.destination,
        departure=ready_at,
        arrival=ready_at + timedelta(seconds=duration),
    )


def plan_bus_leg(step: Step, ready_at: datetime) -> LegResult:
    """The first bus from stop to stop that leaves after ready_at"""
    departure_time = max(ready_at, datetime.now(TZ))
    route = google_maps.directions(
        step.origin,
        step.destination,
        "transit",
        transit_mode="bus",
        departure_time=int(departure_time.timestamp()),
    )
    # Skip Google's walking steps to and from the stops: we plan stop to stop
    rides = [route_step["transit_details"] for route_step in route["steps"] if route_step.get("travel_mode") == "TRANSIT"]
    if not rides:
        raise ExternalApiError(f"No bus found from '{step.origin}' to '{step.destination}'")

    return LegResult(
        mode=step.mode,
        from_=step.origin,
        to=step.destination,
        departure=datetime.fromtimestamp(rides[0]["departure_time"]["value"], TZ),
        arrival=datetime.fromtimestamp(rides[-1]["arrival_time"]["value"], TZ),
        service=" → ".join(_transit_line_name(ride["line"]) for ride in rides),
    )


def plan_train_leg(step: Step, ready_at: datetime) -> LegResult:
    """The first usable NS trip that leaves after ready_at, using real-time times where known"""
    for trip in ns.get_trips(step.origin, step.destination, ready_at):
        if trip.get("status") in UNUSABLE_TRIP_STATUSES or not trip.get("legs"):
            continue
        departure = _ns_time(trip["legs"][0]["origin"])
        if departure < ready_at:
            continue

        rides = [leg for leg in trip["legs"] if leg.get("travelType") == "PUBLIC_TRANSIT"]
        services = [ride.get("product", {}).get("longCategoryName") for ride in rides]
        return LegResult(
            mode=step.mode,
            from_=step.origin,
            to=step.destination,
            departure=departure,
            arrival=_ns_time(trip["legs"][-1]["destination"]),
            service=" → ".join(service for service in services if service) or None,
            disruptions=_trip_disruptions(trip),
        )

    raise ExternalApiError(
        f"No train found from {step.origin} to {step.destination} after {ready_at:%H:%M}"
    )


def _transit_line_name(line: Dict[str, Any]) -> str:
    vehicle = line.get("vehicle", {}).get("name", "Bus")
    number = line.get("short_name") or line.get("name") or ""
    return f"{vehicle} {number}".strip()


def _ns_time(stop: Dict[str, Any]) -> datetime:
    timestamp = stop.get("actualDateTime") or stop["plannedDateTime"]
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z").astimezone(TZ)


def _trip_disruptions(trip: Dict[str, Any]) -> List[Disruption]:
    """The disruption and maintenance messages NS attaches to this particular trip"""
    messages = [(trip.get("primaryMessage") or {}).get("message")]
    messages += trip.get("messages", [])
    for leg in trip["legs"]:
        messages += leg.get("messages", [])

    disruptions: Dict[str, Disruption] = {}
    for message in messages:
        if not message:
            continue
        key = message.get("id") or message.get("head") or ""
        disruptions.setdefault(key, Disruption(
            title=message.get("head") or "Unknown disruption",
            description=message.get("text"),
            type=message.get("type"),
        ))
    return list(disruptions.values())
