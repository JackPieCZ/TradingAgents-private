from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel


class AnalystType(str, Enum):
    MARKET = "Price & Technical"
    SOCIAL = "System State"
    NEWS = "Energy News & Regulatory"
    FUNDAMENTALS = "Weather & Forecast"
