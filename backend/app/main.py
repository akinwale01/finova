from fastapi import FastAPI

# Import the authentication router
from app.api.routes.auth import router as auth_router

# Import the portfolio router
from app.api.routes.portfolio import router as portfolio_router


# Create the FastAPI application
app = FastAPI(
    title="Finova API",
    description="Personal finance and investment management API",
    version="1.0.0",
)


# Register the authentication routes
app.include_router(auth_router)

# Register the portfolio routes
app.include_router(portfolio_router)


# Basic endpoint to confirm the API is running
@app.get("/")
def root():
    return {
        "message": "Welcome to Finova API"
    }