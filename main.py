from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from commute import CommuteResponse, Direction, plan_person
from people_config import load_people_config

# Load environment variables
load_dotenv()

app = FastAPI(title="Ecosystem API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev server
        "https://freekgorrissen.github.io",  # Production client
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600  # Cache preflight requests for 1 hour
)

# The NS and Google Maps clients read their keys from the environment; check them at startup
if not os.getenv("GOOGLE_MAPS_API_KEY") or not os.getenv("NS_API_KEY"):
    raise ValueError("Missing required API keys in environment variables")

PEOPLE = load_people_config(os.getenv("PEOPLE_CONFIG", "people.json")).people


@app.get("/api/commute/{person_id}")
def get_commute(person_id: str, direction: Direction) -> CommuteResponse:
    """Plan every commute option for one person, leaving now"""
    person = PEOPLE.get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Unknown person '{person_id}'")
    return plan_person(person_id, person, direction)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
