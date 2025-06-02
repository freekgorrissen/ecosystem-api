# Ecosystem API

This is the backend API service for the Ecosystem application, providing endpoints for train and maps data.

## Setup

1. Create a `.env` file in the root directory with the following variables:
```
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
NS_API_KEY=your_ns_api_key
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the development server:
```bash
uvicorn main:app --reload
```

## API Endpoints

### Train Data
- `GET /api/train/stations` - Get all train stations
- `GET /api/train/departures/{station_code}` - Get departures for a specific station

### Maps Data
- `GET /api/maps/geocode?address={address}` - Geocode an address
- `GET /api/maps/directions?origin={origin}&destination={destination}&mode={mode}` - Get directions

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