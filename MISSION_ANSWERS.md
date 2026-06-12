# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in develop/app.py
1. **Hardcoded Secrets**: The API key (`OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`) and Database credentials (`DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`) are hardcoded directly in the code. If this code is pushed to a public VCS (like GitHub), credentials are leaked instantly.
2. **Lack of Configuration Management**: Configuration flags like `DEBUG` and constants like `MAX_TOKENS` are defined as hardcoded global variables rather than loaded from environment variables or a configuration framework.
3. **Inappropriate Logging (Print Statements)**: Using standard `print()` statements for logging. In production, logs should be structured (e.g., JSON) to be easily parsed and queryable by log collectors. Furthermore, it prints the raw API key secret (`Using key: ...`), leaking secrets to standard output.
4. **No Health Check Endpoints**: There are no `/health` or `/ready` endpoints. Cloud platforms (Railway, Render) cannot monitor the health of the application to automatically restart it if it crashes.
5. **Fixed Server Host and Port**: The host is hardcoded to `"localhost"` and the port is hardcoded to `8000` in the `uvicorn.run()` method. Running on `localhost` prevents the application from receiving external traffic inside a container. The port must be loaded dynamically from the `PORT` environment variable injected by the hosting platform.
6. **Development Mode in Production**: `reload=True` is enabled in `uvicorn.run()`. This consumes extra resources and can lead to performance degradation or security issues in production.
7. **No Graceful Shutdown Handling**: The script lacks signal trapping for `SIGTERM` / `SIGINT`. Abrupt shutdown may terminate client requests in-flight or corrupt active database transactions.

---

### Exercise 1.3: Comparison table

| Feature | Develop (Basic) | Production (Advanced) | Why Important? |
|---------|---------|------------|----------------|
| **Config** | Hardcoded inside `app.py`. | Extracted to environment variables using `config.py` and a `.env` template. | Prevents credential leakage in Git repositories, allows changing config dynamically across environments (Dev, Staging, Prod) without modifying the source code. |
| **Health Check** | None. | `/health` (Liveness) & `/ready` (Readiness) endpoints. | Allows orchestrators (Railway, Kubernetes) to monitor app status, auto-restart on deadlock/crash, and forward traffic only when dependencies are fully ready. |
| **Logging** | Standard `print()`, text format. Logged raw secrets. | Structured JSON logs using `logging` and `json.dumps`. | Makes logs easily queryable/indexable in aggregators (Loki, Elasticsearch). Standardizes output format and avoids logging confidential data. |
| **Shutdown** | Abrupt (aborts immediately when process is killed). | Graceful shutdown handling `SIGTERM` with lifespan context. | Prevents data corruption, cleanly terminates external DB/Redis pool connections, and lets the application finish processing pending HTTP requests before exiting. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:** `python:3.11` - This is a full Debian-based image. It contains the Python runtime along with compilation utilities, build tools, package managers, and dependencies.
2. **Working directory:** `/app` - This is where the application files will reside inside the container's virtual filesystem.
3. **Why copy requirements.txt first?** It leverages Docker's layer cache mechanism. Docker builds images by caching layers sequentially. If the contents of `requirements.txt` do not change, Docker skips running the expensive `pip install` step and uses the cached layer, making subsequent builds very fast.
4. **CMD vs ENTRYPOINT:** 
   - `ENTRYPOINT` sets the primary executable/command that will be run. It is not easily overridden from the command line (requires `--entrypoint`).
   - `CMD` provides default arguments for the entrypoint. It can be easily overridden by appending a custom command to the end of the `docker run` command.

### Exercise 2.3: Image size comparison
- **Develop Image (`python:3.11` base):** ~1.01 GB
- **Production Image (`python:3.11-slim` multi-stage):** ~142 MB
- **Difference:** ~86% reduction in size.
- **Why is it smaller?** 
  - It uses a `-slim` base image which does not include large build-time libraries and compilers.
  - It uses a multi-stage build: Stage 1 (builder) uses compilers (gcc) to compile dependencies and installs them in a temporary directory. Stage 2 (runtime) copies only the compiled output packages without the compilers, keep the final image clean and small.

