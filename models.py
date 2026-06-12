from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from database import Base


class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    OBSERVER = "observer"


class AlarmStatusEnum(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    PROCESSING = "processing"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"
    CLOSED = "closed"


class AlarmTypeEnum(str, enum.Enum):
    OVER_TEMP = "over_temp"
    UNDER_TEMP = "under_temp"
    OFFLINE = "offline"


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sensors = relationship("Sensor", back_populates="zone")


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.OBSERVER)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    confirmations = relationship("AlarmConfirmation", back_populates="confirmer")


class Sensor(Base):
    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    offline_timeout_minutes = Column(Integer, default=30)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    zone = relationship("Zone", back_populates="sensors")
    threshold_versions = relationship("ThresholdVersion", back_populates="sensor")
    readings = relationship("TemperatureReading", back_populates="sensor")
    alarms = relationship("Alarm", back_populates="sensor")


class ThresholdVersion(Base):
    __tablename__ = "threshold_versions"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)
    version = Column(Integer, nullable=False)
    upper_limit = Column(Float, nullable=False)
    lower_limit = Column(Float, nullable=False)
    dedup_window_minutes = Column(Integer, default=60)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sensor = relationship("Sensor", back_populates="threshold_versions")


class TemperatureReading(Base):
    __tablename__ = "temperature_readings"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)
    temperature = Column(Float, nullable=False)
    reading_time = Column(DateTime(timezone=True), nullable=False, index=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    sensor = relationship("Sensor", back_populates="readings")


class Alarm(Base):
    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)
    alarm_type = Column(Enum(AlarmTypeEnum), nullable=False)
    status = Column(Enum(AlarmStatusEnum), nullable=False, default=AlarmStatusEnum.OPEN)
    threshold_version_id = Column(Integer, ForeignKey("threshold_versions.id"), nullable=True)
    suppression_rule_id = Column(Integer, ForeignKey("suppression_rules.id"), nullable=True)
    trigger_value = Column(Float, nullable=True)
    trigger_time = Column(DateTime(timezone=True), nullable=False)
    latest_value = Column(Float, nullable=True)
    latest_time = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sensor = relationship("Sensor", back_populates="alarms")
    confirmations = relationship("AlarmConfirmation", back_populates="alarm", order_by="AlarmConfirmation.created_at")
    suppression_rule = relationship("SuppressionRule", foreign_keys=[suppression_rule_id])


class AlarmConfirmation(Base):
    __tablename__ = "alarm_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    from_status = Column(Enum(AlarmStatusEnum), nullable=False)
    to_status = Column(Enum(AlarmStatusEnum), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    alarm = relationship("Alarm", back_populates="confirmations")
    confirmer = relationship("Person", back_populates="confirmations")


class SuppressionRuleStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SuppressionRule(Base):
    __tablename__ = "suppression_rules"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True)
    alarm_type = Column(Enum(AlarmTypeEnum), nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String(255), nullable=False)
    created_by = Column(Integer, ForeignKey("persons.id"), nullable=False)
    status = Column(Enum(SuppressionRuleStatus), nullable=False, default=SuppressionRuleStatus.ACTIVE)
    revoked_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sensor = relationship("Sensor", foreign_keys=[sensor_id])
    zone = relationship("Zone", foreign_keys=[zone_id])
    creator = relationship("Person", foreign_keys=[created_by])
    revoker = relationship("Person", foreign_keys=[revoked_by])
    hits = relationship("SuppressionHit", back_populates="rule")


class SuppressionHit(Base):
    __tablename__ = "suppression_hits"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("suppression_rules.id"), nullable=False)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=False)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)
    alarm_type = Column(Enum(AlarmTypeEnum), nullable=False)
    trigger_value = Column(Float, nullable=True)
    trigger_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    rule = relationship("SuppressionRule", back_populates="hits")
    alarm = relationship("Alarm")
    sensor = relationship("Sensor")


class DrillStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DrillAction(str, enum.Enum):
    TRIGGER = "trigger"
    UPDATE = "update"
    ESCALATE = "escalate"
    RECOVER = "recover"
    NONE = "none"


class DrillAlarmChangeType(str, enum.Enum):
    NEW_ALARM = "new_alarm"
    STATUS_UPDATE = "status_update"
    RECOVERED = "recovered"
    ESCALATED = "escalated"


