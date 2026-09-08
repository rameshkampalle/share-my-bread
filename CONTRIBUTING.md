# Contribution Guide

## Working Model

All components are cloud hosted. GitHub is the source of truth for code, database scripts, prompts, workflow exports, evaluation datasets and documentation.

## Branches

Use one feature branch per workstream:

- `feature/frontend`
- `feature/backend`
- `feature/database`
- `feature/n8n`
- `feature/ai-evals`
- `feature/testing-docs`

## Before Stopping Work

Every contributor must:

1. Commit and push the latest stable changes.
2. Record the branch and commit.
3. Export changed n8n workflows to `automation/workflows`.
4. Save database changes as sequential SQL migrations.
5. Save evaluation inputs and results under `evals`.
6. Document blockers and the next exact action.
7. Verify that no secret was committed.

## Definition of Done

A task is complete only when:

- It runs in the shared cloud environment.
- Its source or exported configuration is committed.
- Relevant tests pass.
- Completion evidence is recorded.
- Another contributor can continue the work.
- No credentials are stored in GitHub.

## Security

Never commit:

- API keys
- Passwords
- Access tokens
- Database credentials
- Supabase service-role keys
- n8n webhook secrets
- Environment files containing real values

Use cloud-platform secret stores for sensitive configuration.

## Pull Requests

A pull request should state:

- What changed
- How it was tested
- Cloud URL or execution ID
- Known limitations
- Screenshots where applicable
