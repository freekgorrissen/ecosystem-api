from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

# Load environment variables
load_dotenv()

app = FastAPI(title="Ecosystem API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev server
        "https://freekgorrissen.github.io"  # Production client
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600  # Cache preflight requests for 1 hour
)

# Get API keys from environment variables
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
NS_API_KEY = os.getenv("NS_API_KEY")

if not GOOGLE_MAPS_API_KEY or not NS_API_KEY:
    raise ValueError("Missing required API keys in environment variables")

class TrainStation(BaseModel):
    code: str
    name: str
    lat: float
    lng: float

class Route(BaseModel):
    fromStation: str
    toStation: str
    fromStationCode: Optional[str] = None
    toStationCode: Optional[str] = None

class Product(BaseModel):
    longCategoryName: str
    number: str

class Leg(BaseModel):
    name: str
    direction: str
    plannedDepartureTime: str
    plannedDepartureTrack: Optional[str] = None
    product: Optional[Product] = None

class Trip(BaseModel):
    idx: int
    plannedDurationInMinutes: int
    actualDurationInMinutes: Optional[int] = None
    transfers: int
    status: str
    legs: List[Leg]
    crowdForecast: Optional[str] = None
    punctuality: Optional[float] = None

class Disruption(BaseModel):
    id: str
    title: str
    isActive: bool
    impact: Dict[str, int]

class RouteResponse(BaseModel):
    routeKey: str
    trips: List[Trip]
    disruptions: List[Disruption]

class RouteRequest(BaseModel):
    routes: List[Route]
    max_journeys: int = 5
    is_reversed: bool = False

class CarRoute(BaseModel):
    id: int
    origin: str
    destination: str
    originName: str
    destinationName: str
    name: str

class CarRouteRequest(BaseModel):
    routes: List[CarRoute]
    is_reversed: bool = False

class CarTripResponse(BaseModel):
    id: int
    from_location: str
    to: str
    distance: str
    duration: str
    durationInTraffic: str
    traffic: str
    route: str
    fuelCost: str
    status: str = "NORMAL"

@app.get("/api/train/stations")
async def get_train_stations() -> List[TrainStation]:
    """Get all train stations from NS API"""
    try:
        headers = {"Ocp-Apim-Subscription-Key": NS_API_KEY}
        response = requests.get(
            "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v2/stations",
            headers=headers
        )
        response.raise_for_status()
        
        stations_data = response.json()
        stations = []
        
        for station in stations_data.get("payload", []):
            stations.append(TrainStation(
                code=station.get("code"),
                name=station.get("namen", {}).get("lang"),
                lat=station.get("lat"),
                lng=station.get("lng")
            ))
        
        return stations
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching train stations: {str(e)}")

@app.get("/api/maps/geocode")
async def geocode_address(address: str) -> Dict[str, Any]:
    """Geocode an address using Google Maps API"""
    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": address,
                "key": GOOGLE_MAPS_API_KEY
            }
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error geocoding address: {str(e)}")

@app.get("/api/maps/directions")
async def get_directions(
    origin: str,
    destination: str,
    mode: str = "transit"
) -> Dict[str, Any]:
    """Get directions using Google Maps API"""
    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params={
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "key": GOOGLE_MAPS_API_KEY
            }
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error getting directions: {str(e)}")

@app.get("/api/train/departures/{station_code}")
async def get_train_departures(station_code: str) -> Dict[str, Any]:
    """Get train departures for a specific station"""
    try:
        headers = {"Ocp-Apim-Subscription-Key": NS_API_KEY}
        response = requests.get(
            f"https://gateway.apiportal.ns.nl/reisinformatie-api/api/v2/departures?station={station_code}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching departures: {str(e)}")

