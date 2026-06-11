from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from models import (
    Sensor, ThresholdVersion, TemperatureReading, Alarm, AlarmConfirmation,
    AlarmStatusEnum, AlarmTypeEnum, Person, RoleEnum, Zone
)
from schemas import TemperatureReadingCreate, ReadingImportResult


def get_active_threshold(db: Session, sensor_id: int, at_time: datetime) -> Optional[ThresholdVersion]:
    return (
        db.query(ThresholdVersion)
        .filter(
            ThresholdVersion.sensor_id == sensor_id,
            ThresholdVersion.effective_from <= at_time
        )
        .order_by(desc(ThresholdVersion.effective_from))
        .first()
    )


def get_active_alarm(db: Session, sensor_id: int, alarm_type: AlarmTypeEnum) -> Optional[Alarm]:
    active_statuses = [
        AlarmStatusEnum.OPEN,
        AlarmStatusEnum.ACKNOWLEDGED,
        AlarmStatusEnum.PROCESSING,
        AlarmStatusEnum.ESCALATED,
    ]
    return (
        db.query(Alarm)
        .filter(
            Alarm.sensor_id == sensor_id,
            Alarm.alarm_type == alarm_type,
            Alarm.status.in_(active_statuses)
        )
        .order_by(desc(Alarm.created_at))
        .first()
    )


def has_recent_alarm_in_dedup_window(
    db: Session,
    sensor_id: int,
    alarm_type: AlarmTypeEnum,
    threshold: ThresholdVersion,
    trigger_time: datetime
) -> Optional[Alarm]:
    window_start = trigger_time - timedelta(minutes=threshold.dedup_window_minutes)
    return (
        db.query(Alarm)
        .filter(
            Alarm.sensor_id == sensor_id,
            Alarm.alarm_type == alarm_type,
            Alarm.trigger_time >= window_start,
            Alarm.trigger_time <= trigger_time
        )
        .order_by(desc(Alarm.trigger_time))
        .first()
    )


def create_alarm(
    db: Session,
    sensor: Sensor,
    alarm_type: AlarmTypeEnum,
    threshold: Optional[ThresholdVersion],
    trigger_value: Optional[float],
    trigger_time: datetime
) -> Alarm:
    alarm = Alarm(
        sensor_id=sensor.id,
        alarm_type=alarm_type,
        status=AlarmStatusEnum.OPEN,
        threshold_version_id=threshold.id if threshold else None,
        trigger_value=trigger_value,
        trigger_time=trigger_time,
        latest_value=trigger_value,
        latest_time=trigger_time
    )
    db.add(alarm)
    db.flush()
    return alarm


def update_alarm_latest(
    db: Session,
    alarm: Alarm,
    latest_value: float,
    latest_time: datetime
):
    alarm.latest_value = latest_value
    alarm.latest_time = latest_time
    db.flush()


def check_alarm_condition(
    temperature: float,
    threshold: ThresholdVersion
) -> Optional[AlarmTypeEnum]:
    if temperature > threshold.upper_limit:
        return AlarmTypeEnum.OVER_TEMP
    if temperature < threshold.lower_limit:
        return AlarmTypeEnum.UNDER_TEMP
    return None


def process_reading(db: Session, reading: TemperatureReadingCreate) -> Tuple[Optional[Alarm], Optional[str], bool]:
    sensor = db.query(Sensor).filter(Sensor.code == reading.sensor_code).first()
    if not sensor:
        return None, f"Sensor {reading.sensor_code} not found", False

    if not sensor.is_active:
        return None, f"Sensor {reading.sensor_code} is inactive", False

    threshold = get_active_threshold(db, sensor.id, reading.reading_time)
    if not threshold:
        return None, f"No active threshold for sensor {reading.sensor_code} at {reading.reading_time}", False

    db_reading = TemperatureReading(
        sensor_id=sensor.id,
        temperature=reading.temperature,
        reading_time=reading.reading_time
    )
    db.add(db_reading)
    db.flush()

    alarm_type = check_alarm_condition(reading.temperature, threshold)
    is_new = False
    alarm = None

    if alarm_type:
        active_alarm = get_active_alarm(db, sensor.id, alarm_type)

        if active_alarm:
            if reading.reading_time < active_alarm.trigger_time:
                return None, None, False
            if reading.reading_time > (active_alarm.latest_time or active_alarm.trigger_time):
                update_alarm_latest(db, active_alarm, reading.temperature, reading.reading_time)
                alarm = active_alarm
        else:
            recent_alarm = has_recent_alarm_in_dedup_window(
                db, sensor.id, alarm_type, threshold, reading.reading_time
            )
            if recent_alarm:
                if reading.reading_time > (recent_alarm.latest_time or recent_alarm.trigger_time):
                    update_alarm_latest(db, recent_alarm, reading.temperature, reading.reading_time)
                    alarm = recent_alarm
            else:
                alarm = create_alarm(
                    db, sensor, alarm_type, threshold,
                    reading.temperature, reading.reading_time
                )
                is_new = True

    return alarm, None, is_new