class Drill(Base):
    __tablename__ = "drills"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    target_temp = Column(Float, nullable=False)
    allowed_fluctuation = Column(Float, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    status = Column(Enum(DrillStatus), nullable=False, default=DrillStatus.DRAFT)
    created_by = Column(Integer, ForeignKey("persons.id"), nullable=False)
    started_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    config_snapshot = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    zone = relationship("Zone", foreign_keys=[zone_id])
    creator = relationship("Person", foreign_keys=[created_by])
    starter = relationship("Person", foreign_keys=[started_by])
    canceller = relationship("Person", foreign_keys=[cancelled_by])
    readings = relationship("DrillReading", back_populates="drill", cascade="all, delete-orphan")
    judgments = relationship("DrillJudgment", back_populates="drill", cascade="all, delete-orphan")
    alarm_changes = relationship("DrillAlarmChange", back_populates="drill", cascade="all, delete-orphan")
    operation_logs = relationship("DrillOperationLog", back_populates="drill", cascade="all, delete-orphan")


class DrillReading(Base):
    __tablename__ = "drill_readings"

    id = Column(Integer, primary_key=True, index=True)
    drill_id = Column(Integer, ForeignKey("drills.id"), nullable=False, index=True)
    sensor_code = Column(String(50), nullable=False)
    temperature = Column(Float, nullable=False)
    reading_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drill = relationship("Drill", back_populates="readings")


class DrillJudgment(Base):
    __tablename__ = "drill_judgments"

    id = Column(Integer, primary_key=True, index=True)
    drill_id = Column(Integer, ForeignKey("drills.id"), nullable=False, index=True)
    sensor_code = Column(String(50), nullable=False)
    temperature = Column(Float, nullable=False)
    reading_time = Column(DateTime(timezone=True), nullable=False)
    alarm_type = Column(Enum(AlarmTypeEnum), nullable=True)
    action = Column(Enum(DrillAction), nullable=False)
    previous_alarm_status = Column(String(50), nullable=True)
    current_alarm_status = Column(String(50), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drill = relationship("Drill", back_populates="judgments")


class DrillAlarmChange(Base):
    __tablename__ = "drill_alarm_changes"

    id = Column(Integer, primary_key=True, index=True)
    drill_id = Column(Integer, ForeignKey("drills.id"), nullable=False, index=True)
    sensor_code = Column(String(50), nullable=False)
    alarm_type = Column(Enum(AlarmTypeEnum), nullable=True)
    change_type = Column(Enum(DrillAlarmChangeType), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    trigger_value = Column(Float, nullable=True)
    trigger_time = Column(DateTime(timezone=True), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drill = relationship("Drill", back_populates="alarm_changes")


class DrillOperationLog(Base):
    __tablename__ = "drill_operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    drill_id = Column(Integer, ForeignKey("drills.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    operator_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drill = relationship("Drill", back_populates="operation_logs")
    operator = relationship("Person", foreign_keys=[operator_id])


class ShiftEnum(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    NIGHT = "night"


class ChecklistStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVOKED = "revoked"


class CheckItemStatus(str, enum.Enum):
    PENDING = "pending"
    NORMAL = "normal"
    ABNORMAL = "abnormal"


class ShiftChecklist(Base):
    __tablename__ = "shift_checklists"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False, index=True)
    shift_date = Column(Date, nullable=False, index=True)
    shift_type = Column(Enum(ShiftEnum), nullable=False, index=True)
    status = Column(Enum(ChecklistStatus), nullable=False, default=ChecklistStatus.DRAFT)
    created_by = Column(Integer, ForeignKey("persons.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    general_remark = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    zone = relationship("Zone", foreign_keys=[zone_id])
    creator = relationship("Person", foreign_keys=[created_by])
    submitter = relationship("Person", foreign_keys=[submitted_by])
    revoker = relationship("Person", foreign_keys=[revoked_by])
    sensor_items = relationship("ShiftChecklistSensorItem", back_populates="checklist", cascade="all, delete-orphan")
    manual_items = relationship("ShiftChecklistManualItem", back_populates="checklist", cascade="all, delete-orphan")


class ShiftChecklistSensorItem(Base):
    __tablename__ = "shift_checklist_sensor_items"

    id = Column(Integer, primary_key=True, index=True)
    checklist_id = Column(Integer, ForeignKey("shift_checklists.id"), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)
    snapshot_threshold_upper = Column(Float, nullable=False)
    snapshot_threshold_lower = Column(Float, nullable=False)
    snapshot_latest_reading_value = Column(Float, nullable=True)
    snapshot_latest_reading_time = Column(DateTime(timezone=True), nullable=True)
    snapshot_open_alarm_count = Column(Integer, nullable=False, default=0)
    snapshot_open_alarm_ids = Column(Text, nullable=True)
    check_status = Column(Enum(CheckItemStatus), nullable=False, default=CheckItemStatus.PENDING)
    checked_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    abnormal_remark = Column(Text, nullable=True)
    handler_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    checklist = relationship("ShiftChecklist", back_populates="sensor_items")
    sensor = relationship("Sensor", foreign_keys=[sensor_id])
    checker = relationship("Person", foreign_keys=[checked_by])
    handler = relationship("Person", foreign_keys=[handler_id])


class ShiftChecklistManualItem(Base):
    __tablename__ = "shift_checklist_manual_items"

    id = Column(Integer, primary_key=True, index=True)
    checklist_id = Column(Integer, ForeignKey("shift_checklists.id"), nullable=False, index=True)
    item_name = Column(String(200), nullable=False)
    item_description = Column(String(500), nullable=True)
    check_status = Column(Enum(CheckItemStatus), nullable=False, default=CheckItemStatus.PENDING)
    checked_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    abnormal_remark = Column(Text, nullable=True)
    handler_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    checklist = relationship("ShiftChecklist", back_populates="manual_items")
    checker = relationship("Person", foreign_keys=[checked_by])
    handler = relationship("Person", foreign_keys=[handler_id])


class InspectionTemplateStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class InspectionWorkOrderStatus(str, enum.Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"


class InspectionTemplate(Base):
    __tablename__ = "inspection_templates"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False, index=True)
    shift_type = Column(Enum(ShiftEnum), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    deadline_hours = Column(Float, nullable=False, default=8.0)
    status = Column(Enum(InspectionTemplateStatus), nullable=False, default=InspectionTemplateStatus.DRAFT)
    created_by = Column(Integer, ForeignKey("persons.id"), nullable=False)
    activated_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    disabled_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    disabled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    zone = relationship("Zone", foreign_keys=[zone_id])
    creator = relationship("Person", foreign_keys=[created_by])
    activator = relationship("Person", foreign_keys=[activated_by])
    disabler = relationship("Person", foreign_keys=[disabled_by])
    checkpoints = relationship("InspectionCheckpoint", back_populates="template", cascade="all, delete-orphan")
    work_orders = relationship("InspectionWorkOrder", back_populates="template")


class InspectionCheckpoint(Base):
    __tablename__ = "inspection_checkpoints"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    require_photo = Column(Boolean, default=False)
    require_temperature = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    template = relationship("InspectionTemplate", back_populates="checkpoints")


class InspectionWorkOrder(Base):
    __tablename__ = "inspection_work_orders"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False, index=True)
    shift_type = Column(Enum(ShiftEnum), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    deadline = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(InspectionWorkOrderStatus), nullable=False, default=InspectionWorkOrderStatus.PENDING, index=True)
    claimed_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    general_remark = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("persons.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    template = relationship("InspectionTemplate", back_populates="work_orders")
    zone = relationship("Zone", foreign_keys=[zone_id])
    claimer = relationship("Person", foreign_keys=[claimed_by])
    completer = relationship("Person", foreign_keys=[completed_by])
    creator = relationship("Person", foreign_keys=[created_by])
    items = relationship("InspectionWorkOrderItem", back_populates="work_order", cascade="all, delete-orphan")
    alarm_associations = relationship("InspectionWorkOrderAlarm", back_populates="work_order", cascade="all, delete-orphan")
    operation_logs = relationship("InspectionWorkOrderLog", back_populates="work_order", cascade="all, delete-orphan")


class InspectionWorkOrderItem(Base):
    __tablename__ = "inspection_work_order_items"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("inspection_work_orders.id"), nullable=False, index=True)
    checkpoint_id = Column(Integer, ForeignKey("inspection_checkpoints.id"), nullable=False)
    checkpoint_name = Column(String(200), nullable=False)
    checkpoint_description = Column(String(500), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    require_photo = Column(Boolean, default=False)
    require_temperature = Column(Boolean, default=False)
    temperature_value = Column(Float, nullable=True)
    photo_urls = Column(Text, nullable=True)
    check_status = Column(Enum(CheckItemStatus), nullable=False, default=CheckItemStatus.PENDING)
    checked_by = Column(Integer, ForeignKey("persons.id"), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    remark = Column(Text, nullable=True)
    exception_action = Column(Text, nullable=True)
    handler_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    work_order = relationship("InspectionWorkOrder", back_populates="items")
    checkpoint = relationship("InspectionCheckpoint", foreign_keys=[checkpoint_id])
    checker = relationship("Person", foreign_keys=[checked_by])
    handler = relationship("Person", foreign_keys=[handler_id])


class InspectionWorkOrderAlarm(Base):
    __tablename__ = "inspection_work_order_alarms"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("inspection_work_orders.id"), nullable=False, index=True)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=False, index=True)
    alarm_snapshot = Column(Text, nullable=True)
    associated_by = Column(Integer, ForeignKey("persons.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    work_order = relationship("InspectionWorkOrder", back_populates="alarm_associations")
    alarm = relationship("Alarm", foreign_keys=[alarm_id])
    associator = relationship("Person", foreign_keys=[associated_by])


class InspectionWorkOrderLog(Base):
    __tablename__ = "inspection_work_order_logs"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("inspection_work_orders.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    operator_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    work_order = relationship("InspectionWorkOrder", back_populates="operation_logs")
    operator = relationship("Person", foreign_keys=[operator_id])
