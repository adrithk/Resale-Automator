"""Thin FastAPI adapter for the terminal-independent listing pipeline."""

from __future__ import annotations

from pathlib import Path
from io import BytesIO
from typing import Any, Literal
import uuid

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from depop_csv import DepopCsvError, generate_depop_csv, shipping_location
from listing_generation import ListingGenerationError, generate_listing_draft, validate_listing_draft
from local_persistence import save_approved_result
from local_config import load_backend_environment
from photo_hosting import PhotoHostingError, host_listing_photos, prepare_hosted_photo
from openai_vision import VisionCallResult, VisionProviderError
from listing_pricing import normalize_price, suggest_price
from photo_role_detection import resolve_roles_with_tag_index
from pipeline_service import PipelineService, validate_image_file
from review_validation import validate_final_edits


LOCAL_UPLOAD_DIRECTORY = Path(__file__).resolve().parent / "local_uploads"
MAX_LOCAL_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp", "application/octet-stream", ""}
ALLOWED_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
UPLOAD_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


class ExplicitClassificationRequest(BaseModel):
    item_photo_paths: list[str] = Field(min_length=2)
    tag_photo_path: str


class FolderRoleDetectionRequest(BaseModel):
    photo_paths: list[str] = Field(min_length=3, max_length=8)


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


class ApproveListingRequest(BaseModel):
    pipeline_result: dict[str, Any]
    facts: dict[str, str | None]
    listing_draft: ListingDraftRequest
    price: str | None = None
    photo_paths: list[str] = Field(min_length=3, max_length=8)


class ExportListingRequest(BaseModel):
    approved_facts: dict[str, str | None]
    listing_draft: ListingDraftRequest
    user_approved: Literal[True]
    price: str | None = None
    picture_urls: list[str] = Field(min_length=3, max_length=8)


def create_app(service: PipelineService | None = None) -> FastAPI:
    """Create the HTTP adapter without embedding pipeline or UI behavior."""
    pipeline = service or PipelineService()
    app = FastAPI(title="Resale Listing API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/uploads")
    async def upload_local_photo(photo: UploadFile = File(...)) -> dict[str, str]:
        """Store one browser photo locally under an opaque random name."""
        suffix = Path(photo.filename or "").suffix.lower()
        content_type = (photo.content_type or "").split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_UPLOAD_CONTENT_TYPES or suffix not in ALLOWED_UPLOAD_SUFFIXES:
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
        # Browser/phone MIME labels are hints, not proof of the file format.
        # Check the real bytes before saving; renaming HEIC to JPG is not conversion.
        try:
            with Image.open(BytesIO(contents)) as image:
                is_phone_mpo = image.format == "MPO" and suffix in {".jpg", ".jpeg"}
                if image.format != UPLOAD_FORMATS[suffix] and not is_phone_mpo:
                    raise ValueError("Format does not match extension")
                image.verify()
            if is_phone_mpo:
                contents = prepare_hosted_photo(BytesIO(contents))
        except PhotoHostingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise HTTPException(status_code=422, detail="This file is not a readable image matching its extension. Export it as JPEG, PNG, or WebP; renaming a HEIC file to .jpg is not enough.") from error
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
            draft = generate_listing_draft(request.facts).to_dict()
            location = shipping_location()
            pricing = suggest_price(request.facts)
            return {
                "listing_draft": draft,
                "price": pricing.analysis["price"],
                "shipping_location": location,
                "pricing_metadata": {**dict(pricing.metadata), "basis": "model_estimate", **dict(pricing.analysis)},
            }
        except ListingGenerationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except DepopCsvError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except VisionProviderError as error:
            raise HTTPException(status_code=502, detail="Price generation failed. Check the backend API configuration or retry.") from error

    @app.post("/facts/validate")
    def validate_facts(request: FinalFactsRequest) -> dict[str, Any]:
        outcome = validate_final_edits(request.facts)
        if not outcome.is_valid:
            return {"valid": False, "errors": list(outcome.errors)}
        return {"valid": True, "approved_facts": dict(outcome.approved_facts or {})}

    @app.post("/listing-drafts/validate")
    def validate_draft(request: ListingDraftRequest) -> dict[str, Any]:
        draft, errors = validate_listing_draft(request.model_dump())
        if errors:
            return {"valid": False, "errors": list(errors)}
        assert draft is not None
        return {"valid": True, "listing_draft": draft.to_dict()}

    @app.post("/listings/approve")
    def approve_listing(request: ApproveListingRequest) -> dict[str, Any]:
        facts = validate_final_edits(request.facts)
        draft, draft_errors = validate_listing_draft(request.listing_draft.model_dump())
        if not facts.is_valid or draft is None:
            return {
                "status": "approval_validation_error",
                "fact_errors": list(facts.errors),
                "draft_errors": list(draft_errors),
            }
        try:
            price = normalize_price(request.price)
            location = shipping_location()
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            picture_urls = host_listing_photos(request.photo_paths, upload_directory=LOCAL_UPLOAD_DIRECTORY)
        except PhotoHostingError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        result = dict(request.pipeline_result)
        result.update(
            status="listing_approved",
            approved_facts=dict(facts.approved_facts or {}),
            listing_draft=draft.to_dict(),
            price=price,
            shipping_location=location,
            picture_urls=picture_urls,
            uploaded_photo_paths=list(request.photo_paths),
            review_reasons=[],
            next_step="saved_locally",
        )
        try:
            save_approved_result(result)
        except OSError as error:
            raise HTTPException(status_code=500, detail="The approved listing could not be saved.") from error
        return result

    @app.post("/listings/export.csv")
    def export_listing_csv(request: ExportListingRequest) -> Response:
        """Download one explicitly approved listing in Depop template order."""
        try:
            contents = generate_depop_csv(
                request.approved_facts,
                request.listing_draft.model_dump(),
                price=request.price,
                picture_urls=request.picture_urls,
            )
        except DepopCsvError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        filename = f"depop-listing-{uuid.uuid4().hex}.csv"
        return Response(
            content=contents,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


load_backend_environment()
app = create_app()
