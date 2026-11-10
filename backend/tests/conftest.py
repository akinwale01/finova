import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import DATABASE_URL, TEST_DATABASE_URL


# Never allow integration tests to fall back to the development database.
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is not configured. "
        "Refusing to run integration tests."
    )

test_url = make_url(TEST_DATABASE_URL)
development_url = make_url(DATABASE_URL)

# Prevent tests from connecting to the same PostgreSQL database
# used by the application.
if (
    test_url.host == development_url.host
    and test_url.port == development_url.port
    and test_url.database == development_url.database
):
    raise RuntimeError(
        "TEST_DATABASE_URL points to the development database. "
        "Use a separate database for integration tests."
    )

if not test_url.drivername.startswith("postgresql"):
    raise RuntimeError(
        "Integration tests must use PostgreSQL."
    )


engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)



def clean_test_data(session: Session) -> None:
    """
    Remove data created by the integration test suite.

    Tests intentionally exercise service methods that commit
    transactions, so a normal session.rollback() cannot isolate
    tests after those commits.

    Only application data is removed. The database schema itself
    is never dropped or recreated.
    """
    session.execute(
        text(
            """
            TRUNCATE TABLE
                scheduled_transactions,
                transactions,
                holdings,
                assets,
                portfolios,
                accounts,
                users
            RESTART IDENTITY CASCADE
            """
        )
    )

    session.commit()


@pytest.fixture
def db() -> Session:
    """
    Provide a clean PostgreSQL session for each test.

    The database is cleaned before and after every test because
    the services under test are allowed to commit their own
    transactions.
    """
    session = TestingSessionLocal()

    try:
        clean_test_data(session)
        yield session
        clean_test_data(session)
    finally:
        session.close()