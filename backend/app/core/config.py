import os

from dotenv import load_dotenv


load_dotenv()


# =========================================================
# DATABASE
# =========================================================

# Used by the FastAPI application.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL is not configured. "
        "Please set DATABASE_URL in your .env file."
    )

# Used exclusively by PostgreSQL integration tests.
# It is optional here so the application can run without test configuration.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


# =========================================================
# AUTHENTICATION
# =========================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY is not configured. "
        "Please set JWT_SECRET_KEY in your .env file."
    )


JWT_ALGORITHM = os.getenv(
    "JWT_ALGORITHM",
    "HS256",
)


ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "30",
    )
)
