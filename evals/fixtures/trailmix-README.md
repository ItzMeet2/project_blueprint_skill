# Trailmix

Trailmix is a small web app for planning group hiking trips. One person creates a trip, invites friends by email, and everyone sees the same packing list and itinerary.

## The problem

Groups plan hikes in chat threads. Packing lists get lost, nobody knows who is bringing the stove, and the route is a screenshot buried 200 messages up.

## Who it is for

- **Organizers** who plan the trip and invite people.
- **Hikers** who join a trip and tick off what they will bring.

## Planned features

- Create a trip with a name, dates, and a meeting point.
- Invite friends by email; invited people join with a link.
- Shared packing list: anyone can add an item and claim it ("I'll bring the stove").
- Day-by-day itinerary with distance and estimated hours per day.
- A read-only trip summary page that can be shared.

## Not planned for the first version

- Maps or GPS tracking.
- Payments or expense splitting.
- Native mobile apps.

## Tech

Node.js with Express, PostgreSQL, and server-rendered pages. Deployed on a single small server.

## Status

Idea stage: only this README and a rough database sketch (users, trips, trip members, packing items) exist so far.
