import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.accounting.reconciliation import ReconciliationService
from trading_system.app.common.database import SessionLocal
from trading_system.app.models.core import Position

def run():
    db_session = SessionLocal()
    try:
        # Seed the DB with the exact output from our Q1 2025 Multi-Asset test
        db_session.query(Position).delete()
        db_session.add(Position(symbol="DIA", quantity=115.0, average_price=0.0))
        db_session.add(Position(symbol="QQQ", quantity=-211.0, average_price=0.0))
        db_session.add(Position(symbol="IWM", quantity=-498.0, average_price=0.0))
        db_session.commit()
        
        print("\n=== STARTING RECONCILIATION CHECK ===")
        # We initialize Alpaca with a 'mock' key to simulate a disconnected/mismatched broker
        broker = AlpacaBrokerAdapter(api_key="mock", api_secret="mock")
        
        reconciler = ReconciliationService(broker, db_session)
        success = reconciler.reconcile()
        
        if not success:
            print("\n[WARNING] Reconciliation failed. Check logs for mismatches.")
            print("Per Master Spec: We do NOT auto-correct in V1. Trading should be halted until manual review.")
        else:
            print("\n[SUCCESS] Internal state matches Broker exactly.")
            
    finally:
        db_session.close()

if __name__ == "__main__":
    run()
