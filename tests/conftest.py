"""Test configuration — isolate tests from production data.

Creates a temporary data directory for each test session so
tests never conflict with a running backend or each other.
"""
import os
import shutil
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def test_data_dir():
    """Create an isolated temp directory for all test data."""
    tmpdir = tempfile.mkdtemp(prefix="propedge_test_")

    # Patch core.config module-level constants BEFORE config loads
    import core.config as cfg
    from pathlib import Path

    cfg.DATA_DIR = Path(tmpdir)

    # Also patch the default DataConfig to use temp paths
    original_init = cfg.DataConfig.__init__

    def patched_init(self, **kwargs):
        original_init(self, **kwargs)
        self.duckdb_path = str(Path(tmpdir) / "propedge_analytics.duckdb")
        self.sqlite_path = str(Path(tmpdir) / "propedge_operational.db")
        self.historical_dir = str(Path(tmpdir) / "historical")
        self.models_dir = str(Path(tmpdir) / "models")
        self.features_dir = str(Path(tmpdir) / "features")

    cfg.DataConfig.__init__ = patched_init

    yield tmpdir

    # Restore and cleanup
    cfg.DataConfig.__init__ = original_init
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset global singletons before each test."""
    import data_engine.database as db_mod
    import core.config as cfg_mod

    # Close any open connections
    if db_mod._duckdb is not None:
        try:
            db_mod._duckdb.close()
        except Exception:
            pass
    db_mod._duckdb = None
    db_mod._sqlite = None
    cfg_mod._config = None

    yield

    # Cleanup after test
    if db_mod._duckdb is not None:
        try:
            db_mod._duckdb.close()
        except Exception:
            pass
    db_mod._duckdb = None
    db_mod._sqlite = None
    cfg_mod._config = None
