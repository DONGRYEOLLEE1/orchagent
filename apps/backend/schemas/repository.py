from datetime import datetime

from pydantic import BaseModel


class RepositoryBindingRequest(BaseModel):
    thread_id: str
    source_type: str
    source_ref: str


class RepositoryBindingResponse(BaseModel):
    id: str
    thread_id: str
    source_type: str
    source_label: str
    display_name: str
    default_branch: str | None = None
    pinned_commit_sha: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RepositoryBindingEnvelope(BaseModel):
    binding: RepositoryBindingResponse | None = None


class RepositoryMaterializeRequest(BaseModel):
    thread_id: str


class RepositoryMaterializeResponse(BaseModel):
    binding: RepositoryBindingResponse
    repo_commit_sha: str | None = None
    status: str
