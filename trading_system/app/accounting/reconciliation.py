from typing import Dict, List
from trading_system.app.common.logger import get_logger
from trading_system.app.common.interfaces import BrokerAdapter
from trading_system.app.models.core import Position
from sqlalchemy.orm import Session

logger = get_logger("ReconciliationService")

class ReconciliationService:
    def __init__(self, broker: BrokerAdapter, db_session: Session):
        self.broker = broker
        self.db = db_session
        
    def reconcile(self):
        """
        Queries internal DB and Broker. Alerts on any mismatches.
        Per the Master Spec: Do NOT auto-correct in V1, just alert and halt.
        """
        logger.info("Starting Daily Reconciliation Process...")
        
        # 1. Get Broker Truth
        try:
            broker_positions = self.broker.get_positions()
        except Exception as e:
            logger.error(f"Failed to fetch broker positions: {e}")
            return False
            
        # 2. Get Internal Truth
        internal_records = self.db.query(Position).all()
        internal_positions = {pos.symbol: pos.quantity for pos in internal_records if pos.quantity != 0}
        
        # 3. Compare
        mismatches = []
        all_symbols = set(broker_positions.keys()).union(set(internal_positions.keys()))
        
        for sym in all_symbols:
            broker_qty = broker_positions.get(sym, 0.0)
            internal_qty = internal_positions.get(sym, 0.0)
            
            if broker_qty != internal_qty:
                mismatches.append({
                    "symbol": sym,
                    "broker_qty": broker_qty,
                    "internal_qty": internal_qty,
                    "delta": broker_qty - internal_qty
                })
                
        if mismatches:
            logger.error("CRITICAL ALERT: RECONCILIATION MISMATCH DETECTED!")
            for m in mismatches:
                logger.error(f"Mismatch in {m['symbol']}: Broker says {m['broker_qty']}, DB says {m['internal_qty']}")
            return False
            
        logger.info("Reconciliation Complete. All systems perfectly synced.")
        return True
