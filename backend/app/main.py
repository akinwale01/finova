from fastapi import FastAPI

app = FastAPI(
    title="Finova API",
    description="Personal finance and investment management API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "Welcome to Finova API"
    }