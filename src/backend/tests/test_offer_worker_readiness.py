"""AI_OFFER_PROVIDER: mock je bezpečný výchozí stav; claude vyžaduje explicitní
konfiguraci – platný ANTHROPIC_API_KEY a tvrdé rozpočtové limity. Backlog se
vyčísluje před zapnutím offer workeru."""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.modules.offers.readiness import (
    OfferWorkerNotReadyError,
    check_offer_provider_ready,
    collect_offer_backlog,
)

_REAL_LOOKING_KEY = "sk-ant-api03-" + "x" * 40


def _settings(provider, key=None):
    return SimpleNamespace(ai_offer_provider=provider, anthropic_api_key=key)


@pytest.mark.asyncio
async def test_mock_is_ready_without_api_key(db_session):
    assert await check_offer_provider_ready(_settings("mock"), db_session) == "mock"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, "", "CHANGE_ME_real_anthropic_api_key"])
async def test_claude_requires_a_real_api_key(db_session, key):
    with pytest.raises(OfferWorkerNotReadyError, match="ANTHROPIC_API_KEY"):
        await check_offer_provider_ready(_settings("claude", key), db_session)


@pytest.mark.asyncio
async def test_unknown_provider_is_rejected(db_session):
    with pytest.raises(OfferWorkerNotReadyError, match="not supported"):
        await check_offer_provider_ready(_settings("openai", _REAL_LOOKING_KEY), db_session)


@pytest.mark.asyncio
async def test_claude_requires_hard_budget_limits(db_session, test_tenants):
    await db_session.execute(text("DELETE FROM organization_ai_budgets"))
    await db_session.execute(
        text(
            "INSERT INTO organization_ai_budgets (id, organization_id, daily_token_limit, monthly_cost_limit_usd, "
            "alert_threshold_pct, daily_tokens_used, monthly_cost_used_usd, is_hard_limit, created_at, updated_at) "
            "VALUES ('bud_n2', 'org_e2e_a', 200000, 500, 80, 0, 0, :hard, now(), now())"
        ),
        {"hard": False},
    )
    await db_session.commit()
    try:
        with pytest.raises(OfferWorkerNotReadyError, match="hard AI budget limits"):
            await check_offer_provider_ready(_settings("claude", _REAL_LOOKING_KEY), db_session)

        await db_session.execute(text("UPDATE organization_ai_budgets SET is_hard_limit = true WHERE id = 'bud_n2'"))
        await db_session.commit()
        assert await check_offer_provider_ready(_settings("claude", _REAL_LOOKING_KEY), db_session) == "claude"
    finally:
        await db_session.execute(text("DELETE FROM organization_ai_budgets WHERE id = 'bud_n2'"))
        await db_session.commit()


class _FakeRedis:
    def __init__(self, lengths):
        self.lengths = lengths

    async def llen(self, key):
        return self.lengths.get(key, 0)


@pytest.mark.asyncio
async def test_backlog_counts_redis_queue_and_flags_ai_work(db_session, test_tenants):
    redis = _FakeRedis({"offer:normal": 2, "offer:low": 1, "offer:processing": 1})
    backlog = await collect_offer_backlog(db_session, redis)
    assert backlog.redis_offer_queue == 3
    assert backlog.redis_offer_processing == 1
    assert backlog.would_call_ai is True
    assert backlog.outbox_unpublished >= 0
    assert set(backlog.as_dict()) >= {"offer_jobs_queued", "outbox_unpublished", "would_call_ai"}
