from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from slim_domain.domain.report_folder.report_folder_cache import ReportFolderCache
from slim_domain.domain.report_folder.report_folder_repository import ReportFolderRepository


class UnresolvedReportFolderError(Exception):
    """Raised when a customer has no known Reports destination folder, or
    the previously-mapped one no longer exists on disk (renamed/moved on the
    file share since it was last resolved)."""

    def __init__(self, customer_id: int, customer_name: str, location: str = "", reason: str = "") -> None:
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.location = location
        # reason: set only when there IS a mapping but it couldn't be
        # confirmed reachable right now (e.g. the network share is
        # offline) -- distinct from "no mapping at all." Empty string
        # (the default) means the caller should use the generic "needs to
        # be set" wording, same as before this field existed -- see
        # resolve_folder()'s own docstring.
        self.reason = reason
        where = f" ({location})" if location else ""
        super().__init__(f"No usable report folder mapped for customer {customer_name!r}{where} ({customer_id})")


class ReportFolderService:
    """Public API for the customer -> Reports-folder mapping domain.

    Deliberately its own domain, not a Customer field: the Testing_Requests
    and Reports folder trees are confirmed NOT to share a naming
    convention (a real listing showed ~20% drift, plus at least one
    genuinely one-to-many case), so the destination folder can never be
    derived from Customer.name -- it has to be its own learned mapping,
    resolved once per customer the same way an unresolved customer/chemical
    is (see TRFormInputResolver / UnresolvedCustomerError).
    """

    def __init__(
        self,
        session: Session,
        test_root: Path | str | None = None,
        production_root: Path | str | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._repo = ReportFolderRepository(session, engine=engine)
        # When set (REPORT_FOLDER_TEST_ROOT in .env -- see build_services()
        # in slim_report_engine.cli), every folder this service will
        # accept is confined under this directory, and it's auto-created
        # on demand -- letting Jamie and Quality exercise the real
        # resolution UI and save/swap behavior end-to-end without any
        # possibility of a write landing in a real customer's real
        # S:\Reports folder.
        self.test_root: Path | None = Path(test_root).resolve() if test_root else None
        # production_root: the real-mode analogue -- confirmed a real gap
        # (direct user question, "shouldn't we validate save path too?"):
        # without this, /resolve/folder (reachable via a one-time token,
        # NOT the API key) could set a customer's report destination to
        # ANY existing absolute directory the server can see, with no
        # restriction to the real Reports tree at all -- arguably worse
        # than an unrestricted read path, since it's a persistent WRITE
        # target reachable behind weaker auth. None means unrestricted
        # (only used when a caller deliberately doesn't configure one,
        # e.g. some tests) -- build_services() always supplies a real
        # default in practice.
        self.production_root: Path | None = Path(production_root).resolve() if production_root else None
        # Test and production mappings are stored as separate rows and this
        # service only ever loads its own mode's -- the wall between the two.
        self.mode = "test" if self.test_root is not None else "production"
        self._cache = ReportFolderCache(self._repo, self.mode)

    def _in_active_root(self, folder_path: str) -> bool:
        """True if folder_path is under the root for the current mode: the
        test root while test mode is on, otherwise the production root
        (None means unrestricted, as in set_folder). Stored paths are
        already resolved, so this is a plain path comparison -- no disk
        or network access."""
        root = self.test_root if self.test_root is not None else self.production_root
        if root is None:
            return True
        path = Path(folder_path)
        return path == root or root in path.parents

    def resolve_folder(self, customer_id: int, customer_name: str, location: str = "") -> Path:
        """Return the mapped, currently-real report folder for
        (customer_id, location). location is "" for every customer except
        SX5 (see class docstring's module -- North/South comes from the
        TR filename, not the customer record).

        Raises UnresolvedReportFolderError if there's no mapping yet, if
        the mapping is outside the current mode's root (see
        _in_active_root), or if
        the mapped folder no longer exists -- a stale/renamed mapping fails
        loudly here rather than silently writing into a phantom path.
        Also raises it (with `reason` set, distinguishing this from the
        no-mapping case) if the mapped folder exists on record but can't
        currently be confirmed reachable -- e.g. the network share is
        offline. Confirmed real gap (2026-09-29 failure-path audit):
        Path.is_dir() only swallows a narrow allowlist of OSErrors
        internally (ENOENT/ENOTDIR/EBADF/ELOOP, Windows "drive not
        ready") and returns False for those -- it does NOT swallow the
        Windows network error codes a genuinely offline/unreachable UNC
        share typically raises (e.g. WinError 53 "network path not
        found," 64 "network name no longer available"), so those used to
        propagate as a raw, unhandled OSError instead of this class."""
        mapped = self._cache.get(customer_id, location)
        if mapped is not None and not self._in_active_root(mapped):
            # Second layer of the wall (the first is the per-mode rows): a
            # mapping outside this mode's root -- e.g. one saved under an
            # old test root -- is never used; the customer is unresolved
            # again and a technician picks the folder once.
            mapped = None
        if mapped is not None:
            try:
                reachable = Path(mapped).is_dir()
            except OSError as e:
                raise UnresolvedReportFolderError(
                    customer_id, customer_name, location,
                    reason=f"the mapped folder ({mapped}) could not be reached ({e}) -- the "
                    "network drive may be offline. Check the connection and try again.",
                ) from e
            if reachable:
                return Path(mapped)
        raise UnresolvedReportFolderError(customer_id, customer_name, location)

    def set_folder(self, customer_id: int, folder_path: str, created_by: str = "", location: str = "") -> Path:
        """Validate, persist, and cache the report folder for (customer_id, location).

        Rejects a blank path explicitly rather than relying on is_dir()
        alone: Path("").is_dir() is True (it resolves to ".", the
        CALLING PROCESS's current working directory) -- confirmed the hard
        way when a blank submission from the resolve-folder page would
        otherwise have silently mapped a customer to wherever the
        Slim-LIMS server process happens to be running from. Also
        requires an absolute path for the same reason: any relative path
        is relative to that same server-process cwd, not to anything a
        technician actually meant.

        created_by: the entering technician's initials, for the ISO 17025
        audit trail -- see CustomerService.create_customer's docstring for
        why initials rather than a login. Required.

        Idempotent: no-op (returns the existing mapping) if a currently-
        valid folder is already mapped for (customer_id, location) --
        mirrors CustomerService.add_form_key/ChemicalService.add_form_name's
        own idempotent guard. Confirmed real gap without this (2026-09-24,
        direct question: "can a stale resolution tab feed in false data?"):
        a genuinely stale resolve-folder page -- left open, then submitted
        well after a FRESHER resolution attempt for the same customer had
        already succeeded -- would previously upsert unconditionally,
        silently overwriting the already-correct mapping with whatever was
        sitting in the old tab. There should only ever be one real
        submission per customer; changing an already-valid mapping on
        purpose is a separate, not-yet-built "change" workflow, not
        something a stray stale tab should be able to do by accident. This
        guard doesn't block the one legitimate case where set_folder() DOES
        need to write again (the mapped folder moved/was renamed on the
        file share) -- resolve_folder() only ever raises
        UnresolvedReportFolderError, which is what gets a technician to
        this page in the first place, when the current mapping is already
        missing or no longer a real directory -- the exact same condition
        this guard checks for."""
        existing = self._cache.get(customer_id, location)
        if existing is not None and self._in_active_root(existing) and Path(existing).is_dir():
            return Path(existing)

        if not created_by.strip():
            raise ValueError("Initials cannot be blank.")
        folder_path = folder_path.strip()
        if not folder_path:
            raise ValueError("Folder path cannot be blank.")
        path = Path(folder_path)
        if not path.is_absolute():
            raise ValueError(f"Folder path must be a full path (e.g. S:\\Reports\\...): {folder_path!r}")

        if self.test_root is not None:
            resolved = path.resolve()
            if resolved != self.test_root and self.test_root not in resolved.parents:
                raise ValueError(
                    f"Test mode is on -- the folder must be under {self.test_root}, not: {folder_path}"
                )
            # Safe to auto-create here specifically because it's confined
            # to the test root above -- never done for a real production
            # path, where a missing folder means the mapping is wrong.
            resolved.mkdir(parents=True, exist_ok=True)
            path = resolved
        else:
            if self.production_root is not None:
                resolved = path.resolve()
                if resolved != self.production_root and self.production_root not in resolved.parents:
                    raise ValueError(
                        f"Folder must be under {self.production_root}, not: {folder_path}"
                    )
                path = resolved
            try:
                reachable = path.is_dir()
            except OSError as e:
                # Same OSError-escape gap as resolve_folder() above, for
                # the same reason (a genuinely offline network share isn't
                # in the narrow set of OSErrors Path.is_dir() swallows) --
                # confirmed real gap, 2026-09-29 failure-path audit.
                raise ValueError(
                    f"Could not reach {folder_path!r} ({e}) -- the network drive may be offline. "
                    "Check the connection and try again."
                ) from e
            if not reachable:
                raise ValueError(f"Not a real, accessible folder: {folder_path}")

        self._repo.upsert(customer_id, str(path), created_by=created_by, location=location, mode=self.mode)
        self._cache.set(customer_id, str(path), location=location)
        return path
