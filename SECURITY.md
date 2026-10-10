# Security review notes

These notes describe the current API implementation. They are not a penetration test or a production security certification.

## Controls in place

- Passwords are hashed with bcrypt. Registration validates password length and rejects inputs above bcrypt's 72-byte limit.
- Signed access tokens expire and include a token ID. Logout records the token ID as revoked.
- Document routes filter by the authenticated user's ID.
- Uploads are limited by file size, PDF signature, page count, and extracted character count. Failed uploads are cleaned up.
- Upload requests require a per-user idempotency key. A completed request with the same key does not repeat document ingestion.
- Questions have a length limit, and retrieval count is bounded.
- CORS uses explicit origins from configuration. Wildcard origins are rejected.
- Runtime secret configuration is read from environment variables. Local environment files are ignored by Git, except for the example template.
- Current request handlers use SQLAlchemy ORM queries rather than constructing SQL from user-provided strings.

## Attack surfaces

### SQL injection and NoSQL injection

The current database code uses SQLAlchemy ORM filters for user, document, and chunk queries. No NoSQL client or query layer is present. Keep future raw SQL parameterized if raw SQL becomes necessary.

### Server-side template injection

The API does not render user-provided templates or expose a server-side template feature. SSTI is not a current request-path feature. Reassess this if template rendering is introduced.

### ReDoS

The API does not accept user-supplied regular expressions. Idempotency keys are checked against a small, fixed ASCII character allowlist and bounded length. Reassess if user-controlled regex support is added.

### Secret exposure

Set `SECRET_KEY` and `GEMINI_API_KEY` through environment configuration. Never put real keys in source files, example files, logs, or pull request descriptions. If a key was committed at any point, rotate it and review the repository history. Adding an ignore rule does not remove a secret from existing commits.

### Replay attacks

Upload idempotency keys prevent duplicate ingestion work for the same user and key while the key remains valid. Logout revokes the corresponding access token. These controls do not make bearer tokens non-replayable: a copied token may be used until it expires or is revoked. Use HTTPS and avoid exposing tokens in logs or URLs.

### HTTP resource exhaustion

Requests are rate limited by peer IP and route group. Upload size, page count, extracted text length, question length, and retrieval count are capped. The rate limiter is in-process and has a bounded tracking map. It is not a distributed rate limiter or network-level DDoS defense. Put a trusted gateway or shared rate limit store in front of multi-worker or public deployments.

### Clipboard attacks

The backend has no clipboard feature and does not access browser clipboard contents. Clipboard handling, if introduced in a frontend, needs a separate client-side review.

## Operational notes

- Restrict production `CORS_ORIGINS` to the actual frontend origins.
- Replace the example signing key before deployment.
- Use HTTPS for external traffic.
- Keep API keys out of logs and rotate them if they may have been exposed.
- Configure gateway-level request limits for public deployments.
