# Sprint Plan: Over capacity

## Sprint 1

Capacity: 10

| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
|----|------|-------|--------|----------|------------|--------|---------------------|
| US-001 | Auth | As a user, I can sign in | 8 | Must | — | 1 | Given valid creds, then I am in |
| US-002 | Auth | As a user, I can sign out | 5 | Must | US-001 | 1 | Given a session, then I am out |

## Sprint 2

Capacity: 10

| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
|----|------|-------|--------|----------|------------|--------|---------------------|
| US-003 | Auth | As a user, I can reset my password | 8 | Should | US-001 | 2 | Given an email, then I get a link |
| US-004 | Auth | As a user, I can change my email | 3 | Could | — | 2 | Given a new email, then it is saved |
