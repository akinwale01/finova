import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATABASE_URL


engine = create_engine(
    DATABASE_URL,
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