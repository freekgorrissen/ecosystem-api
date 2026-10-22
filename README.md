# Ecosystem API

This is the backend API service for the Ecosystem application. It plans expected commute times by car and public transport, comparing several commute options per person.

## Setup

1. Create a `.env` file in the root directory (see `.env.example`):
```
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
NS_API_KEY=your_ns_api_key
PEOPLE_CONFIG=people.json
```

2. Create `people.json` with each person's commute options (see `people.example.json`). It contains real addresses, so it's gitignored and kept out of the Docker image.

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the development server:
```bash
uvicorn main:app --reload
```

## API Endpoints

- `GET /api/commute/{person}?direction=to_work|to_home` - Plan every commute option for a person, leaving now: total time, departure and arrival per leg, and train disruptions

Train legs come from the NS API; car, bike, walking and bus legs from Google Maps.

## Deployment to Google Cloud Run

1. Build the Docker image:
```bash
docker build -t gcr.io/[PROJECT_ID]/ecosystem-api .
```

2. Push to Google Container Registry:
```bash
docker push gcr.io/[PROJECT_ID]/ecosystem-api
```

3. Deploy to Cloud Run:
```bash
gcloud run deploy ecosystem-api \
  --image gcr.io/[PROJECT_ID]/ecosystem-api \
  --platform managed \
  --region [REGION] \
  --allow-unauthenticated
```

Make sure to set the environment variables in Google Cloud Run:
- `GOOGLE_MAPS_API_KEY`
- `NS_API_KEY`
- `PEOPLE_CONFIG` (path of the mounted `people.json`)
