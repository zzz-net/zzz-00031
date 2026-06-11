from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import List, Optional

import models
import schemas


def create_zone(db: Session, zone: schemas.ZoneCreate) -> models.Zone:
    db_zone = models.Zone(**zone.model_dump())
    db.add(db_zone)
    db.commit()
    db.refresh(db_zone)
    return db_zone


def get_zone(db: Session, zone_id: int) -> Optional[models.Zone]:
    return db.query(models.Zone).filter(models.Zone.id == zone_id).first()


def get_zone_by_name(db: Session, name: str) -> Optional[models.Zone]:
    return db.query(models.Zone).filter(models.Zone.name == name).first()


def list_zones(db: Session, skip: int = 0, limit: int = 100) -> List[models.Zone]:
    return db.query(models.Zone).offset(skip).limit(limit).all()


def create_person(db: Session, person: schemas.PersonCreate) -> models.Person:
    db_person = models.Person(**person.model_dump())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


def get_person(db: Session, person_id: int) -> Optional[models.Person]:
    return db.query(models.Person).filter(models.Person.id == person_id).first()


def list_persons(db: Session, skip: int = 0, limit: int = 100) -> List[models.Person]:
    return db.query(models.Person).offset(skip).limit(limit).all()


def create_sensor(db: Session, sensor: schemas.SensorCreate) -> models.Sensor:
    db_sensor = models.Sensor(**sensor.model_dump())
    db.add(db_sensor)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor


def get_sensor(db: Session, sensor_id: int) -> Optional[models.Sensor]:
    return db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()


def get_sensor_by_code(db: Session, code: str) -> Optional[models.Sensor]:
    return db.query(models.Sensor).filter(models.Sensor.code == code).first()


def list_sensors(db: Session, zone_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[models.Sensor]:
    query = db.query(models.Sensor)
    if zone_id:
        query = query.filter(models.Sensor.zone_id == zone_id)
    return query.offset(skip).limit(limit).all()


def update_sensor(db: Session, sensor_id: int, sensor_update: schemas.SensorUpdate) -> Optional[models.Sensor]:
    db_sensor = get_sensor(db, sensor_id)
    if not db_sensor:
        return None
    update_data = sensor_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_sensor, key, value)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor


def create_threshold_version(db: Session, threshold: schemas.ThresholdVersionCreate) -> models.ThresholdVersion:
    existing = (
        db.query(models.ThresholdVersion)
        .filter(models.ThresholdVersion.sensor_id == threshold.sensor_id)
        .order_by(desc(models.ThresholdVersion.version))
        .first()
    )
    next_version = existing.version + 1 if existing else 1

    db_threshold = models.ThresholdVersion(
        sensor_id=threshold.sensor_id,
        version=next_version,
        upper_limit=threshold.upper_limit,
        lower_limit=threshold.lower_limit,
        dedup_window_minutes=threshold.dedup_window_minutes,
        effective_from=threshold.effective_from
    )
    db.add(db_threshold)
    db.commit()
    db.refresh(db_threshold)
    return db_threshold


def get_threshold_versions(db: Session, sensor_id: int, skip: int = 0, limit: int = 50) -> List[models.ThresholdVersion]:
    return (
        db.query(models.ThresholdVersion)
        .filter(models.ThresholdVersion.sensor_id == sensor_id)
        .order_by(desc(models.ThresholdVersion.version))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_latest_threshold(db: Session, sensor_id: int) -> Optional[models.ThresholdVersion]:
    return (
        db.query(models.ThresholdVersion)
        .filter(models.ThresholdVersion.sensor_id == sensor_id)
        .order_by(desc(models.ThresholdVersion.version))
        .first()
    )


def list_readings(db: Session, sensor_id: Optional[int] = None, start: Optional[datetime] = None,
                  end: Optional[datetime] = None, skip: int = 0, limit: int = 1000) -> List[models.TemperatureReading]:
    query = db.query(models.TemperatureReading)
    if sensor_id:
        query = query.filter(models.TemperatureReading.sensor_id == sensor_id)
    if start:
        query = query.filter(models.TemperatureReading.reading_time >= start)
    if end:
        query = query.filter(models.TemperatureReading.reading_time <= end)
    return query.order_by(desc(models.TemperatureReading.reading_time)).offset(skip).limit(limit).all()
