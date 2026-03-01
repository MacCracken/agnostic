# ADR-010: Security and Communication Encryption

## Status
Accepted

## Context
The system handles sensitive test data, API keys, and internal communication between agents. We need to ensure secure communication and data protection.

## Decision
Implement comprehensive security measures with:

1. **TLS Encryption** for all inter-service communication
2. **Certificate Management** with self-signed certificates for development
3. **Environment Variable Protection** for API keys and secrets
4. **Network Isolation** using Docker networks and Kubernetes namespaces
5. **Audit Logging** for security-relevant events

## Rationale
- **TLS Encryption** protects data in transit between all services
- **Certificate Management** enables production-ready security
- **Environment Variable Protection** prevents secret leakage
- **Network Isolation** limits attack surface between services
- **Audit Logging** provides security incident detection capabilities

## Consequences
- Increased operational complexity with certificate management
- Performance overhead from TLS encryption (minimal impact)
- Requires certificate rotation procedures
- Enhanced security posture suitable for enterprise deployment

## Implementation
- `docker-compose.tls.yml` for secure deployment configuration
- `certs/generate-certs.sh` for development certificate generation
- Environment variables for all sensitive configuration
- Docker networks and Kubernetes NetworkPolicies for isolation
- Security agent integration for ongoing security assessment

## Amendment: API layer hardening (2026-02-28)

Additional controls implemented across the WebGUI API layer:

1. **Path traversal prevention** (`webgui/api.py`) — `GET /reports/{id}/download` resolves the stored `file_path` with `Path.resolve()` and asserts `is_relative_to(_REPORTS_DIR)` before serving. Any path escaping `/app/reports` returns HTTP 403.

2. **Session ID sanitization** (`webgui/exports.py`) — session IDs are stripped of non-alphanumeric characters (`re.sub`) before being embedded in filenames, preventing directory traversal through the report generation path.

3. **Constant-time API key comparison** (`webgui/api.py`) — static `AGNOSTIC_API_KEY` comparison changed from `==` to `hmac.compare_digest()` to prevent timing side-channel attacks.

4. **Required RabbitMQ credentials** (`docker-compose.yml`) — `guest:guest` fallback defaults removed; `RABBITMQ_USER` and `RABBITMQ_PASSWORD` must be explicitly set. `.env.example` updated with non-default placeholder values.

5. **Security headers middleware** (`webgui/app.py`) — `SecurityHeadersMiddleware` adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and `Referrer-Policy: strict-origin-when-cross-origin` to every response.

6. **Input validation** (`webgui/api.py`) — `TaskSubmitRequest` enforces `max_length` on text fields (title: 200, description: 5000, business_goals/constraints: 500) and uses `Literal["critical","high","medium","low"]` for priority, rejecting unknown values with HTTP 422.