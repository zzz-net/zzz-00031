from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class RoleEnum(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    OBSERVER = "observer"


class AlarmStatusEnum(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    PROCESSING = "processing"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"
    CLOSED = "closed"


class AlarmTypeEnum(str, Enum):
    OVER_TEMP = "over_temp"
    UNDER_TEMP = "under_temp"
    OFFLINE = "offline"


class ZoneBase(BaseModel):
    name: str
    description: Optional[str] = None


class ZoneCreate(ZoneBase):
    pass


class Zone(ZoneBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PersonBase(BaseModel):
    name: str
    role: RoleEnum = RoleEnum.OBSERVER
    phone: Optional[str] = None
    email: Optional[str] = None


class PersonCreate(PersonBase):
    pass


class Person(PersonBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SensorBase(BaseModel):
    code: str
    name: str
    zone_id: int
    is_active: bool = True
    offline_timeout_minutes: int = 30


class SensorCreate(SensorBase):
    pass


class SensorUpdate(BaseModel):
    name: Optional[str] = None
    zone_id: Optional[int] = None
    is_active: Optional[bool] = None
    offline_timeout_minutes: Optional[int] = None


class Sensor(SensorBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ThresholdVersionBase(BaseModel):
    sensor_id: int
    upper_limit: float
    lower_limit: float
    dedup_window_minutes: int = 60
    effective_from: datetime


class ThresholdVersionCreate(ThresholdVersionBase):
    pass


class ThresholdVersion(ThresholdVersionBase):
    id: int
    version: int
    created_at: datetime

    class Config:
        from_attributes = True


class TemperatureReadingBase(BaseModel):
    sensor_code: str
    temperature: float
    reading_time: datetime


class TemperatureReadingCreate(BaseModel):
    sensor_code: str
    temperature: float
    reading_time: datetime


class TemperatureReading(BaseModel):
    id: int
    sensor_id: int
    temperature: float
    reading_time: datetime
    imported_at: datetime

    class Config:
        from_attributes = True


class ReadingImportResult(BaseModel):
    total: int
    successful: int
    failed: int
    errors: List[str] = []
    new_alarms: int = 0
    updated_alarms: int = 0


class AlarmConfirmationBase(BaseModel):
    person_id: int
    note: Optional[str] = None


class Alarm(AlarmConfirmationBase):
    pass


class AlarmDetail(BaseModel):
    id: int
    sensor_id: int
    sensor_code: str
    sensor_name: str
    zone_name: str
    alarm_type: AlarmTypeEnum
    status: AlarmStatusEnum
    trigger_value: Optional[float] = None
    trigger_time: datetime
    latest_value: Optional[float] = None
    latest_time: Optional[datetime] = None
    resolution_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    confirmations: List["AlarmConfirmation"] = []

    class Config:
        from_attributes = True


class AlarmConfirmation(BaseModel):
    id: int
    alarm_id: int
    person_id: int
    person_name: str
    person_role: RoleEnum
    from_status: AlarmStatusEnum
    to_status: AlarmStatusEnum
    note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlarmStatusUpdate(BaseModel):
    person_id: int
    note: Optional[str] = None


class AlarmCloseUpdate(BaseModel):
    person_id: int
    resolution_note: str


class AlarmSuppressUpdate(BaseModel):
    person_id: int
    note: Optional[str] = None
    suppress_minutes: int = 60


AlarmDetail.model_rebuild()
