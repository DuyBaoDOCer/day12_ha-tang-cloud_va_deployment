# Deployment Information

## Public URL
https://day12-ha-tang-cloud-va-deployment-production.up.railway.app

## Platform
Railway

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
curl https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/health
```
**Expected Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "checks": {
    "llm": "mock"
  }
}
```

### 2. Readiness Check (Readiness Probe)
```bash
curl https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/ready
```
**Expected Response:**
```json
{
  "ready": true
}
```

### 3. API ask (Without Authentication Header)
```bash
curl -X POST https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is 2+2?"}'
```
**Expected Response:**
- Status Code: `401 Unauthorized`
- Body: `{"detail":"Invalid or missing API key. Include header: X-API-Key: <key>"}`

### 4. API ask (With Authentication Header)
*(Replace `YOUR_API_KEY` with the actual key set in your environment variables)*
```bash
curl -X POST https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/ask \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain Cloud Computing"}'
```
**Expected Response:**
- Status Code: `200 OK`
- Body:
```json
{
  "question": "Explain Cloud Computing",
  "answer": "Mock LLM Response to: Explain Cloud Computing",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T07:57:27.123456+00:00"
}
```

## Environment Variables Configured on Railway
- `PORT`: `8000`
- `AGENT_API_KEY`: `your-secret-api-key`
- `ENVIRONMENT`: `production`
- `REDIS_URL`: `redis://redis:6379/0` (or the dynamic service URL if running on Railway Redis)
- `DEBUG`: `false`
- `LLM_MODEL`: `gpt-4o-mini`

## Screenshots
![Deployment dashboard](screenshots/dashboard.png)
![Service running](screenshots/running.png)
![Test results](screenshots/test.png)
