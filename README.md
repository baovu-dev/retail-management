# KICKLAB

# FEEL FREE TO EDIT - NOT FINALISED

ASD 2026 group project - retail/shopping domain. 

## Team
- Bao Vu - Reviews & Ratings
- Chai Eun Lee - Product Management
- Gordon Huang - Customer Accounts
- Taehyoun Lee - Order Management
- Aiden Phan - Chatbot/Recommendations

## Setup

You'll need Docker Desktop and Ollama installed. Pull a model before running
anything AI-related, e.g.

```
ollama pull llama3.1:8b
```

## Running everything

```
docker compose up --build
```

This should spin up all 5 features plus the shared login/dashboard stuff.
Still a work in progress - not every service is wired into this file yet,
check with whoever owns a feature if theirs isn't showing up.

You can also just run your own feature on its own instead of the whole thing:

```
cd student-1
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

Still Release 0, more to come.