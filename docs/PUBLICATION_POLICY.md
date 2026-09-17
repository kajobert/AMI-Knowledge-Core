# AMI public module publication policy

AMI Knowledge Core is intended to be publishable as reusable infrastructure while private evidence and personal context remain outside public source repositories.

## Public-safe content

- application/library source code
- schemas and migrations that contain no real user data
- deterministic tests and synthetic fixtures
- architecture and protocol specifications written for publication
- CI workflows that reference secrets by name only
- sanitized examples with fake credentials and identifiers

## Never commit to public repositories

- raw ChatGPT/Gemini/Drive/NotebookLM exports
- personal conversations, private notes, contact data, or sensitive profile context
- production database dumps or evidence-vault contents
- API keys, tokens, passwords, private keys, cookies, session material, or real connection strings
- unredacted production logs
- private hostnames/IPs when disclosure is unnecessary
- deployment credentials or secret-bearing OpenClaw configuration

## Repository boundary

Recommended long-term split:

- `AMI-alpha`: private canonical project/evidence coordination layer
- raw evidence vault / archaeology exports: private and access-controlled
- deployment/configuration containing environment-specific sensitive data: private
- reusable sanitized modules such as `ami-knowledge-core`, AMI Kernel, AMI Protocol, and adapters: public when they pass publication review

Public does not imply that evidence becomes public. The Knowledge Core code may be public while its databases and ingested sources remain private.

## Pre-publication review

Before changing a repository from private to public:

1. review the complete Git history and all branches, not only the default branch;
2. search for secrets, tokens, credentials, personal data, private URLs and production logs;
3. review issues, pull requests, Actions logs and artifacts because those become publicly visible too;
4. ensure examples use synthetic data;
5. ensure `.env`, local databases, exports and evidence folders are ignored;
6. decide the intended software license explicitly;
7. enable GitHub secret scanning / push protection where available.

If a real secret was ever committed, removing it from the current tree is not enough. Revoke/rotate it first, then clean history if publication still makes sense.

## GitHub Actions

Current deterministic CI must not require repository secrets merely to lint, test, start PostgreSQL, or run synthetic fixtures.

Future external-AI workflows may use a repository/environment secret such as an OpenRouter API key. The secret value must never be stored in source. AI workflows should be explicitly triggered and should not receive secrets from untrusted fork pull requests.

Self-hosted production runners must not be attached to public pull-request workflows. Use GitHub-hosted runners for public untrusted contributions, or isolate any self-hosted runner behind explicit trusted-event policies.
