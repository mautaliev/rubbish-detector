from pydantic import BaseModel, Field
from typing import Optional, Dict


class DetectRequest(BaseModel):
    image_base64: str = Field(..., description="Image encoded as base64. Data URL is also supported.")
    detect_class: bool = Field(False, description="Use 5-class model instead of 1-class model.")
    conf: float = Field(0.25, ge=0.0, le=1.0, description="YOLO confidence threshold.")


class FoundItem(BaseModel):
    count: int


class DetectResponse(BaseModel):
    image_base64: Optional[str]
    found: Optional[Dict[str, FoundItem]]
    total: int
