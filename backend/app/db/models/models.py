"""
ORM Models — using String UUIDs and JSON for broad PostgreSQL compatibility.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    files: Mapped[list["RepositoryFile"]] = relationship("RepositoryFile", back_populates="repository", cascade="all, delete-orphan")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship("AnalysisResult", back_populates="repository", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner", "name", name="uq_repository_owner_name"),
        Index("ix_repository_owner", "owner"),
        Index("ix_repository_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Repository {self.owner}/{self.name}>"


class RepositoryFile(Base):
    __tablename__ = "repository_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    is_entry_point: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dead_code: Mapped[bool] = mapped_column(Boolean, default=False)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="files")
    outbound_deps: Mapped[list["Dependency"]] = relationship("Dependency", foreign_keys="Dependency.source_file_id", back_populates="source_file", cascade="all, delete-orphan")
    inbound_deps: Mapped[list["Dependency"]] = relationship("Dependency", foreign_keys="Dependency.target_file_id", back_populates="target_file")

    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_file_repo_path"),
        Index("ix_file_repository_id", "repository_id"),
        Index("ix_file_type", "file_type"),
    )

    def __repr__(self) -> str:
        return f"<RepositoryFile {self.path}>"


class Dependency(Base):
    __tablename__ = "dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    source_file_id: Mapped[str] = mapped_column(String(36), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False)
    target_file_id: Mapped[str] = mapped_column(String(36), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False)
    import_statement: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    source_file: Mapped["RepositoryFile"] = relationship("RepositoryFile", foreign_keys=[source_file_id], back_populates="outbound_deps")
    target_file: Mapped["RepositoryFile"] = relationship("RepositoryFile", foreign_keys=[target_file_id], back_populates="inbound_deps")

    __table_args__ = (
        UniqueConstraint("source_file_id", "target_file_id", name="uq_dependency_edge"),
        Index("ix_dependency_repository_id", "repository_id"),
        Index("ix_dependency_source", "source_file_id"),
        Index("ix_dependency_target", "target_file_id"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(100), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repository: Mapped["Repository"] = relationship("Repository", back_populates="analysis_results")

    __table_args__ = (
        Index("ix_analysis_repository_id", "repository_id"),
        Index("ix_analysis_type", "analysis_type"),
        Index("ix_analysis_repo_type", "repository_id", "analysis_type"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisResult {self.analysis_type} for {self.repository_id}>"