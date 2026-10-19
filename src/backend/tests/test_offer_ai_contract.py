"""Offer AI contract — measurements only, no prices (full price separation).

The AI returns measured quantities; prices are computed server-side from the
catalog pricing engine. These tests pin that contract so a regression that
reintroduces model-produced prices — or a fail-open validation path — is caught
immediately. See docs/ARCHITECTURE_DECISION_RECORDS/ADR-0004-measurements-only.md.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.offer_processing.provider import (
    AnthropicAdapter,
    MockAdapter,
    ProviderRequest,
    ProviderRequestError,
    _extract_tool_output,
    _OFFER_TOOLS,
)
from app.offer_processing.validation import (
    InsufficientDataResult,
    OfferOutputValidator,
    OfferValidationError,
    ValidatedMeasurements,
)

# The work-type whitelist the runner resolves from the catalog. Production always
# passes a concrete set; the validator is fail-closed when it is missing.
KNOWN = frozenset({"roof_clean"})


def _measurement_raw(**overrides):
    base = {
        "outcome": "offer_generated",
        "measurements": [
            {
                "work_type_code": "ROOF_CLEAN",
                "quantity": 12.5,
                "unit": "m2",
                "surface_condition": "critical",
                "recommended_scope": "local_repair",
                "description": "moss on north slope",
                "confidence": 0.8,
            }
        ],
        "overall_confidence": 0.8,
        "warnings": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Validation — measurements
# ---------------------------------------------------------------------------


def test_validator_accepts_measurements_and_normalizes():
    result = OfferOutputValidator(known_work_type_codes=KNOWN).validate(_measurement_raw())
    assert isinstance(result, ValidatedMeasurements)
    item = result.measurements[0]
    assert item.work_type_code == "roof_clean"          # lowercased
    assert item.quantity == Decimal("12.5000")          # quantized
    assert item.surface_condition == "critical"


def test_validator_strips_any_price_fields_from_ai_output():
    """Even if the model sneaks price fields in, they must not survive."""
    raw = _measurement_raw()
    raw["measurements"][0]["unit_price_czk"] = 9999
    raw["measurements"][0]["total_price_czk"] = 123456
    result = OfferOutputValidator(known_work_type_codes=KNOWN).validate(raw)
    dumped = result.measurements[0].model_dump()
    assert "unit_price_czk" not in dumped
    assert "total_price_czk" not in dumped


def test_validator_fail_closed_without_whitelist():
    """No whitelist → reject (Constitution Art. 6 & 9). Must NOT pass permissively."""
    with pytest.raises(OfferValidationError) as exc:
        OfferOutputValidator().validate(_measurement_raw())
    assert "fail-closed" in str(exc.value)


def test_validator_empty_whitelist_rejects_all_codes():
    """An empty catalog whitelist rejects every code — also fail-closed."""
    with pytest.raises(OfferValidationError) as exc:
        OfferOutputValidator(known_work_type_codes=frozenset()).validate(_measurement_raw())
    assert "unknown work_type_codes" in str(exc.value)


def test_validator_enforces_code_whitelist():
    validator = OfferOutputValidator(known_work_type_codes=frozenset({"facade_paint"}))
    with pytest.raises(OfferValidationError) as exc:
        validator.validate(_measurement_raw())
    assert "unknown work_type_codes" in str(exc.value)


def test_validator_accepts_known_code_case_insensitively():
    result = OfferOutputValidator(known_work_type_codes=KNOWN).validate(_measurement_raw())
    assert isinstance(result, ValidatedMeasurements)


def test_validator_rejects_bad_surface_condition():
    raw = _measurement_raw()
    raw["measurements"][0]["surface_condition"] = "apocalyptic"
    with pytest.raises(OfferValidationError):
        OfferOutputValidator(known_work_type_codes=KNOWN).validate(raw)


def test_validator_rejects_non_positive_quantity():
    raw = _measurement_raw()
    raw["measurements"][0]["quantity"] = 0
    with pytest.raises(OfferValidationError):
        OfferOutputValidator(known_work_type_codes=KNOWN).validate(raw)


def test_validator_handles_insufficient_data():
    # The insufficient-data path needs no whitelist (it carries no work_type_codes).
    result = OfferOutputValidator().validate(
        {"outcome": "insufficient_data", "questions": ["Add a wide shot of the roof."]}
    )
    assert isinstance(result, InsufficientDataResult)
    assert result.questions == ["Add a wide shot of the roof."]


# ---------------------------------------------------------------------------
# Mock adapter — measurements only, end-to-end through the validator
# ---------------------------------------------------------------------------


async def test_mock_adapter_emits_measurements_no_prices():
    req = ProviderRequest(
        work_type_code="roof_clean",
        parameters={},
        photo_urls=[],
        work_type_definition={},
        pricing_context={},
    )
    resp = await MockAdapter().complete(req)
    assert resp.raw_output["outcome"] == "offer_generated"
    assert "measurements" in resp.raw_output
    assert "line_items" not in resp.raw_output
    assert "total_price_czk" not in resp.raw_output
    # Mock output is a valid measurement payload against a whitelist containing its code.
    validated = OfferOutputValidator(known_work_type_codes=KNOWN).validate(resp.raw_output)
    assert isinstance(validated, ValidatedMeasurements)


# ---------------------------------------------------------------------------
# Tool-call extraction (strict tool use → raw output discriminator)
# ---------------------------------------------------------------------------


def test_tool_definitions_are_strict_and_priceless():
    names = {t["name"] for t in _OFFER_TOOLS}
    assert names == {"submit_measurements", "request_more_info"}
    for tool in _OFFER_TOOLS:
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
    measure = next(t for t in _OFFER_TOOLS if t["name"] == "submit_measurements")
    item_props = measure["input_schema"]["properties"]["measurements"]["items"]["properties"]
    assert "unit_price_czk" not in item_props
    assert "total_price_czk" not in item_props


def test_extract_tool_output_maps_submit_measurements():
    block = SimpleNamespace(
        type="tool_use",
        name="submit_measurements",
        input={"measurements": [], "overall_confidence": 0.5, "warnings": []},
    )
    message = SimpleNamespace(content=[block])
    out = _extract_tool_output(message)
    assert out["outcome"] == "offer_generated"
    assert out["overall_confidence"] == 0.5


def test_extract_tool_output_maps_request_more_info():
    block = SimpleNamespace(type="tool_use", name="request_more_info", input={"questions": ["q"]})
    message = SimpleNamespace(content=[block])
    out = _extract_tool_output(message)
    assert out["outcome"] == "insufficient_data"
    assert out["questions"] == ["q"]


def test_extract_tool_output_raises_without_tool_call():
    message = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
    with pytest.raises(ProviderRequestError):
        _extract_tool_output(message)


# ---------------------------------------------------------------------------
# Image blocks — photos reach the model
# ---------------------------------------------------------------------------


def test_build_content_includes_image_blocks_for_http_urls():
    adapter = AnthropicAdapter(api_key="x", model_id="claude-opus-4-8")
    req = ProviderRequest(
        work_type_code="roof_clean",
        parameters={"area_hint": 80},
        photo_urls=["https://example.com/a.jpg", "https://example.com/b.jpg", "not-a-url"],
        work_type_definition={"code": "roof_clean"},
        pricing_context={},
    )
    content = adapter._build_content(req)
    assert content[0]["type"] == "text"
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 2          # the non-url is skipped
    assert images[0]["source"]["url"] == "https://example.com/a.jpg"


def test_adapter_uses_configured_model():
    adapter = AnthropicAdapter(api_key="x", model_id="claude-opus-4-8")
    assert adapter.model_id == "claude-opus-4-8"
    assert adapter.key == "claude"


# ---------------------------------------------------------------------------
# Runner — fail-closed catalog resolution (Constitution Art. 6 & 9)
# ---------------------------------------------------------------------------


class _FakeSessionFactory:
    """Stands in for WorkerAsyncSessionFactory — yields a dummy session."""

    def __call__(self):
        return self

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, *exc_info):
        return False


def _null_log():
    return SimpleNamespace(warning=lambda *a, **k: None)


def _offer_processor(monkeypatch, *, catalog_repo_cls):
    from app.worker import offer_runner as runner_mod

    monkeypatch.setattr(runner_mod, "WorkerAsyncSessionFactory", _FakeSessionFactory())
    monkeypatch.setattr(runner_mod, "WorkCatalogRepository", catalog_repo_cls)
    monkeypatch.setattr(runner_mod, "PhotoRepository", lambda session: SimpleNamespace())
    payload = SimpleNamespace(
        job_id="job_1",
        offer_request_id="ofr_1",
        organization_id="org_1",
        work_type_code="roof_clean",
        parameters={},
        photo_ids=[],
        attempt=1,
        priority="normal",
    )
    dequeued = SimpleNamespace(payload=payload, lease_token="lt_1", leased_at=None)
    return runner_mod.OfferJobProcessor(
        dequeued=dequeued, worker_id="w_1", agent_runtime=None, redis=None
    )


async def test_resolve_ai_inputs_fails_closed_when_catalog_unavailable(monkeypatch):
    """A catalog outage must fail the job, never yield a permissive whitelist."""
    from app.worker.offer_runner import _AiInputResolutionError

    class _BrokenCatalog:
        def __init__(self, session):
            pass

        async def get_work_type_by_code(self, code):
            raise RuntimeError("catalog unavailable")

        async def list_work_types_global(self):
            raise RuntimeError("catalog unavailable")

    processor = _offer_processor(monkeypatch, catalog_repo_cls=_BrokenCatalog)
    with pytest.raises(_AiInputResolutionError):
        await processor._resolve_ai_inputs(log=_null_log())


async def test_resolve_ai_inputs_returns_catalog_whitelist(monkeypatch):
    class _Catalog:
        def __init__(self, session):
            pass

        async def get_work_type_by_code(self, code):
            return SimpleNamespace(code="roof_clean", name_cs="Čištění střechy")

        async def list_work_types_global(self):
            return [
                SimpleNamespace(code="roof_clean"),
                SimpleNamespace(code="facade_paint"),
            ]

    processor = _offer_processor(monkeypatch, catalog_repo_cls=_Catalog)
    photo_urls, work_type_def, known_codes = await processor._resolve_ai_inputs(
        log=_null_log()
    )
    assert photo_urls == []
    assert work_type_def == {"code": "roof_clean", "name": "Čištění střechy"}
    assert known_codes == frozenset({"roof_clean", "facade_paint"})
