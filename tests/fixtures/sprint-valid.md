# Sprint Plan: BookShelf

Sprint length: 2 weeks

## Sprint 1

**Goal:** A reader can sign in and see their books.

Capacity: 20
Planned: 16

| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
|----|------|-------|--------|----------|------------|--------|---------------------|
| US-001 | Auth | As a reader, I can sign in | 3 | Must | — | 1 | Given valid creds, when I submit, then I land on My Books |
| US-002 | Books | As a reader, I can see my books | 5 | Must | US-001 | 1 | Given I own 2 books, when I open My Books, then both are listed |
| US-003 | Books | As a reader, I can add a book \| with an ISBN | 8 | Should | US-002 | 1 | Given a title, when I save, then it appears in the list |

### Risks

| Risk | Impact |
|------|--------|
| Auth is not implemented yet | High |

## Sprint 2

Capacity: 10

| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
|----|------|-------|--------|----------|------------|--------|---------------------|
| US-004 | Reviews | As a reader, I can review a book | 5 | Could | US-003 | 2 | Given a book, when I rate it 4, then the rating shows |
| US-005 | Books | As a reader, I can delete a book | 3 | Won't | US-002, US-003 | 2 | Given a book, when I delete it, then it is gone |

Example of the format (inside a code fence, so it must be ignored):

```markdown
| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
|----|------|-------|--------|----------|------------|--------|---------------------|
| US-001 | Dup | This duplicate ID must be ignored | 99 | Maybe | — | 9 | ignored |
```
