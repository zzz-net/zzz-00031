from pydantic import BaseModel, Field
from datetime import datetime, date
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
    suppression_rule_id: Optional[int] = None
    suppression_rule_reason: Optional[str] = None
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
    resolution_note: Optional[str] = None


class SuppressionRuleStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SuppressionRuleCreate(BaseModel):
    sensor_id: Optional[int] = None
    zone_id: Optional[int] = None
    alarm_type: Optional[AlarmTypeEnum] = None
    start_time: datetime
    end_time: datetime
    reason: str
    created_by: int


class SuppressionRuleBase(BaseModel):
    id: int
    sensor_id: Optional[int] = None
    zone_id: Optional[int] = None
    alarm_type: Optional[AlarmTypeEnum] = None
    start_time: datetime
    end_time: datetime
    reason: str
    status: SuppressionRuleStatus
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SuppressionRuleDetail(SuppressionRuleBase):
    sensor_code: Optional[str] = None
    sensor_name: Optional[str] = None
    zone_name: Optional[str] = None
    creator_name: Optional[str] = None
    creator_role: Optional[RoleEnum] = None
    revoked_by: Optional[int] = None
    revoked_at: Optional[datetime] = None
    revoker_name: Optional[str] = None
    hit_count: int = 0


class SuppressionHit(BaseModel):
    id: int
    rule_id: int
    alarm_id: int
    sensor_id: int
    sensor_code: Optional[str] = None
    alarm_type: AlarmTypeEnum
    trigger_value: Optional[float] = None
    trigger_time: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ReadingImportResult(BaseModel):
    total: int
    successful: int
    failed: int
    errors: List[str] = []
    new_alarms: int = 0
    updated_alarms: int = 0
    suppressed_alarms: int = 0


AlarmDetail.model_rebuild()


class ShiftEnum(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    NIGHT = "night"


class ChecklistStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVOKED = "revoked"


class CheckItemStatus(str, Enum):
    PENDING = "pending"
    NORMAL = "normal"
    ABNORMAL = "abnormal"


class ShiftChecklistCreate(BaseModel):
    zone_id: int
    shift_date: date
    shift_type: ShiftEnum
    created_by: int
    general_remark: Optional[str] = None


class ShiftChecklistSubmit(BaseModel):
    person_id: int
    general_remark: Optional[str] = None


class ShiftChecklistRevoke(BaseModel):
    person_id: int


class ShiftChecklistSensorItemUpdate(BaseModel):
    person_id: int
    check_status: CheckItemStatus
    abnormal_remark: Optional[str] = None
    handler_id: Optional[int] = None


class ShiftChecklistManualItemUpdate(BaseModel):
    person_id: int
    check_status: CheckItemStatus
    abnormal_remark: Optional[str] = None
    handler_id: Optional[int] = None


class ShiftChecklistSensorItem(BaseModel):
    id: int
    checklist_id: int
    sensor_id: int
    sensor_code: Optional[str] = None
    sensor_name: Optional[str] = None
    snapshot_threshold_upper: float
    snapshot_threshold_lower: float
    snapshot_latest_reading_value: Optional[float] = None
    snapshot_latest_reading_time: Optional[datetime] = None
    snapshot_open_alarm_count: int = 0
    snapshot_open_alarm_ids: Optional[str] = None
    check_status: CheckItemStatus
    checked_by: Optional[int] = None
    checked_by_name: Optional[str] = None
    checked_at: Optional[datetime] = None
    abnormal_remark: Optional[str] = None
    handler_id: Optional[int] = None
    handler_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShiftChecklistManualItem(BaseModel):
    id: int
    checklist_id: int
    item_name: str
    item_description: Optional[str] = None
    check_status: CheckItemStatus
    checked_by: Optional[int] = None
    checked_by_name: Optional[str] = None
    checked_at: Optional[datetime] = None
    abnormal_remark: Optional[str] = None
    handler_id: Optional[int] = None
    handler_name: Optional[str] = None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShiftChecklistBase(BaseModel):
    id: int
    zone_id: int
    zone_name: Optional[str] = None
    shift_date: date
    shift_type: ShiftEnum
    status: ChecklistStatus
    created_by: int
    creator_name: Optional[str] = None
    creator_role: Optional[RoleEnum] = None
    submitted_by: Optional[int] = None
    submitter_name: Optional[str] = None
    submitted_at: Optional[datetime] = None
    revoked_by: Optional[int] = None
    revoker_name: Optional[str] = None
    revoked_at: Optional[datetime] = None
    general_remark: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ShiftChecklistList(ShiftChecklistBase):
    sensor_item_count: int = 0
    manual_item_count: int = 0
    pending_count: int = 0
    abnormal_count: int = 0

    class Config:
        from_attributes = True


class ShiftChecklistDetail(ShiftChecklistBase):
    sensor_items: List[ShiftChecklistSensorItem] = []
    manual_items: List[ShiftChecklistManualItem] = []

    class Config:
        from_attributes = True
