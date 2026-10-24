from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import StaticPool

from app.exceptions import FinovaError, NotFoundError
from app.services.base_service import BaseService


# ============================================================
# TEST DATABASE
# ============================================================

TestBase = declarative_base()


class DummyModel(TestBase):
    """
    Minimal model used only to test BaseService.

    This keeps the tests independent of Finova's actual
    production models.
    """

    __tablename__ = "dummy_base_service"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)


@pytest.fixture
def db():
    """
    Create an isolated in-memory SQLite database for each test.
    """

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestBase.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    TestBase.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def service(db):
    """
    BaseService configured against the dummy model.
    """

    service = BaseService[DummyModel](db)
    service.model = DummyModel

    return service


# ============================================================
# RETRIEVAL TESTS
# ============================================================


def test_get_by_id_returns_existing_record(db, service):
    record = DummyModel(name="Test Record")

    db.add(record)
    db.commit()
    db.refresh(record)

    result = service.get_by_id(record.id)

    assert result is not None
    assert result.id == record.id
    assert result.name == "Test Record"


def test_get_by_id_returns_none_for_missing_record(service):
    result = service.get_by_id(999999)

    assert result is None


def test_require_by_id_returns_existing_record(db, service):
    record = DummyModel(name="Required Record")

    db.add(record)
    db.commit()
    db.refresh(record)

    result = service.require_by_id(
        record.id,
        "DummyModel",
    )

    assert result.id == record.id


def test_require_by_id_raises_not_found(service):
    with pytest.raises(NotFoundError) as exc_info:
        service.require_by_id(
            999999,
            "DummyModel",
        )

    assert "DummyModel with id 999999 was not found." in str(
        exc_info.value
    )


def test_require_by_id_uses_model_name_when_resource_name_is_omitted(
    service,
):
    with pytest.raises(NotFoundError) as exc_info:
        service.require_by_id(999999)

    assert "DummyModel with id 999999 was not found." in str(
        exc_info.value
    )


# ============================================================
# ADD / FLUSH / REFRESH TESTS
# ============================================================


def test_add_places_record_in_session(db, service):
    record = DummyModel(name="Added Record")

    result = service.add(record)

    assert result is record
    assert record in db


def test_flush_persists_pending_insert_without_commit(db, service):
    record = DummyModel(name="Flushed Record")

    service.add(record)
    service.flush()

    assert record.id is not None

    # The record exists in the current transaction but the
    # transaction has not been committed yet.
    assert db.get(DummyModel, record.id) is record


def test_refresh_reloads_record(db, service):
    record = DummyModel(name="Original")

    db.add(record)
    db.commit()
    db.refresh(record)

    # Change the database directly using another connection
    # would complicate this isolated test, so verify that the
    # method returns the same persisted instance.
    result = service.refresh(record)

    assert result is record
    assert result.name == "Original"


# ============================================================
# COMMIT TESTS
# ============================================================


def test_commit_persists_record(db, service):
    record = DummyModel(name="Committed Record")

    service.add(record)
    result = service.commit(record)

    assert result is record
    assert record.id is not None

    persisted = db.get(DummyModel, record.id)

    assert persisted is not None
    assert persisted.name == "Committed Record"


def test_commit_without_record_returns_none(service):
    result = service.commit()

    assert result is None


# ============================================================
# DELETE TESTS
# ============================================================


def test_delete_marks_record_for_deletion(db, service):
    record = DummyModel(name="Delete Me")

    db.add(record)
    db.commit()
    db.refresh(record)

    service.delete(record)

    db.commit()

    assert db.get(DummyModel, record.id) is None


# ============================================================
# ROLLBACK TESTS
# ============================================================


def test_rollback_discards_pending_changes(db, service):
    record = DummyModel(name="Rollback Record")

    service.add(record)

    service.rollback()

    assert record not in db


# ============================================================
# COMMIT FAILURE TEST
# ============================================================


def test_commit_rolls_back_when_database_error_occurs(db, service):
    """
    Force a database failure by violating the NOT NULL constraint.
    """

    invalid_record = DummyModel(name=None)

    service.add(invalid_record)

    with pytest.raises(FinovaError) as exc_info:
        service.commit(invalid_record)

    assert "Database transaction failed." in str(
        exc_info.value
    )

    assert not db.in_transaction()