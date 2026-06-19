"""Initial schema: repositories, files, dependencies, analysis_results

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=True, default=0),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("analysis_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner", "name", name="uq_repository_owner_name"),
    )
    op.create_index("ix_repositories_owner", "repositories", ["owner"])
    op.create_index("ix_repositories_created_at", "repositories", ["created_at"])

    # ------------------------------------------------------------------
    # repository_files
    # ------------------------------------------------------------------
    op.create_table(
        "repository_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("parsed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repository_files_repo_id", "repository_files", ["repository_id"])
    op.create_index(
        "ix_repository_files_repo_path",
        "repository_files",
        ["repository_id", "path"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # dependencies
    # ------------------------------------------------------------------
    op.create_table(
        "dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("target_file", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dependencies_repo_id", "dependencies", ["repository_id"])
    op.create_index("ix_dependencies_source", "dependencies", ["repository_id", "source_file"])
    op.create_index("ix_dependencies_target", "dependencies", ["repository_id", "target_file"])

    # ------------------------------------------------------------------
    # analysis_results
    # ------------------------------------------------------------------
    op.create_table(
        "analysis_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_type", sa.String(length=50), nullable=False),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_results_repo_id", "analysis_results", ["repository_id"])
    op.create_index(
        "ix_analysis_results_repo_type",
        "analysis_results",
        ["repository_id", "analysis_type"],
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("dependencies")
    op.drop_table("repository_files")
    op.drop_table("repositories")
