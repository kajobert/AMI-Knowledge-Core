# Security policy

AMI Knowledge Core treats provenance data, raw evidence, credentials and production configuration as sensitive by default.

## Reporting

Do not publish real credentials, personal evidence, private logs, tokens or security-sensitive production details in a public issue. Use a private project channel for sensitive reports until a dedicated vulnerability-reporting route is configured.

## Repository rules

- Never commit secrets or real `.env` files.
- Use synthetic fixtures in tests.
- Keep raw evidence and user/private-source exports outside this repository.
- CI and pull-request validation must run without production credentials.
- External AI integrations are untrusted processors: bound their context and validate their outputs.
- No AI workflow may merge, deploy or promote knowledge to CANONICAL without an explicit policy/review gate.

See `docs/PUBLICATION_POLICY.md` for the public/private repository boundary.
