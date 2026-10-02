import logging
import json
from datetime import datetime

class StructuredJSONFormatter(logging.Formatter):
    """
    Format logs as structured JSON to ensure every meaningful action is traceable 
    and machine-readable for post-mortem analysis.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage()
        }
        
        # Capture critical trading metadata if passed via the 'extra' dict
        for key in ["strategy_version", "signal", "symbol", "target_weight", "risk_approved", "order_id", "broker_status", "fill_price", "slippage"]:
            if hasattr(record, key):
                log_record[key] = getattr(record, key)
                
        return json.dumps(log_record)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(handler)
    return logger