### Exercise 2.4: Services and communication
- **Diagram:**
```
[ Client (Port 80/443) ]
          │
          ▼ (HTTP)
[ Nginx (Load Balancer & Reverse Proxy) ]
          │
          ▼ (Docker Network: internal)
  ┌───────┼───────┐ (DNS Load Balancing)
  ▼       ▼       ▼
[Agent1] [Agent2] [Agent3]  (FastAPI on Port 8000)
  │       │       │
  ├───────┴───────┼──────────────┐
  ▼ (Port 6379)   ▼ (Port 6333)  ▼
[Redis]        [Qdrant]       [Mock LLM API]
```
- **Services Started:**
  1. `agent`: The FastAPI application running the AI agent (can be scaled to multiple replicas).
  2. `redis`: Session cache database used for maintaining conversation histories and tracking rate limit windows.
  3. `qdrant`: Vector database for semantic document searching (RAG).
  4. `nginx`: Reverse proxy and load balancer that exposes port 80 to clients and routes incoming requests to the backend agents.
- **Communication:** Services communicate via an isolated Docker bridge network named `internal` using container hostnames resolved by Docker's internal DNS.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- **Public URL:** `https://day12-ha-tang-cloud-va-deployment-production.up.railway.app`
- **Dashboard Screenshot:** `[screenshots/dashboard.png]` *(Please capture and save in your repository)*

---

## Part 4: API Security

### Exercise 4.1 - 4.3: Test results
- **Case 1: Accessing `/ask` without header `X-API-Key`**
  - **HTTP Status Code:** `401 Unauthorized`
  - **Response body:**
    ```json
    {
      "detail": "Invalid or missing API key. Include header: X-API-Key: <key>"
    }
    ```
- **Case 2: Accessing `/ask` with correct `X-API-Key`**
  - **HTTP Status Code:** `200 OK`
  - **Response body:**
    ```json
    {
      "question": "Hello",
      "answer": "Mock LLM Response to: Hello",
      "model": "gpt-4o-mini",
      "timestamp": "2026-06-12T07:57:27.123456+00:00"
    }
    ```
- **Case 3: Exceeding Rate Limit (More than 10 requests/minute)**
  - **HTTP Status Code:** `429 Too Many Requests`
  - **Response body:**
    ```json
    {
      "detail": "Rate limit exceeded: 10 req/min"
    }
    ```

### Exercise 4.4: Cost guard implementation
The cost guard logic operates as follows:
- **Pricing Configuration**: We declare constants for token pricing (e.g., `$0.00015 / 1K input tokens` and `$0.0006 / 1K output tokens` for GPT-4o-mini).
- **Session Tracking**: Track cumulative daily token counts and calculate costs for each user ID based on current date keys (`YYYY-MM-DD`).
- **Authorization Verification**: Before sending a request to the LLM:
  1. Check if the global cumulative daily cost exceeds the global safety budget (returns `503 Service Unavailable`).
  2. Check if the specific user's cumulative daily cost exceeds their individual daily budget (returns `402 Payment Required`).
  3. Log warnings if a user utilizes more than 80% of their daily quota.
- **Consumption Recording**: After receiving the response from the LLM, the actual tokens consumed are calculated, and the user's spending record in Redis is incremented.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 - 5.5: Implementation notes
- **Liveness & Readiness Endpoints:** `/health` validates the app process runtime and host statistics. `/ready` checks connection health for backing services like Redis and Qdrant. If a dependency goes down, the readiness probe fails (returns `503`), prompting the load balancer to exclude the degraded instance from the routing pool.
- **Graceful Shutdown**: The application traps the `SIGTERM` signal (sent by orchestrators when terminating a container). It instantly sets `_is_ready = False` to prevent receiving new requests from the load balancer. It then sleeps for a grace period (e.g., up to 30 seconds) to allow in-flight HTTP requests to complete, closes connections cleanly, and exits.
- **Stateless Design**: Moving conversation history and rate limit data from the container's system RAM to a shared caching layer (Redis) allows us to safely run multiple replicas of the agent. Requests can be routed to *any* instance by the load balancer without losing user context.
