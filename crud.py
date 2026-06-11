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


def create_suppression_rule(db: Session, rule: schemas.SuppressionRuleCreate) -> models.SuppressionRule:
    db_rule = models.SuppressionRule(
        sensor_id=rule.sensor_id,
        zone_id=rule.zone_id,
        alarm_type=rule.alarm_type,
        start_time=rule.start_time,
        end_time=rule.end_time,
        reason=rule.reason,
        created_by=rule.created_by,
        status=models.SuppressionRuleStatus.ACTIVE
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def get_suppression_rule(db: Session, rule_id: int) -> Optional[models.SuppressionRule]:
    return db.query(models.SuppressionRule).filter(models.SuppressionRule.id == rule_id).first()


def list_suppression_rules(
    db: Session,
    sensor_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    status: Optional[models.SuppressionRuleStatus] = None,
    skip: int = 0,
    limit: int = 100
) -> List[models.SuppressionRule]:
    query = db.query(models.SuppressionRule)
    if sensor_id:
        query = query.filter(models.SuppressionRule.sensor_id == sensor_id)
    if zone_id:
        query = query.filter(models.SuppressionRule.zone_id == zone_id)
    if status:
        query = query.filter(models.SuppressionRule.status == status)
    return query.order_by(desc(models.SuppressionRule.created_at)).offset(skip).limit(limit).all()


def check_suppression_conflict(
    db: Session,
    sensor_id: Optional[int],
    zone_id: Optional[int],
    alarm_type: Optional[models.AlarmTypeEnum],
    start_time: datetime,
    end_time: datetime,
    exclude_rule_id: Optional[int] = None
) -> List[models.SuppressionRule]:
    query = db.query(models.SuppressionRule).filter(
        models.SuppressionRule.status == models.SuppressionRuleStatus.ACTIVE,
        models.SuppressionRule.start_time < end_time,
        models.SuppressionRule.end_time > start_time
    )
    if exclude_rule_id:
        query = query.filter(models.SuppressionRule.id != exclude_rule_id)

    rules = query.all()
    conflicts = []
    for rule in rules:
        sensor_match = (sensor_id is not None and rule.sensor_id == sensor_id) or \
                       (sensor_id is None and zone_id is None and rule.sensor_id is None and rule.zone_id is None)
        zone_match = False
        if zone_id is not None and rule.zone_id is not None:
            zone_match = rule.zone_id == zone_id
        if zone_id is not None and rule.sensor_id is not None:
            sensor = db.query(models.Sensor).filter(models.Sensor.id == rule.sensor_id).first()
            if sensor and sensor.zone_id == zone_id:
                zone_match = True
        if sensor_id is not None and rule.zone_id is not None:
            sensor = db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()
            if sensor and sensor.zone_id == rule.zone_id:
                sensor_match = True

        type_match = alarm_type is None or rule.alarm_type is None or rule.alarm_type == alarm_type

        if (sensor_match or zone_match or (rule.sensor_id is None and rule.zone_id is None)) and type_match:
            conflicts.append(rule)

    return conflicts


def get_active_suppression_for_sensor(
    db: Session,
    sensor_id: int,
    alarm_type: models.AlarmTypeEnum,
    at_time: datetime
) -> Optional[models.SuppressionRule]:
    sensor = db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()
    if not sensor:
        return None

    zone_id = sensor.zone_id

    rules = (
        db.query(models.SuppressionRule)
        .filter(
            models.SuppressionRule.status == models.SuppressionRuleStatus.ACTIVE,
            models.SuppressionRule.start_time <= at_time,
            models.SuppressionRule.end_time > at_time
        )
        .order_by(desc(models.SuppressionRule.created_at))
        .all()
    )

    for rule in rules:
        if rule.alarm_type is not None and rule.alarm_type != alarm_type:
            continue
        if rule.sensor_id is not None and rule.sensor_id != sensor_id:
            continue
        if rule.zone_id is not None and rule.zone_id != zone_id:
            continue
        if rule.sensor_id is None and rule.zone_id is None:
            return rule
        if rule.sensor_id == sensor_id:
            return rule
        if rule.zone_id == zone_id:
            return rule

    return None


def revoke_suppression_rule(
    db: Session,
    rule_id: int,
    revoked_by: int
) -> Optional[models.SuppressionRule]:
    rule = get_suppression_rule(db, rule_id)
    if not rule:
        return None
    rule.status = models.SuppressionRuleStatus.REVOKED
    rule.revoked_by = revoked_by
    rule.revoked_at = datetime.now()
    db.commit()
    db.refresh(rule)
    return rule


def create_suppression_hit(
    db: Session,
    rule_id: int,
    alarm_id: int,
    sensor_id: int,
    alarm_type: models.AlarmTypeEnum,
    trigger_value: Optional[float],
    trigger_time: datetime
) -> models.SuppressionHit:
    hit = models.SuppressionHit(
        rule_id=rule_id,
        alarm_id=alarm_id,
        sensor_id=sensor_id,
        alarm_type=alarm_type,
        trigger_value=trigger_value,
        trigger_time=trigger_time
    )
    db.add(hit)
    db.flush()
    return hit


def list_suppression_hits(
    db: Session,
    rule_id: Optional[int] = None,
    sensor_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[models.SuppressionHit]:
    query = db.query(models.SuppressionHit)
    if rule_id:
        query = query.filter(models.SuppressionHit.rule_id == rule_id)
    if sensor_id:
        query = query.filter(models.SuppressionHit.sensor_id == sensor_id)
    return query.order_by(desc(models.SuppressionHit.created_at)).offset(skip).limit(limit).all()
