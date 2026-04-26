# External Intelligence Architecture

This bounded context is the compliant backbone for discovering public business contact signals and preparing human-approved outreach.

## Principles

- Use official APIs or user-provided text first.
- Keep source, job, lead, contact point, and outreach draft as separate records.
- Store provenance for every discovered record.
- Never bypass authentication, paywalls, CAPTCHAs, rate limits, robots policies, or browser safety warnings.
- Do not send messages automatically. The system creates drafts; an operator must approve any real communication.
- Avoid private or sensitive personal data collection. Prefer public business listings and first-party CRM data.

## Flow

1. User or operator writes a natural-language request.
2. The agent extracts company/category, location, purpose, and a search query.
3. The resolver checks curated public sources first.
4. If no actionable contact is found, the resolver falls back to Google Places Text Search.
5. Connector returns lead candidates with provenance and confidence.
6. Service normalizes contact points such as phone and email.
7. Operator can create an `OutreachDraft`.
8. A future approval/sending service can integrate CRM, email, SMS, or call-center tools.

## Extension Points

- `intelligence_connectors.py`: add official API adapters.
- `intelligence_service.py`: orchestration, policy checks, persistence, audit logging.
- `api/routes/intelligence.py`: authenticated API surface.
- `models/entities.py`: persistence model.

## Current Connectors

- `manual`: parses user-provided text locally.
- `google_places`: safe placeholder for an official Google Places adapter.
- `google_places`: official Google Places Text Search adapter. Enable with
  `GOOGLE_PLACES_API_KEY` and `INTELLIGENCE_EXTERNAL_ENABLED=true`.
- `reddit_api`: safe placeholder for an official Reddit API adapter.
- `x_api`: safe placeholder for an official X API adapter.

External API collection is intentionally disabled by default via `INTELLIGENCE_EXTERNAL_ENABLED=false` until API keys, policy review, and rate-limit controls are configured.
