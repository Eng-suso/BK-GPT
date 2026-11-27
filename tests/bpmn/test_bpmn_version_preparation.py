from types import SimpleNamespace

from backend.workspace_database import bpmn as bpmn_store


class _Session:
    def __init__(self):
        self.version = None

    def add(self, version):
        self.version = version


def test_prepared_bpmn_version_keeps_the_exact_saved_xml(monkeypatch):
    def unexpected_layout(*args, **kwargs):
        raise AssertionError("the saved XML must not be laid out a second time")

    monkeypatch.setattr(bpmn_store, "assert_write_allowed", lambda action: None)
    monkeypatch.setattr(bpmn_store, "_canvas_xml_for_write", unexpected_layout)
    session = _Session()
    model = SimpleNamespace(id="model-1", process_id="process-1", name="Process", tenant_id="tenant-1")

    version = bpmn_store.create_bpmn_version(
        session,
        model,
        "<prepared-bpmn/>",
        "Rename activity",
        "canvas_facade_update",
        already_prepared=True,
    )

    assert session.version is version
    assert version.xml == "<prepared-bpmn/>"
