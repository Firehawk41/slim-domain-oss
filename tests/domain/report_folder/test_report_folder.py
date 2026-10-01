from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure.database import Base
from slim_domain.domain.customer.customer_repository import _CustomerRow
from slim_domain.domain.report_folder.report_folder_repository import _CustomerReportFolderRow
from slim_domain.domain.report_folder.report_folder_service import (
    ReportFolderService,
    UnresolvedReportFolderError,
)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                _CustomerRow(
                    id=1,
                    customer_name="Customer 130",
                    street_address="123 Main St",
                    city="Springfield",
                    state="IL",
                    postal_code="62701",
                    country="USA",
                ),
                _CustomerRow(
                    id=2,
                    customer_name="Beta Labs",
                    street_address="456 Oak Ave",
                    city="Shelbyville",
                    state="TN",
                    postal_code="37160",
                    country="",
                ),
            ]
        )
        s.commit()
        yield s


@pytest.fixture
def service(session: Session) -> ReportFolderService:
    return ReportFolderService(session)


def test_resolve_folder_raises_when_unmapped(service: ReportFolderService) -> None:
    with pytest.raises(UnresolvedReportFolderError):
        service.resolve_folder(1, "Customer 130")


def test_resolve_folder_returns_mapped_real_directory(
    service: ReportFolderService, tmp_path: Path
) -> None:
    real_dir = tmp_path / "Customer 130"
    real_dir.mkdir()
    service.set_folder(1, str(real_dir), created_by="JT")

    assert service.resolve_folder(1, "Customer 130") == real_dir


def test_resolve_folder_raises_when_mapped_dir_no_longer_exists(
    service: ReportFolderService, tmp_path: Path
) -> None:
    real_dir = tmp_path / "Renamed Later"
    real_dir.mkdir()
    service.set_folder(1, str(real_dir), created_by="JT")
    real_dir.rmdir()  # simulate the folder being renamed/moved on the share

    with pytest.raises(UnresolvedReportFolderError):
        service.resolve_folder(1, "Customer 130")


