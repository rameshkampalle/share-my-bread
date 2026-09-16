"""Strict output contract and short-lived, request-bound catalogue evidence."""
import base64
import hashlib
import hmac
import json
import re
import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.guardrail_input import mask_sensitive, normalize_input


class UnsafeOutput(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Item(StrictModel):
    productId: str
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1, le=99)


class Candidate(Item):
    similarityScore: float | None = Field(default=None, ge=0, le=1)


class Proposal(StrictModel):
    action: Literal['ADD_ITEMS']
    items: list[Item] = Field(min_length=1, max_length=20)


class AssistantResponse(StrictModel):
    responseType: Literal['ANSWER', 'CLARIFICATION', 'CART_PROPOSAL', 'NO_MATCH', 'REFUSAL', 'ERROR']
    message: str = Field(min_length=1, max_length=800)
    requiresConfirmation: bool
    correlationId: str
    proposal: Proposal | None
    candidates: list[Candidate] = Field(max_length=12)


def sign_evidence(request_id, products, secret):
    payload = json.dumps({'requestId': str(request_id), 'expires': int(time.time()) + 300, 'products': products}, separators=(',', ':'))
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    signature = hmac.new(secret.encode(), ('catalogue-v1:' + encoded).encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def validate_output(response, evidence, request_id, secret):
    try:
        if not secret or len(evidence) > 12:
            raise UnsafeOutput()
        value = AssistantResponse.model_validate(response)
        UUID(value.correlationId)
        UUID(str(request_id))
        products = {}
        for token in evidence:
            if len(token) > 32000:
                raise UnsafeOutput()
            encoded, signature = token.rsplit('.', 1)
            expected = hmac.new(secret.encode(), ('catalogue-v1:' + encoded).encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise UnsafeOutput()
            data = json.loads(base64.urlsafe_b64decode(encoded))
            if data['requestId'] != str(request_id) or data['expires'] < time.time():
                raise UnsafeOutput()
            for product in data['products']:
                old = products.get(product['productId'])
                if old is not None and old != product:
                    raise UnsafeOutput()
                products[product['productId']] = product
        if value.responseType == 'CART_PROPOSAL':
            if not value.requiresConfirmation or value.proposal is None:
                raise UnsafeOutput()
        elif value.requiresConfirmation or value.proposal is not None:
            raise UnsafeOutput()
        if value.responseType == 'CLARIFICATION' and not value.candidates:
            raise UnsafeOutput()
        if value.candidates and value.responseType not in {'CLARIFICATION', 'CART_PROPOSAL'}:
            raise UnsafeOutput()
        items = (value.proposal.items if value.proposal else []) + value.candidates
        if len({item.productId for item in items}) != len(items):
            raise UnsafeOutput()
        for item in items:
            UUID(item.productId)
            if item.productId not in products or products[item.productId]['name'] != item.name:
                raise UnsafeOutput()
        text = normalize_input(json.dumps(response, ensure_ascii=False))
        if mask_sensitive(text) != text:
            raise UnsafeOutput()
        if re.search(r'(?i)\bI (?:have |already )?(?:added|paid|reserved|collected|fulfilled|updated)\b'
                     r'|\b(?:your|the) order (?:is|has been) (?:paid|fulfilled|collected)\b'
                     r'|\bguaranteed safe\b|\b100% (?:safe|allergen.free)\b', value.message):
            raise UnsafeOutput()
        return list(products.values())
    except Exception:
        raise UnsafeOutput('The assistant response could not be verified.') from None