def import_readings(db: Session, readings: List[TemperatureReadingCreate]) -> ReadingImportResult:
    sorted_readings = sorted(readings, key=lambda r: r.reading_time)

    total = len(readings)
    successful = 0
    failed = 0
    errors = []
    new_alarms = 0
    updated_alarms = 0
    new_alarm_ids = set()
    updated_alarm_ids = set()

    for reading in sorted_readings:
        try:
            alarm, error, is_new = process_reading(db, reading)
            if error:
                failed += 1
                errors.append(f"{reading.sensor_code} @ {reading.reading_time}: {error}")
            else:
                successful += 1
                if alarm:
                    if is_new:
                        new_alarm_ids.add(alarm.id)
                    else:
                        updated_alarm_ids.add(alarm.id)
        except Exception as e:
            failed += 1
            errors.append(f"{reading.sensor_code} @ {reading.reading_time}: {str(e)}")

    new_alarms = len(new_alarm_ids)
    updated_alarms = len(updated_alarm_ids - new_alarm_ids)

    db.commit()

    return ReadingImportResult(
        total=total,
        successful=successful,
        failed=failed,
        errors=errors,
        new_alarms=new_alarms,
        updated_alarms=updated_alarms
    )


def can_close_alarm(person: Person) -> bool:
    return person.role in [RoleEnum.ADMIN, RoleEnum.OPERATOR]


def can_acknowledge_alarm(person: Person) -> bool:
    return person.role in [RoleEnum.ADMIN, RoleEnum.OPERATOR]


def transition_alarm_status(
    db: Session,
    alarm_id: int,
    person_id: int,
    to_status: AlarmStatusEnum,
    note: Optional[str] = None,
    require_note: bool = False
) -> Tuple[Optional[Alarm], Optional[str]]:
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        return None, "Alarm not found"

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        return None, "Person not found"

    if to_status == AlarmStatusEnum.CLOSED:
        if not can_close_alarm(person):
            return None, "Permission denied: only admin or operator can close alarms"
        if require_note and not note:
            return None, "Resolution note is required to close an alarm"

    if to_status in [AlarmStatusEnum.ACKNOWLEDGED, AlarmStatusEnum.PROCESSING, AlarmStatusEnum.ESCALATED]:
        if not can_acknowledge_alarm(person):
            return None, f"Permission denied: only admin or operator can transition to {to_status.value}"

    from_status = alarm.status

    confirmation = AlarmConfirmation(
        alarm_id=alarm.id,
        person_id=person.id,
        from_status=from_status,
        to_status=to_status,
        note=note
    )
    db.add(confirmation)

    alarm.status = to_status
    if to_status == AlarmStatusEnum.CLOSED and note:
        alarm.resolution_note = note

    db.flush()
    db.commit()
    db.refresh(alarm)

    return alarm, None


def get_alarm_detail(db: Session, alarm_id: int) -> Optional[dict]:
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        return None

    sensor = db.query(Sensor).filter(Sensor.id == alarm.sensor_id).first()
    zone = db.query(Zone).filter(Zone.id == sensor.zone_id).first() if sensor else None

    confirmations = []
    for conf in alarm.confirmations:
        person = db.query(Person).filter(Person.id == conf.person_id).first()
        confirmations.append({
            "id": conf.id,
            "alarm_id": conf.alarm_id,
            "person_id": conf.person_id,
            "person_name": person.name if person else "Unknown",
            "person_role": person.role if person else RoleEnum.OBSERVER,
            "from_status": conf.from_status,
            "to_status": conf.to_status,
            "note": conf.note,
            "created_at": conf.created_at
        })

    return {
        "id": alarm.id,
        "sensor_id": alarm.sensor_id,
        "sensor_code": sensor.code if sensor else "Unknown",
        "sensor_name": sensor.name if sensor else "Unknown",
        "zone_name": zone.name if zone else "Unknown",
        "alarm_type": alarm.alarm_type,
        "status": alarm.status,
        "trigger_value": alarm.trigger_value,
        "trigger_time": alarm.trigger_time,
        "latest_value": alarm.latest_value,
        "latest_time": alarm.latest_time,
        "resolution_note": alarm.resolution_note,
        "created_at": alarm.created_at,
        "updated_at": alarm.updated_at,
        "confirmations": confirmations
    }


def list_alarms(
    db: Session,
    status: Optional[AlarmStatusEnum] = None,
    sensor_id: Optional[int] = None,
    alarm_type: Optional[AlarmTypeEnum] = None,
    skip: int = 0,
    limit: int = 100
) -> List[dict]:
    query = db.query(Alarm)
    if status:
        query = query.filter(Alarm.status == status)
    if sensor_id:
        query = query.filter(Alarm.sensor_id == sensor_id)
    if alarm_type:
        query = query.filter(Alarm.alarm_type == alarm_type)

    alarms = query.order_by(desc(Alarm.created_at)).offset(skip).limit(limit).all()

    result = []
    for alarm in alarms:
        detail = get_alarm_detail(db, alarm.id)
        if detail:
            result.append(detail)

    return result
