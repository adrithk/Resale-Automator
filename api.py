"""Thin FastAPI adapter for the terminal-independent listing pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from listing_generation import ListingGenerationError, generate_listing_draft, validate_listing_draft
from openai_vision import VisionCallResult
from photo_role_detection import resolve_roles_with_tag_index
from pipeline_service import PipelineService, validate_image_file


LOCAL_UPLOAD_DIRECTORY = Path(__file__).resolve().parent / "local_uploads"
MAX_LOCAL_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class ExplicitClassificationRequest(BaseModel):
    item_photo_paths: list[str] = Field(min_length=2)
    tag_photo_path: str


class FolderRoleDetectionRequest(BaseModel):
    photo_paths: list[str] = Field(min_length=3)


class ConfirmedFolderClassificationRequest(BaseModel):
    photo_paths: list[str] = Field(min_length=3)
    photo_role_analysis: dict[str, Any]
    photo_role_metadata: dict[str, Any]
    tag_photo_index: int = Field(ge=0)


class FinalFactsRequest(BaseModel):
    facts: dict[str, str | None]


class ListingDraftRequest(BaseModel):
    draft_title: str | None = None
    description: str | None = None


def create_app(service: PipelineService | None = None) -> FastAPI:
    """Create the HTTP adapter without embedding pipeline or UI behavior."""
    pipeline = service or PipelineService()
    app = FastAPI(title="Resale Listing API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/uploads")
    async def upload_local_photo(photo: UploadFile = File(...)) -> dict[str, str]:
        """Store one browser photo locally under an opaque random name."""
        suffix = Path(photo.filename or "").suffix.lower()
        if photo.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES or suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(
                status_code=415,
                detail="Upload a JPEG, PNG, or WebP photo.",
            )
        contents = await photo.read(MAX_LOCAL_UPLOAD_BYTES + 1)
        if not contents or len(contents) > MAX_LOCAL_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Each photo must be no larger than 10 MB.",
            )
        LOCAL_UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
        destination = LOCAL_UPLOAD_DIRECTORY / f"photo-{uuid.uuid4().hex}{suffix}"
        destination.write_bytes(contents)
        errors = validate_image_file(str(destination), "Uploaded photo")
        if errors:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=errors[0])
        return {"photo_path": str(destination.resolve())}

    @app.post("/photo-roles")
    def start_photo_role_detection(request: FolderRoleDetectionRequest) -> dict[str, Any]:
        return pipeline.start_folder_classification(request.photo_paths)

    @app.post("/classifications/explicit")
    def classify_explicit(request: ExplicitClassificationRequest) -> dict[str, Any]:
        return pipeline.classify_explicit(
            request.item_photo_paths,
            request.tag_photo_path,
        )

    @app.post("/classifications/folder/confirmed")
    def classify_confirmed_folder(
        request: ConfirmedFolderClassificationRequest,
    ) -> dict[str, Any]:
        try:
            confirmed_roles = resolve_roles_with_tag_index(
                request.photo_paths,
                request.photo_role_analysis,
                tag_index=request.tag_photo_index,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return pipeline.classify_confirmed_folder(
            request.photo_paths,
            VisionCallResult(
                analysis=request.photo_role_analysis,
                metadata=request.photo_role_metadata,
            ),
            confirmed_roles,
        )

    @app.post("/listing-drafts")
    def generate_draft(request: FinalFactsRequest) -> dict[str, Any]:
        try:
            return {"listing_draft": generate_listing_draft(request.facts).to_dict()}
        except ListingGenerationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/listing-drafts/validate")
    def validate_draft(request: ListingDraftRequest) -> dict[str, Any]:
        draft, errors = validate_listing_draft(request.model_dump())
        if errors:
            return {"valid": False, "errors": list(errors)}
        assert draft is not None
        return {"valid": True, "listing_draft": draft.to_dict()}

    return app


app = create_app()
