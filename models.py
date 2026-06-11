from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Enum
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
    trigger_value = Column(Float, nullable=True)
    trigger_time = Column(DateTime(timezone=True), nullable=False)
    latest_value = Column(Float, nullable=True)
    latest_time = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sensor = relationship("Sensor", back_populates="alarms")
    confirmations = relationship("AlarmConfirmation", back_populates="alarm", order_by="AlarmConfirmation.created_at")


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
