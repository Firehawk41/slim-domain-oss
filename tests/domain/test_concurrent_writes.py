"""Proves the 2026-09-24 fix for a real bug found via a live stress test
against the deployed Slim-LIMS service: sharing ONE SQLAlchemy Session
across concurrent requests (FastAPI runs sync routes on a real
threadpool) crashed with sqlalchemy.exc.InvalidRequestError('Session is
already flushing'), and could silently drop an unrelated thread's
uncommitted write when another thread's insert failed and rolled back.

Each repository's write methods now accept an optional `engine` --
when set, every write opens its own short-lived session instead of
sharing one. These tests build a REAL multi-threaded race (not a
simulated one) against a real temp-file SQLite database, each thread
getting its own genuine connection -- deliberately NOT a plain
"sqlite:///:memory:" engine (every new Session there gets a blank,
separate in-memory DB, making this look broken when it isn't) and NOT
StaticPool either (StaticPool shares ONE physical connection across every
session, so "concurrent" writers still serialize on that single
connection's own transaction state -- not a real stand-in for Postgres's
actual per-connection pool, which is what production uses). A generous
busy_timeout lets SQLite's own single-writer-at-a-time lock queue
concurrent writers instead of raising "database is locked" -- the
invariant under test is "no crash, no lost write," not "truly
simultaneous," since even Postgres serializes conflicting writes via row
locks/MVCC.
"""
import concurrent.futures
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure.database import Base
from slim_domain.domain.analysis.analysis_repository import AnalysisRepository, _AnalysisRow
from slim_domain.domain.chemical.chemical_repository import ChemicalRepository
from slim_domain.domain.customer.customer_repository import CustomerRepository
from slim_domain.domain.report_folder.report_folder_repository import ReportFolderRepository, _CustomerReportFolderRow
from slim_domain.domain.customer.customer_repository import _CustomerRow


def _real_file_engine(tmp_path: Path):
    db_path = tmp_path / f"test_{id(tmp_path)}.db"
    return create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})


def _customer_kwargs(name: str) -> dict:
    return dict(
        name=name, street_address="1 Test St", city="Testville",
        state="TX", postal_code="00000", country="USA", created_by="JT",
    )


def test_customer_repository_concurrent_distinct_creates_all_persist(tmp_path):
    engine = _real_file_engine(tmp_path)
    Base.metadata.create_all(engine)
    repo = CustomerRepository(Session(engine), engine=engine)

    names = [f"Concurrent Customer {i}" for i in range(5)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(repo.insert, **_customer_kwargs(n)) for n in names]
        results = [f.result() for f in futures]  # re-raises if any thread failed

    assert len(results) == 5
    with Session(engine) as check:
        count = check.query(_CustomerRow).count()
    assert count == 5


def test_customer_repository_concurrent_name_collision_does_not_eat_the_others(tmp_path):
    """Reproduces the exact real scenario from the live stress test: one
    colliding pair (same name, forces an IntegrityError on one of them)
    fired alongside unrelated, distinct creates. The distinct ones must
    all persist regardless of the collision's outcome -- the original bug
    silently dropped an unrelated customer's insert as collateral damage."""
    engine = _real_file_engine(tmp_path)
    Base.metadata.create_all(engine)
    repo = CustomerRepository(Session(engine), engine=engine)

    jobs = ["Collide", "Collide", "Distinct A", "Distinct B", "Distinct C"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(repo.insert, **_customer_kwargs(n)) for n in jobs]
        outcomes = []
        for f in futures:
            try:
                outcomes.append(("ok", f.result()))
            except ValueError as e:
                outcomes.append(("rejected", str(e)))

    # Exactly one of the two "Collide" submissions succeeds, one is cleanly
    # rejected -- neither raises an unhandled InvalidRequestError.
    with Session(engine) as check:
        assert check.query(_CustomerRow).filter_by(customer_name="Collide").count() == 1
        for name in ("Distinct A", "Distinct B", "Distinct C"):
            assert check.query(_CustomerRow).filter_by(customer_name=name).count() == 1, (
                f"{name} should have persisted regardless of the unrelated collision"
            )


def test_chemical_repository_concurrent_distinct_creates_all_persist(tmp_path):
    engine = _real_file_engine(tmp_path)
    Base.metadata.create_all(engine)
    repo = ChemicalRepository(Session(engine), engine=engine)

    def make(name: str):
        return repo.insert(
            name=name, metals_prep="N/A", silicon_prep="N/A", ions_prep="N/A",
            ked_element_ids=frozenset(), created_by="JT",
        )

    names = [f"Concurrent Chemical {i}" for i in range(5)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = [f.result() for f in [ex.submit(make, n) for n in names]]

    assert len({r.id for r in results}) == 5  # 5 distinct real rows, no lost/duplicate IDs


def test_analysis_repository_concurrent_form_mappings_all_persist(tmp_path):
    engine = _real_file_engine(tmp_path)
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        seed.add(_AnalysisRow(id=1, analysis_name="36 Elements", analysis_description=None))
        seed.commit()
    repo = AnalysisRepository(Session(engine), engine=engine)

    form_names = [f"Concurrent Form {i}" for i in range(5)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(lambda n: repo.insert_form_analysis(n, 1), form_names))

    assert sorted(dict(repo.select_all_form_analyses()).keys()) == sorted(form_names)


def test_report_folder_repository_concurrent_upserts_for_different_customers_all_persist(tmp_path):
    engine = _real_file_engine(tmp_path)
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        for i in range(5):
            seed.add(_CustomerRow(
                id=i + 1, customer_name=f"Folder Customer {i}", street_address="1 St",
                city="T", state="TX", postal_code="0", country="USA",
            ))
        seed.commit()
    repo = ReportFolderRepository(Session(engine), engine=engine)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(lambda i: repo.upsert(i + 1, f"C:/reports/{i}", created_by="JT"), range(5)))

    with Session(engine) as check:
        assert check.query(_CustomerReportFolderRow).count() == 5


def test_engine_none_falls_back_to_shared_session_unchanged():
    """The default path (no engine supplied) must behave exactly as it did
    before this fix existed -- every pre-existing test already proves
    this implicitly (none of them pass engine=), this makes it explicit."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = CustomerRepository(session)  # no engine= -- old behavior

    customer = repo.insert(**_customer_kwargs("Solo Customer"))

    assert customer.name == "Solo Customer"
    assert session.query(_CustomerRow).count() == 1
