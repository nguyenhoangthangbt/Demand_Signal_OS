"""DemandSignalOS thin trust-gate API.

DSO is library-first (CONSTITUTION L2); this is NOT the full forecasting API
(port 8006 is still reserved for the v0.1.5 extraction). It is a deliberately
THIN FastAPI app that surfaces only the normalized trust gate
(DECISIONS_LOG §P #65): emit a SIGNED CalibrationReceipt for forecast-trust
checks and export the self-auditable validation workbook.

It imports ONLY the light deps — ``trust_gate`` + ``ops_schemas`` + ``excel_io``
+ ``fastapi`` + ``uvicorn``. It does NOT import ``demand_signal_os`` itself, so
the heavy forecasting stack (scipy / statsforecast / lightgbm) never loads in
the API path and the Docker image stays small.
"""

from demand_signal_os.api.app import create_app

__all__ = ["create_app"]
