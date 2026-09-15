"""Server-to-server checks. This secret is never sent to the browser or n8n."""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from app.services.guardrails import build_checker, GuardrailUnavailable
from app.services.catalogue_guardrails import checked_catalogue
from app.shared.config import get_settings

router = APIRouter(prefix='/api/guardrails', tags=['guardrails'])


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: Literal['input', 'output', 'retrieval']
    text: str = Field(min_length=1, max_length=16000)

    @field_validator('text')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Text must not be blank')
        return value


async def require_service_secret(x_guardrails_secret: str | None = Header(default=None)):
    expected = get_settings().guardrails_api_secret
    if not expected:
        raise HTTPException(503, 'Safety checks are not configured.')
    if not x_guardrails_secret or not secrets.compare_digest(x_guardrails_secret.encode(), expected.encode()):
        raise HTTPException(401, 'Invalid service credentials.')


async def get_checker(_=Depends(require_service_secret)):
    try:
        return build_checker()
    except GuardrailUnavailable:
        raise HTTPException(503, 'Safety checks are unavailable.') from None


@router.post('/check', dependencies=[Depends(require_service_secret)])
async def check(payload: CheckRequest, response: Response, checker=Depends(get_checker)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await checker.check(payload.stage, payload.text)
    except GuardrailUnavailable:
        raise HTTPException(503, 'Safety checks are unavailable. Please try again.') from None


class CatalogueRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    productIds: list[UUID] = Field(max_length=10)


@router.post('/catalogue', dependencies=[Depends(require_service_secret)])
async def catalogue(payload: CatalogueRequest, response: Response, checker=Depends(get_checker)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await checked_catalogue(payload.productIds, checker)
    except GuardrailUnavailable:
        raise HTTPException(503, 'Checked catalogue is unavailable.') from None
