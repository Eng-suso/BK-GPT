from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


DATA_DIR = Path("data")
WORKSPACE_DB = DATA_DIR / "workspace.db"
WORKSPACE_DB_URL = f"sqlite:///{WORKSPACE_DB.as_posix()}"


class WorkspaceBase(DeclarativeBase):
    pass


class WorkspaceClient(WorkspaceBase):
    __tablename__ = "workspace_clients"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sector: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    contact: Mapped[str] = mapped_column(String, nullable=False)

    projects: Mapped[list["WorkspaceProject"]] = relationship(back_populates="client")


class WorkspaceProject(WorkspaceBase):
    __tablename__ = "workspace_projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("workspace_clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    process_count: Mapped[int] = mapped_column(Integer, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    milestones_json: Mapped[str] = mapped_column(Text, nullable=False)
    open_issues_json: Mapped[str] = mapped_column(Text, nullable=False)
    deliverables_json: Mapped[str] = mapped_column(Text, nullable=False)

    client: Mapped[WorkspaceClient] = relationship(back_populates="projects")
    processes: Mapped[list["WorkspaceProcess"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="WorkspaceProcess.name",
    )


class WorkspaceProcess(WorkspaceBase):
    __tablename__ = "workspace_processes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id"), nullable=False, index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    readiness: Mapped[int] = mapped_column(Integer, nullable=False)

    project: Mapped[WorkspaceProject] = relationship(back_populates="processes")
    bpmn_model: Mapped["WorkspaceBpmnModel"] = relationship(
        back_populates="process",
        cascade="all, delete-orphan",
        uselist=False,
    )


class WorkspaceBpmnModel(WorkspaceBase):
    __tablename__ = "workspace_bpmn_models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    process_id: Mapped[str] = mapped_column(ForeignKey("workspace_processes.id"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    xml: Mapped[str | None] = mapped_column(Text)

    process: Mapped[WorkspaceProcess] = relationship(back_populates="bpmn_model")


class WorkspaceBpmnVersion(WorkspaceBase):
    __tablename__ = "workspace_bpmn_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    xml: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceBpmnReview(WorkspaceBase):
    __tablename__ = "workspace_bpmn_reviews"

    bpmn_model_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    process_understanding_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bpmn_semantic_model_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bpmn_brief: Mapped[str] = mapped_column(Text, nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_information_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceSimulationRun(WorkspaceBase):
    __tablename__ = "workspace_simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scenario_name: Mapped[str] = mapped_column(String, nullable=False)
    engine: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, index=True)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String)


class WorkspaceSource(WorkspaceBase):
    __tablename__ = "workspace_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id"), nullable=False, index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    meta: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceDecision(WorkspaceBase):
    __tablename__ = "workspace_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id"), nullable=False, index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


def build_workspace_engine():
    DATA_DIR.mkdir(exist_ok=True)
    return create_engine(
        WORKSPACE_DB_URL,
        connect_args={"check_same_thread": False},
    )


workspace_engine = build_workspace_engine()
WorkspaceSessionLocal = sessionmaker(bind=workspace_engine, autoflush=False, expire_on_commit=False)


@contextmanager
def workspace_connection():
    session = WorkspaceSessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
