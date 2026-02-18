from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.router_plan import router as plan_router
from app.router_users import router as users_router
from app.router_routines import router as routines_router

app = FastAPI(debug=True)

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(plan_router)
app.include_router(users_router)
app.include_router(routines_router)


@app.get("/health")
def health():
    return {"ok": True}
