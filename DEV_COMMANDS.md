# Rutinas DS — Development Commands

This document defines the correct commands to run the project locally.

Environment: Windows 11

Project root:
C:\rutinas_ds

---

## Backend (FastAPI)

### Location

C:\rutinas_ds\backend


### Activate virtual environment

PowerShell:

cd C:\rutinas_ds\backend
..venv\Scripts\activate


Expected result:

(.venv) PS C:\rutinas_ds\backend>


---

### Run backend server
uvicorn main:app --reload --port 8001


Backend URL:

http://127.0.0.1:8001


Swagger docs:
http://127.0.0.1:8001/docs


---

### Install dependencies (only first time)

pip install -r requirements.txt


---

## Frontend (Next.js)

### Location
C:\rutinas_ds\frontend


### Install dependencies (first time only)

npm install


---

### Run frontend

npm run dev


Frontend URL:
http://localhost:3000


---

## Environment Notes

- Python version: 3.11.x
- Node version: LTS (18 or 20)
- Database: Supabase PostgreSQL (remote)
- Backend must run before frontend login works.

---

## Common Issues

### Backend fails with bcrypt error
Install compatible version:

pip install bcrypt==4.0.1


### Frontend cannot reach backend
Check API URL in:

frontend/lib/api.ts


Expected:
http://127.0.0.1:8001


---

## Development Rule

Backend is the source of truth for business logic.
Frontend must not replicate routine logic.