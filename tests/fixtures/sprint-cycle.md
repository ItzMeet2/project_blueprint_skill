# Sprint Plan: Cycle

## Sprint 1

| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
|----|------|-------|--------|----------|------------|--------|---------------------|
| US-001 | Auth | As a user, I can sign in | 3 | Must | US-003 | 1 | Given valid creds, then I am in |
| US-002 | Auth | As a user, I can sign out | 2 | Must | US-001 | 1 | Given a session, then I am out |
| US-003 | Auth | As a user, I can reset my password | 3 | Should | US-002 | 1 | Given an email, then I get a link |