@app.post("/api/trains/rail_routes")
async def get_train_routes(request: RouteRequest) -> List[RouteResponse]:
    """Get train routes and disruptions for multiple routes"""
    try:
        headers = {
            "Ocp-Apim-Subscription-Key": NS_API_KEY,
            "Accept": "application/json"
        }
        
        now = datetime.utcnow().isoformat()
        route_responses = []
        
        for route in request.routes:
            actual_from_station = route.toStation if request.is_reversed else route.fromStation
            actual_to_station = route.fromStation if request.is_reversed else route.toStation
            actual_from_station_code = route.toStationCode if request.is_reversed else route.fromStationCode
            actual_to_station_code = route.fromStationCode if request.is_reversed else route.toStationCode
            
            route_key = f"{actual_from_station}-{actual_to_station}"
            
            # Fetch trips
            trips_url = (
                f"https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/trips"
                f"?fromStation={actual_from_station}"
                f"&toStation={actual_to_station}"
                f"&dateTime={now}"
                f"&searchForArrival=false"
            )
            
            trips_response = requests.get(trips_url, headers=headers)
            trips_response.raise_for_status()
            trips_data = trips_response.json()
            
            # Transform trips
            transformed_trips = []
            if trips_data.get("trips"):
                for idx, trip in enumerate(trips_data["trips"][:request.max_journeys]):
                    legs = []
                    if trip.get("legs"):
                        for leg in trip["legs"]:
                            legs.append(Leg(
                                name=leg.get("product", {}).get("displayName") or 
                                     leg.get("product", {}).get("longCategoryName") or 
                                     "Train",
                                direction=leg.get("direction", ""),
                                plannedDepartureTime=leg.get("origin", {}).get("plannedDateTime") or 
                                                   leg.get("origin", {}).get("actualDateTime") or 
                                                   "",
                                plannedDepartureTrack=leg.get("origin", {}).get("plannedTrack"),
                                product=Product(
                                    longCategoryName=leg.get("product", {}).get("longCategoryName") or "Train",
                                    number=leg.get("product", {}).get("number") or ""
                                ) if leg.get("product") else None
                            ))
                    
                    transformed_trips.append(Trip(
                        idx=idx,
                        plannedDurationInMinutes=trip.get("plannedDurationInMinutes", 0),
                        actualDurationInMinutes=trip.get("actualDurationInMinutes"),
                        transfers=trip.get("transfers", 0),
                        status=trip.get("status", "NORMAL"),
                        legs=legs,
                        crowdForecast=trip.get("crowdForecast"),
                        punctuality=trip.get("punctuality")
                    ))
            
            # Fetch disruptions
            disruptions = []
            station_codes = [code for code in [actual_from_station_code, actual_to_station_code] if code]
            
            for station_code in station_codes:
                try:
                    disruption_url = f"https://gateway.apiportal.ns.nl/disruptions/v3/station/{station_code}"
                    disruption_response = requests.get(disruption_url, headers=headers)
                    if disruption_response.ok:
                        disruption_data = disruption_response.json()
                        if disruption_data.get("payload", {}).get("disruptions"):
                            for disruption in disruption_data["payload"]["disruptions"]:
                                if disruption.get("isActive"):
                                    disruptions.append(Disruption(
                                        id=disruption.get("id", ""),
                                        title=disruption.get("title", "Unknown disruption"),
                                        isActive=True,
                                        impact={"value": disruption.get("impact", {}).get("value", 1)}
                                    ))
                except requests.RequestException:
                    continue
            
            route_responses.append(RouteResponse(
                routeKey=route_key,
                trips=transformed_trips,
                disruptions=disruptions
            ))
        
        return route_responses
    
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching train routes: {str(e)}"
        )

@app.post("/api/car/road_routes")
async def get_car_routes(request: CarRouteRequest) -> List[CarTripResponse]:
    """Get car routes with traffic information"""
    try:
        current_routes = [
            {
                **route.dict(),
                "origin": route.destination if request.is_reversed else route.origin,
                "destination": route.origin if request.is_reversed else route.destination,
                "originName": route.destinationName if request.is_reversed else route.originName,
                "destinationName": route.originName if request.is_reversed else route.destinationName,
            }
            for route in request.routes
        ]

        trip_responses = []
        
        for route in current_routes:
            # Get distance matrix data
            distance_matrix_url = (
                "https://maps.googleapis.com/maps/api/distancematrix/json"
                f"?origins={route['origin']}"
                f"&destinations={route['destination']}"
                f"&mode=driving"
                f"&departure_time=now"
                f"&traffic_model=best_guess"
                f"&key={GOOGLE_MAPS_API_KEY}"
            )
            
            distance_matrix_response = requests.get(distance_matrix_url)
            distance_matrix_response.raise_for_status()
            distance_matrix_data = distance_matrix_response.json()
            
            if distance_matrix_data["status"] != "OK":
                raise HTTPException(
                    status_code=500,
                    detail=f"Distance Matrix API error: {distance_matrix_data['status']}"
                )
            
            element = distance_matrix_data["rows"][0]["elements"][0]
            distance = element["distance"]["text"]
            duration = element["duration"]["text"]
            duration_in_traffic = element.get("duration_in_traffic", {}).get("text", duration)
            
            # Get route details
            directions_url = (
                "https://maps.googleapis.com/maps/api/directions/json"
                f"?origin={route['origin']}"
                f"&destination={route['destination']}"
                f"&mode=driving"
                f"&key={GOOGLE_MAPS_API_KEY}"
            )
            
            directions_response = requests.get(directions_url)
            directions_response.raise_for_status()
            directions_data = directions_response.json()
            
            if directions_data["status"] != "OK":
                raise HTTPException(
                    status_code=500,
                    detail=f"Directions API error: {directions_data['status']}"
                )
            
            # Extract main roads from the route
            steps = directions_data["routes"][0]["legs"][0]["steps"]
            road_names = []
            
            for step in steps:
                instructions = step["html_instructions"]
                match = re.search(r"\b[A-Z]\d+\b", instructions)
                if match:
                    road_names.append(match.group(0))
                    if len(road_names) >= 3:
                        break
            
            route_description = " → ".join(road_names) if road_names else "Local roads"
            
            # Calculate traffic level
            duration_value = element["duration"]["value"]
            duration_in_traffic_value = element.get("duration_in_traffic", {}).get("value", duration_value)
            ratio = duration_in_traffic_value / duration_value
            
            if ratio > 1.4:
                traffic = "Heavy"
            elif ratio > 1.2:
                traffic = "Moderate"
            else:
                traffic = "Light"
            
            # Calculate fuel cost
            distance_value = float(re.sub(r'[^\d.]', '', distance))
            fuel_price_per_100km = 12  # Estimate €12 per 100km
            fuel_cost = f"€{((distance_value / 100) * fuel_price_per_100km):.2f}"
            
            trip_responses.append(CarTripResponse(
                id=route["id"],
                from_location=route["originName"],
                to=route["destinationName"],
                distance=distance,
                duration=duration,
                durationInTraffic=duration_in_traffic,
                traffic=traffic,
                route=route_description,
                fuelCost=fuel_cost
            ))
        
        return trip_responses
    
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching car routes: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 