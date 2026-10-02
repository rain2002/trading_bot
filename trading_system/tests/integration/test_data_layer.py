import pytest
from datetime import datetime, timedelta
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
import pandas as pd

def test_yfinance_provider_fetches_and_hashes_data():
    """
    Test that the data provider successfully fetches real data, 
    normalizes it, and attaches the strict cryptographic lineage hash.
    """
    provider = YFinanceDataProvider()
    
    # Fetch a short, known period in the past
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 15)
    
    df = provider.fetch_historical_data('SPY', start, end)
    
    # Verify data exists and is normalized
    assert not df.empty
    assert 'close' in df.columns
    assert 'open' in df.columns
    assert df.index.name == 'timestamp'
    
    # Verify lineage metadata was attached
    assert 'lineage' in df.attrs
    lineage = df.attrs['lineage']
    
    assert lineage['symbol'] == 'SPY'
    assert lineage['provider'] == 'yfinance'
    assert 'version_hash' in lineage
    assert len(lineage['version_hash']) == 12  # SHA-256 truncated
