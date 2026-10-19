"""N2b: BudgetSweeper.sweep_once musí na PostgreSQL proběhnout (offer worker).

`:expiry_interval::interval` v text() SQL končil na PostgreSQL syntaktickou
chybou – sweeper v offer workeru selhal při každém průchodu a zapomenuté
rezervace AI budgetu se nikdy neuvolnily.
"""

import pytest

from app.modules.offers.budget_sweeper import BudgetSweeper


@pytest.mark.asyncio
async def test_sweep_once_executes_on_the_configured_database(db_session_factory, test_tenants):
    if db_session_factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("FOR UPDATE SKIP LOCKED / interval aritmetika – jen PostgreSQL")
    sweeper = BudgetSweeper(session_factory=db_session_factory)
    swept = await sweeper.sweep_once()
    assert swept >= 0
