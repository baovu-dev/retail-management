# KICKLAB

ASD 2026 Group 26 project - retail/shopping domain.

## Team
- Bao Vu - Reviews & Ratings
- Chai Eun Lee - Product Management
- Gordon Huang - Customer Accounts
- Taehyoun Lee - Order Management
- Aiden Phan - Chatbot/Recommendations

## Setup

You'll need Docker Desktop and Ollama installed.

1. Open Docker Desktop and make sure it's actually running (check for the
   whale icon in your menu bar) - `docker` commands will fail with a
   confusing error otherwise.
2. Pull a model and get Ollama running:
```
ollama pull llama3.1:8b
ollama serve
```

Leave `ollama serve` running in its own terminal, anything AI-related will fail to connect if it's not up.

## Running everything

```
docker compose up --build
```

This starts the shared login/dashboard and the five feature services. See the
[Orders runbook](student-4/README.md) for local configuration, host AI services,
service startup and verification. The browser uses localhost endpoints; services
inside Docker use Compose service names.

For an existing installation, back up data before rebuilding or recreating
containers. Orders now uses a persistent named volume and non-destructive startup;
old container databases require an explicit import. Reviews and Customers still
run seed initializers, so coordinate with their owners before restarting them.

You can also just run each individual feature on its own instead of the whole thing:

```
cd student-X (X can be any number of your choice from 1 to 5)
docker compose up --build
```

## Ports

Trying to keep these consistent across everyone's services - backend/frontend
combined on one port, database on another:

- Shared (login/home/dashboard): 5000 / 6000
- Student 1 (Reviews): 5001 / 6001
- Student 2 (Products): 5002 / 6002
- Student 3 (Customer Accounts): 5003 / 6003
- Student 4 (Orders): 5004 / 6004
- Student 5 (Chatbot): 5005 / 6005

Note some of us built frontend/backend as one combined service, others split
them into separate processes - both are fine, just means the port usage looks
a bit different per student.

## Folder structure

- `student-1/` to `student-5/` - each person's own feature
- `shared/` - login, homepage, staff dashboard, shared CSS
- `ai-services/` - shared AI stuff, mostly for release 1+
- `docs/` - reports and diagrams
- `docker-compose.yml` - runs the whole thing together

See the Orders runbook and retained evidence for the scope of verified flows.

## Release 1 Orders

See the [Orders runbook](student-4/README.md) and
[retained validation evidence](student-4/evidence/README.md). AI Mode/Ollama, MCP,
RAG and the agentic loop run locally outside Docker. Release 2 implementation
is a separate next phase.