def test_set_folder_rejects_nonexistent_path(service: ReportFolderService, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Not a real"):
        service.set_folder(1, str(tmp_path / "does_not_exist"), created_by="JT")


def test_set_folder_rejects_blank_path(service: ReportFolderService) -> None:
    # Regression: Path("").is_dir() is True (it resolves to ".", the
    # server process's own cwd) -- confirmed live when a technician left
    # the resolve-folder page's field untouched (a placeholder isn't
    # submitted, so that read as blank) and it would otherwise have
    # silently mapped a customer's reports to wherever Slim-LIMS happens
    # to be running from.
    with pytest.raises(ValueError, match="cannot be blank"):
        service.set_folder(1, "", created_by="JT")


def test_set_folder_rejects_whitespace_only_path(service: ReportFolderService) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        service.set_folder(1, "   ", created_by="JT")


def test_set_folder_rejects_relative_path(service: ReportFolderService, tmp_path: Path, monkeypatch) -> None:
    # A relative path is relative to the SERVER's cwd, not to anything a
    # technician typing into a browser could have meant.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    with pytest.raises(ValueError, match="full path"):
        service.set_folder(1, "reports", created_by="JT")


def test_set_folder_persists_to_db(session: Session, tmp_path: Path) -> None:
    real_dir = tmp_path / "Customer 130"
    real_dir.mkdir()
    ReportFolderService(session).set_folder(1, str(real_dir), created_by="JT")

    fresh = ReportFolderService(session)
    assert fresh.resolve_folder(1, "Customer 130") == real_dir


def test_mapping_is_independent_per_customer(service: ReportFolderService, tmp_path: Path) -> None:
    acme_dir = tmp_path / "Acme"
    beta_dir = tmp_path / "Beta"
    acme_dir.mkdir()
    beta_dir.mkdir()
    service.set_folder(1, str(acme_dir), created_by="JT")
    service.set_folder(2, str(beta_dir), created_by="JT")

    assert service.resolve_folder(1, "Customer 130") == acme_dir
    assert service.resolve_folder(2, "Beta Labs") == beta_dir


def test_set_folder_is_idempotent_while_existing_mapping_is_still_valid(
    service: ReportFolderService, tmp_path: Path
) -> None:
    # There should only ever be one real submission per customer (Jamie,
    # 2026-09-24) -- a second set_folder() call while the current mapping
    # is still a real, valid directory is a no-op, not a silent overwrite.
    # Confirmed real gap this closes: a genuinely stale resolve-folder tab,
    # submitted late after a FRESHER resolution for the same customer had
    # already succeeded, could previously clobber the already-correct
    # mapping with whatever was sitting in the old tab. Deliberately
    # changing an already-valid mapping on purpose is a separate,
    # not-yet-built "change" workflow, not something this method should do
    # implicitly.
    old_dir = tmp_path / "Old"
    new_dir = tmp_path / "New"
    old_dir.mkdir()
    new_dir.mkdir()
    service.set_folder(1, str(old_dir), created_by="JT")
    service.set_folder(1, str(new_dir), created_by="ZZ")

    assert service.resolve_folder(1, "Customer 130") == old_dir


def test_set_folder_still_overwrites_when_existing_mapping_is_no_longer_valid(
    service: ReportFolderService, tmp_path: Path
) -> None:
    # The one legitimate case the idempotent guard above must NOT block:
    # the mapped folder really did move/get renamed on the file share.
    # resolve_folder() only ever sends a technician back to this page when
    # the current mapping is already missing or no longer a real
    # directory -- exactly the condition the guard also checks for, so a
    # genuine remap still goes through.
    old_dir = tmp_path / "Old"
    new_dir = tmp_path / "New"
    old_dir.mkdir()
    service.set_folder(1, str(old_dir), created_by="JT")
    old_dir.rmdir()  # simulate the folder being renamed/moved on the share
    new_dir.mkdir()

    service.set_folder(1, str(new_dir), created_by="AB")

    assert service.resolve_folder(1, "Customer 130") == new_dir


def test_report_folder_row_table_name() -> None:
    assert _CustomerReportFolderRow.__tablename__ == "customer_report_folders"


# --- location (SX5 North/South) ---
# Confirmed real need: SX5 is a single customer record (shared for
# invoicing) whose real reports split across two real folders depending
# on the TR filename, not the customer record.


def test_two_locations_for_the_same_customer_resolve_independently(
    service: ReportFolderService, tmp_path: Path
) -> None:
    north_dir = tmp_path / "SX5_North"
    south_dir = tmp_path / "SX5_South"
    north_dir.mkdir()
    south_dir.mkdir()
    service.set_folder(1, str(north_dir), created_by="JT", location="SX5N")
    service.set_folder(1, str(south_dir), created_by="JT", location="SX5S")

    assert service.resolve_folder(1, "SX5", location="SX5N") == north_dir
    assert service.resolve_folder(1, "SX5", location="SX5S") == south_dir


def test_unmapped_location_raises_even_when_default_location_is_mapped(
    service: ReportFolderService, tmp_path: Path
) -> None:
    real_dir = tmp_path / "SX5_North"
    real_dir.mkdir()
    service.set_folder(1, str(real_dir), created_by="JT", location="SX5N")

    with pytest.raises(UnresolvedReportFolderError):
        service.resolve_folder(1, "SX5", location="SX5S")


def test_unresolved_report_folder_error_carries_location() -> None:
    e = UnresolvedReportFolderError(1, "SX5", "SX5N")
    assert e.location == "SX5N"
    assert "SX5N" in str(e)


def test_unresolved_report_folder_error_default_location_is_blank() -> None:
    e = UnresolvedReportFolderError(1, "Customer 130")
    assert e.location == ""


def test_unresolved_report_folder_error_default_reason_is_blank() -> None:
    e = UnresolvedReportFolderError(1, "Customer 130")
    assert e.reason == ""


# --- unreachable (not just missing) network share (2026-09-29 failure-path audit) ---
# Path.is_dir() only swallows a narrow allowlist of OSErrors internally
# (ENOENT/ENOTDIR/EBADF/ELOOP, Windows "drive not ready") and returns
# False for those -- it does NOT swallow the Windows network error codes a
# genuinely offline/unreachable UNC share typically raises (e.g. WinError
# 53 "network path not found"), so those used to propagate as a raw,
# unhandled OSError instead of a clean, actionable exception.


def test_resolve_folder_raises_with_reason_when_mapped_dir_is_unreachable(
    service: ReportFolderService, tmp_path: Path, monkeypatch
) -> None:
    real_dir = tmp_path / "Customer 130"
    real_dir.mkdir()
    service.set_folder(1, str(real_dir), created_by="JT")

    def flaky_is_dir(self):
        raise OSError(53, "The network path was not found")

    monkeypatch.setattr(Path, "is_dir", flaky_is_dir)

    with pytest.raises(UnresolvedReportFolderError) as exc_info:
        service.resolve_folder(1, "Customer 130")
    assert "could not be reached" in exc_info.value.reason
    assert "network drive may be offline" in exc_info.value.reason


def test_set_folder_raises_a_reachability_specific_value_error_when_unreachable(
    service: ReportFolderService, tmp_path: Path, monkeypatch
) -> None:
    real_dir = tmp_path / "Customer 130"
    real_dir.mkdir()

    def flaky_is_dir(self):
        raise OSError(53, "The network path was not found")

    monkeypatch.setattr(Path, "is_dir", flaky_is_dir)

    with pytest.raises(ValueError, match="Could not reach"):
        service.set_folder(1, str(real_dir), created_by="JT")


def test_set_folder_rejects_blank_initials(service: ReportFolderService, tmp_path: Path) -> None:
    real_dir = tmp_path / "Customer 130"
    real_dir.mkdir()
    with pytest.raises(ValueError, match="Initials cannot be blank"):
        service.set_folder(1, str(real_dir), created_by="   ")


def test_set_folder_records_created_by_and_created_at(session: Session, tmp_path: Path) -> None:
    real_dir = tmp_path / "Customer 130"
    real_dir.mkdir()
    ReportFolderService(session).set_folder(1, str(real_dir), created_by="JT")

    row = session.get(_CustomerReportFolderRow, (1, ""))
    assert row is not None
    assert row.created_by == "JT"
    assert row.created_at is not None


def test_set_folder_noop_does_not_touch_created_by(session: Session, tmp_path: Path) -> None:
    old_dir = tmp_path / "Old"
    new_dir = tmp_path / "New"
    old_dir.mkdir()
    new_dir.mkdir()
    svc = ReportFolderService(session)
    svc.set_folder(1, str(old_dir), created_by="JT")
    svc.set_folder(1, str(new_dir), created_by="AB")  # stale/late submission -- no-op

    row = session.get(_CustomerReportFolderRow, (1, ""))
    assert row is not None
    assert row.created_by == "JT"


def test_set_folder_remap_updates_created_by(session: Session, tmp_path: Path) -> None:
    old_dir = tmp_path / "Old"
    new_dir = tmp_path / "New"
    old_dir.mkdir()
    svc = ReportFolderService(session)
    svc.set_folder(1, str(old_dir), created_by="JT")
    old_dir.rmdir()  # simulate a genuine remap, per the matching resolve_folder test
    new_dir.mkdir()
    svc.set_folder(1, str(new_dir), created_by="AB")

    row = session.get(_CustomerReportFolderRow, (1, ""))
    assert row is not None
    assert row.created_by == "AB"


# --- Test-mode sandbox (REPORT_FOLDER_TEST_ROOT) ---


def test_test_root_auto_creates_and_accepts_nested_folder(session: Session, tmp_path: Path) -> None:
    test_root = tmp_path / "sandbox"
    svc = ReportFolderService(session, test_root=test_root)

    result = svc.set_folder(1, str(test_root / "Customer 130"), created_by="JT")

    assert result == test_root / "Customer 130"
    assert result.is_dir()  # auto-created, even though it didn't exist yet


def test_test_root_accepts_the_root_itself(session: Session, tmp_path: Path) -> None:
    test_root = tmp_path / "sandbox"
    test_root.mkdir()
    svc = ReportFolderService(session, test_root=test_root)

    result = svc.set_folder(1, str(test_root), created_by="JT")

    assert result == test_root


def test_test_root_rejects_a_path_outside_it(session: Session, tmp_path: Path) -> None:
    test_root = tmp_path / "sandbox"
    real_dir = tmp_path / "real_customer_folder"
    real_dir.mkdir()
    svc = ReportFolderService(session, test_root=test_root)

    with pytest.raises(ValueError, match="Test mode is on"):
        svc.set_folder(1, str(real_dir), created_by="JT")


def test_test_root_rejects_a_sibling_path_that_merely_shares_a_prefix(session: Session, tmp_path: Path) -> None:
    # Guards against a naive string-prefix check: "sandbox-evil" starts
    # with the same characters as "sandbox" but is NOT nested under it.
    test_root = tmp_path / "sandbox"
    evil_dir = tmp_path / "sandbox-evil"
    evil_dir.mkdir()
    svc = ReportFolderService(session, test_root=test_root)

    with pytest.raises(ValueError, match="Test mode is on"):
        svc.set_folder(1, str(evil_dir), created_by="JT")


def test_no_test_root_means_unrestricted_as_before(service: ReportFolderService, tmp_path: Path) -> None:
    assert service.test_root is None
    real_dir = tmp_path / "anywhere"
    real_dir.mkdir()
    assert service.set_folder(1, str(real_dir), created_by="JT") == real_dir


# --- Production-mode containment (REPORT_FOLDER_ROOT) ---
# Confirmed real gap (direct user question, 2026-09-17): without this,
# /resolve/folder -- reachable via a one-time token, NOT the API key --
# could set a customer's report destination to ANY existing absolute
# directory the server can see, not just somewhere under the real
# Reports tree.


def test_production_root_accepts_a_real_nested_folder(session: Session, tmp_path: Path) -> None:
    prod_root = tmp_path / "Reports"
    prod_root.mkdir()
    customer_dir = prod_root / "Customer 130"
    customer_dir.mkdir()
    svc = ReportFolderService(session, production_root=prod_root)

    assert svc.set_folder(1, str(customer_dir), created_by="JT") == customer_dir


def test_production_root_rejects_a_path_outside_it(session: Session, tmp_path: Path) -> None:
    prod_root = tmp_path / "Reports"
    prod_root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    svc = ReportFolderService(session, production_root=prod_root)

    with pytest.raises(ValueError, match="must be under"):
        svc.set_folder(1, str(elsewhere), created_by="JT")


def test_production_root_rejects_a_sibling_path_that_merely_shares_a_prefix(session: Session, tmp_path: Path) -> None:
    prod_root = tmp_path / "Reports"
    prod_root.mkdir()
    evil_dir = tmp_path / "Reports-evil"
    evil_dir.mkdir()
    svc = ReportFolderService(session, production_root=prod_root)

    with pytest.raises(ValueError, match="must be under"):
        svc.set_folder(1, str(evil_dir), created_by="JT")


def test_production_root_does_not_auto_create_missing_folders(session: Session, tmp_path: Path) -> None:
    """Unlike test mode, a missing folder under the production root is
    still rejected, not auto-created -- a missing folder means the
    mapping is wrong, not something to paper over."""
    prod_root = tmp_path / "Reports"
    prod_root.mkdir()
    svc = ReportFolderService(session, production_root=prod_root)

    with pytest.raises(ValueError, match="Not a real"):
        svc.set_folder(1, str(prod_root / "does_not_exist_yet"), created_by="JT")


def test_test_root_takes_precedence_over_production_root(session: Session, tmp_path: Path) -> None:
    test_root = tmp_path / "sandbox"
    prod_root = tmp_path / "Reports"
    test_root.mkdir()
    prod_root.mkdir()
    svc = ReportFolderService(session, test_root=test_root, production_root=prod_root)

    # Accepted under the test root even though it's outside production_root.
    result = svc.set_folder(1, str(test_root / "Customer 130"), created_by="JT")
    assert result == test_root / "Customer 130"
