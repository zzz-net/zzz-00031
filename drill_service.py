from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import json

import models
import schemas
import crud


def create_drill(db: Session, drill_data: schemas.DrillCreate) -> models.Drill:
    db_drill = models.Drill(
        zone_id=drill_data.zone_id,
        name=drill_data.name,
        target_temp=drill_data.target_temp,
        allowed_fluctuation=drill_data.allowed_fluctuation,
        duration_minutes=drill_data.duration_minutes,
        created_by=drill_data.created_by,
        status=models.DrillStatus.DRAFT
    )
    db.add(db_drill)
    db.flush()

    log = models.DrillOperationLog(
        drill_id=db_drill.id,
        action="created",
        operator_id=drill_data.created_by,
        detail=json.dumps({
            "name": drill_data.name,
            "target_temp": drill_data.target_temp,
            "allowed_fluctuation": drill_data.allowed_fluctuation,
            "duration_minutes": drill_data.duration_minutes
        }, default=str)
    )
    db.add(log)

    db.commit()
    db.refresh(db_drill)
    return db_drill


def get_drill(db: Session, drill_id: int) -> Optional[models.Drill]:
    return db.query(models.Drill).filter(models.Drill.id == drill_id).first()


def list_drills(
    db: Session,
    zone_id: Optional[int] = None,
    status: Optional[models.DrillStatus] = None,
    skip: int = 0,
    limit: int = 100
) -> List[models.Drill]:
    query = db.query(models.Drill)
    if zone_id:
        query = query.filter(models.Drill.zone_id == zone_id)
    if status:
        query = query.filter(models.Drill.status == status)
    return query.order_by(desc(models.Drill.created_at)).offset(skip).limit(limit).all()


def check_drill_conflict(db: Session, zone_id: int, exclude_drill_id: Optional[int] = None) -> Optional[models.Drill]:
    query = db.query(models.Drill).filter(
        models.Drill.zone_id == zone_id,
        models.Drill.status == models.DrillStatus.RUNNING
    )
    if exclude_drill_id:
        query = query.filter(models.Drill.id != exclude_drill_id)
    return query.first()


def import_drill_readings(
    db: Session,
    drill_id: int,
    readings: List[schemas.DrillReadingCreate]
) -> Tuple[int, int, List[str]]:
    drill = get_drill(db, drill_id)
    if not drill:
        return 0, 0, ["Drill not found"]
    if drill.status != models.DrillStatus.DRAFT:
        return 0, 0, ["Cannot import readings: drill is not in draft status"]

    zone_sensors = crud.list_sensors(db, zone_id=drill.zone_id, limit=1000)
    valid_codes = {s.code for s in zone_sensors}

    successful = 0
    failed = 0
    errors = []

    for reading in readings:
        if reading.sensor_code not in valid_codes:
            failed += 1
            errors.append(f"Sensor {reading.sensor_code} not found in zone {drill.zone_id}")
            continue

        db_reading = models.DrillReading(
            drill_id=drill_id,
            sensor_code=reading.sensor_code,
            temperature=reading.temperature,
            reading_time=reading.reading_time
        )
        db.add(db_reading)
        successful += 1

    db.commit()
    return successful, failed, errors


def start_drill(db: Session, drill_id: int, person_id: int) -> Tuple[Optional[models.Drill], Optional[str]]:
    drill = get_drill(db, drill_id)
    if not drill:
        return None, "Drill not found"
    if drill.status != models.DrillStatus.DRAFT:
        return None, f"Cannot start drill in status: {drill.status.value}"

    person = crud.get_person(db, person_id)
    if not person:
        return None, "Person not found"
    if person.role not in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]:
        return None, "Permission denied: only admin or operator can start drills"

    conflict = check_drill_conflict(db, drill.zone_id, exclude_drill_id=drill_id)
    if conflict:
        return None, f"Conflict: zone {drill.zone_id} already has a running drill (id={conflict.id})"

    readings = db.query(models.DrillReading).filter(
        models.DrillReading.drill_id == drill_id
    ).order_by(models.DrillReading.reading_time).all()

    if not readings:
        return None, "Cannot start drill: no readings imported"

    config_snapshot = _build_config_snapshot(db, drill, readings)
    drill.config_snapshot = json.dumps(config_snapshot, default=str, ensure_ascii=False)

    drill.status = models.DrillStatus.RUNNING
    drill.started_by = person_id
    drill.started_at = datetime.now()

    log = models.DrillOperationLog(
        drill_id=drill_id,
        action="started",
        operator_id=person_id,
        detail=json.dumps({"reading_count": len(readings)}, default=str)
    )
    db.add(log)
    db.flush()

    _run_simulation(db, drill, readings)

    db.commit()
    db.refresh(drill)
    return drill, None


def cancel_drill(db: Session, drill_id: int, person_id: int) -> Tuple[Optional[models.Drill], Optional[str]]:
    drill = get_drill(db, drill_id)
    if not drill:
        return None, "Drill not found"
    if drill.status not in [models.DrillStatus.DRAFT, models.DrillStatus.RUNNING]:
        return None, f"Cannot cancel drill in status: {drill.status.value}"

    person = crud.get_person(db, person_id)
    if not person:
        return None, "Person not found"
    if person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only admin can cancel drills"

    previous_status = drill.status.value
    drill.status = models.DrillStatus.CANCELLED
    drill.cancelled_by = person_id
    drill.cancelled_at = datetime.now()

    log = models.DrillOperationLog(
        drill_id=drill_id,
        action="cancelled",
        operator_id=person_id,
        detail=json.dumps({"previous_status": previous_status}, default=str)
    )
    db.add(log)

    db.commit()
    db.refresh(drill)
    return drill, None


def complete_drill(db: Session, drill_id: int, person_id: int) -> Tuple[Optional[models.Drill], Optional[str]]:
    drill = get_drill(db, drill_id)
    if not drill:
        return None, "Drill not found"
    if drill.status != models.DrillStatus.RUNNING:
        return None, f"Cannot complete drill in status: {drill.status.value}"

    person = crud.get_person(db, person_id)
    if not person:
        return None, "Person not found"
    if person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only admin can complete drills"

    drill.status = models.DrillStatus.COMPLETED
    drill.completed_at = datetime.now()

    log = models.DrillOperationLog(
        drill_id=drill_id,
        action="completed",
        operator_id=person_id,
        detail=None
    )
    db.add(log)

    db.commit()
    db.refresh(drill)
    return drill, None


def _build_config_snapshot(db: Session, drill: models.Drill, readings: List[models.DrillReading]) -> dict:
    zone = drill.zone
    sensors = crud.list_sensors(db, zone_id=drill.zone_id, limit=1000)

    sensor_snapshots = []
    for sensor in sensors:
        threshold = crud.get_latest_threshold(db, sensor.id)
        sensor_snapshots.append({
            "id": sensor.id,
            "code": sensor.code,
            "name": sensor.name,
            "is_active": sensor.is_active,
            "offline_timeout_minutes": sensor.offline_timeout_minutes,
            "current_threshold": {
                "upper_limit": threshold.upper_limit if threshold else None,
                "lower_limit": threshold.lower_limit if threshold else None
            } if threshold else None
        })

    sensor_codes = list(set(r.sensor_code for r in readings))
    time_range = [readings[0].reading_time.isoformat(), readings[-1].reading_time.isoformat()] if readings else []

    return {
        "drill": {
            "id": drill.id,
            "name": drill.name,
            "zone_id": drill.zone_id,
            "zone_name": zone.name if zone else None,
            "target_temp": drill.target_temp,
            "allowed_fluctuation": drill.allowed_fluctuation,
            "duration_minutes": drill.duration_minutes,
            "upper_limit": drill.target_temp + drill.allowed_fluctuation,
            "lower_limit": drill.target_temp - drill.allowed_fluctuation
        },
        "sensors": sensor_snapshots,
        "reading_summary": {
            "total_count": len(readings),
            "sensor_codes": sensor_codes,
            "time_range": time_range
        }
    }


def _run_simulation(db: Session, drill: models.Drill, readings: List[models.DrillReading]):
    upper_limit = drill.target_temp + drill.allowed_fluctuation
    lower_limit = drill.target_temp - drill.allowed_fluctuation

    sensor_cache = {}
    zone_sensors = crud.list_sensors(db, zone_id=drill.zone_id, limit=1000)
    for s in zone_sensors:
        sensor_cache[s.code] = s

    last_reading_time = {}
    active_alarms = {}

    for reading in readings:
        sensor_code = reading.sensor_code
        temperature = reading.temperature
        reading_time = reading.reading_time

        sensor = sensor_cache.get(sensor_code)
        offline_timeout = sensor.offline_timeout_minutes if sensor else 30

        if sensor_code in last_reading_time:
            gap_minutes = (reading_time - last_reading_time[sensor_code]).total_seconds() / 60.0
            if gap_minutes > offline_timeout:
                offline_trigger_time = last_reading_time[sensor_code] + timedelta(minutes=offline_timeout)
                offline_key = (sensor_code, models.AlarmTypeEnum.OFFLINE)
                if offline_key not in active_alarms:
                    active_alarms[offline_key] = {
                        "status": "open",
                        "trigger_value": None,
                        "trigger_time": offline_trigger_time,
                        "max_deviation": 0
                    }

                    db.add(models.DrillJudgment(
                        drill_id=drill.id,
                        sensor_code=sensor_code,
                        temperature=temperature,
                        reading_time=reading_time,
                        alarm_type=models.AlarmTypeEnum.OFFLINE,
                        action=models.DrillAction.TRIGGER,
                        previous_alarm_status=None,
                        current_alarm_status="open",
                        detail=json.dumps({
                            "offline_trigger_time": offline_trigger_time.isoformat(),
                            "gap_minutes": gap_minutes
                        }, default=str)
                    ))

                    db.add(models.DrillAlarmChange(
                        drill_id=drill.id,
                        sensor_code=sensor_code,
                        alarm_type=models.AlarmTypeEnum.OFFLINE,
                        change_type=models.DrillAlarmChangeType.NEW_ALARM,
                        from_status=None,
                        to_status="open",
                        trigger_value=None,
                        trigger_time=offline_trigger_time,
                        detail=None
                    ))
                else:
                    alarm_info = active_alarms[offline_key]
                    db.add(models.DrillJudgment(
                        drill_id=drill.id,
                        sensor_code=sensor_code,
                        temperature=temperature,
                        reading_time=reading_time,
                        alarm_type=models.AlarmTypeEnum.OFFLINE,
                        action=models.DrillAction.UPDATE,
                        previous_alarm_status=alarm_info["status"],
                        current_alarm_status=alarm_info["status"],
                        detail=json.dumps({
                            "gap_minutes": gap_minutes
                        }, default=str)
                    ))

        alarm_type = None
        if temperature > upper_limit:
            alarm_type = models.AlarmTypeEnum.OVER_TEMP
        elif temperature < lower_limit:
            alarm_type = models.AlarmTypeEnum.UNDER_TEMP

        if alarm_type:
            key = (sensor_code, alarm_type)
            if key in active_alarms:
                alarm_info = active_alarms[key]
                is_escalation = False

                if alarm_type == models.AlarmTypeEnum.OVER_TEMP:
                    deviation = temperature - upper_limit
                    if deviation > alarm_info["max_deviation"]:
                        is_escalation = True
                        alarm_info["max_deviation"] = deviation
                elif alarm_type == models.AlarmTypeEnum.UNDER_TEMP:
                    deviation = lower_limit - temperature
                    if deviation > alarm_info["max_deviation"]:
                        is_escalation = True
                        alarm_info["max_deviation"] = deviation

                prev_status = alarm_info["status"]

                if is_escalation:
                    new_status = "escalated"
                    action = models.DrillAction.ESCALATE
                    change_type = models.DrillAlarmChangeType.ESCALATED
                else:
                    new_status = prev_status
                    action = models.DrillAction.UPDATE
                    change_type = models.DrillAlarmChangeType.STATUS_UPDATE

                alarm_info["status"] = new_status

                db.add(models.DrillJudgment(
                    drill_id=drill.id,
                    sensor_code=sensor_code,
                    temperature=temperature,
                    reading_time=reading_time,
                    alarm_type=alarm_type,
                    action=action,
                    previous_alarm_status=prev_status,
                    current_alarm_status=new_status,
                    detail=json.dumps({
                        "upper_limit": upper_limit,
                        "lower_limit": lower_limit,
                        "deviation": temperature - upper_limit if alarm_type == models.AlarmTypeEnum.OVER_TEMP else lower_limit - temperature,
                        "is_escalation": is_escalation
                    }, default=str)
                ))

                db.add(models.DrillAlarmChange(
                    drill_id=drill.id,
                    sensor_code=sensor_code,
                    alarm_type=alarm_type,
                    change_type=change_type,
                    from_status=prev_status,
                    to_status=new_status,
                    trigger_value=temperature,
                    trigger_time=reading_time,
                    detail=None
                ))
            else:
                deviation = 0.0
                if alarm_type == models.AlarmTypeEnum.OVER_TEMP:
                    deviation = temperature - upper_limit
                elif alarm_type == models.AlarmTypeEnum.UNDER_TEMP:
                    deviation = lower_limit - temperature

                active_alarms[key] = {
                    "status": "open",
                    "trigger_value": temperature,
                    "trigger_time": reading_time,
                    "max_deviation": deviation
                }

                db.add(models.DrillJudgment(
                    drill_id=drill.id,
                    sensor_code=sensor_code,
                    temperature=temperature,
                    reading_time=reading_time,
                    alarm_type=alarm_type,
                    action=models.DrillAction.TRIGGER,
                    previous_alarm_status=None,
                    current_alarm_status="open",
                    detail=json.dumps({
                        "upper_limit": upper_limit,
                        "lower_limit": lower_limit,
                        "deviation": deviation
                    }, default=str)
                ))

                db.add(models.DrillAlarmChange(
                    drill_id=drill.id,
                    sensor_code=sensor_code,
                    alarm_type=alarm_type,
                    change_type=models.DrillAlarmChangeType.NEW_ALARM,
                    from_status=None,
                    to_status="open",
                    trigger_value=temperature,
                    trigger_time=reading_time,
                    detail=None
                ))
        else:
            recovered_types = []
            for atype in [models.AlarmTypeEnum.OVER_TEMP, models.AlarmTypeEnum.UNDER_TEMP]:
                key = (sensor_code, atype)
                if key in active_alarms:
                    recovered_types.append((atype, active_alarms.pop(key)))

            if recovered_types:
                for atype, alarm_info in recovered_types:
                    prev_status = alarm_info["status"]

                    db.add(models.DrillJudgment(
                        drill_id=drill.id,
                        sensor_code=sensor_code,
                        temperature=temperature,
                        reading_time=reading_time,
                        alarm_type=atype,
                        action=models.DrillAction.RECOVER,
                        previous_alarm_status=prev_status,
                        current_alarm_status="closed",
                        detail=json.dumps({
                            "upper_limit": upper_limit,
                            "lower_limit": lower_limit,
                            "recovery_temperature": temperature
                        }, default=str)
                    ))

                    db.add(models.DrillAlarmChange(
                        drill_id=drill.id,
                        sensor_code=sensor_code,
                        alarm_type=atype,
                        change_type=models.DrillAlarmChangeType.RECOVERED,
                        from_status=prev_status,
                        to_status="closed",
                        trigger_value=temperature,
                        trigger_time=reading_time,
                        detail=None
                    ))
            else:
                db.add(models.DrillJudgment(
                    drill_id=drill.id,
                    sensor_code=sensor_code,
                    temperature=temperature,
                    reading_time=reading_time,
                    alarm_type=None,
                    action=models.DrillAction.NONE,
                    previous_alarm_status=None,
                    current_alarm_status=None,
                    detail=json.dumps({
                        "upper_limit": upper_limit,
                        "lower_limit": lower_limit
                    }, default=str)
                ))

        last_reading_time[sensor_code] = reading_time

    db.flush()


def build_drill_detail(db: Session, drill: models.Drill) -> dict:
    zone = drill.zone
    creator = drill.creator
    starter = drill.starter
    canceller = drill.canceller

    reading_count = len(drill.readings) if drill.readings else 0
    judgment_count = len(drill.judgments) if drill.judgments else 0
    alarm_change_count = len(drill.alarm_changes) if drill.alarm_changes else 0

    return {
        "id": drill.id,
        "zone_id": drill.zone_id,
        "zone_name": zone.name if zone else None,
        "name": drill.name,
        "target_temp": drill.target_temp,
        "allowed_fluctuation": drill.allowed_fluctuation,
        "duration_minutes": drill.duration_minutes,
        "status": drill.status,
        "upper_limit": drill.target_temp + drill.allowed_fluctuation,
        "lower_limit": drill.target_temp - drill.allowed_fluctuation,
        "created_by": drill.created_by,
        "creator_name": creator.name if creator else None,
        "creator_role": creator.role if creator else None,
        "started_by": drill.started_by,
        "starter_name": starter.name if starter else None,
        "started_at": drill.started_at,
        "completed_at": drill.completed_at,
        "cancelled_by": drill.cancelled_by,
        "canceller_name": canceller.name if canceller else None,
        "cancelled_at": drill.cancelled_at,
        "config_snapshot": drill.config_snapshot,
        "reading_count": reading_count,
        "judgment_count": judgment_count,
        "alarm_change_count": alarm_change_count,
        "created_at": drill.created_at,
        "updated_at": drill.updated_at,
    }


def build_drill_full_detail(db: Session, drill: models.Drill) -> dict:
    detail = build_drill_detail(db, drill)

    judgments = []
    for j in (drill.judgments or []):
        judgments.append({
            "id": j.id,
            "drill_id": j.drill_id,
            "sensor_code": j.sensor_code,
            "temperature": j.temperature,
            "reading_time": j.reading_time,
            "alarm_type": j.alarm_type,
            "action": j.action,
            "previous_alarm_status": j.previous_alarm_status,
            "current_alarm_status": j.current_alarm_status,
            "detail": j.detail,
            "created_at": j.created_at,
        })

    alarm_changes = []
    for ac in (drill.alarm_changes or []):
        alarm_changes.append({
            "id": ac.id,
            "drill_id": ac.drill_id,
            "sensor_code": ac.sensor_code,
            "alarm_type": ac.alarm_type,
            "change_type": ac.change_type,
            "from_status": ac.from_status,
            "to_status": ac.to_status,
            "trigger_value": ac.trigger_value,
            "trigger_time": ac.trigger_time,
            "detail": ac.detail,
            "created_at": ac.created_at,
        })

    operation_logs = []
    for ol in (drill.operation_logs or []):
        operator = ol.operator
        operation_logs.append({
            "id": ol.id,
            "drill_id": ol.drill_id,
            "action": ol.action,
            "operator_id": ol.operator_id,
            "operator_name": operator.name if operator else None,
            "operator_role": operator.role if operator else None,
            "detail": ol.detail,
            "created_at": ol.created_at,
        })

    detail["judgments"] = judgments
    detail["alarm_changes"] = alarm_changes
    detail["operation_logs"] = operation_logs
    return detail


def build_drill_export(db: Session, drill: models.Drill) -> dict:
    full = build_drill_full_detail(db, drill)

    config_snapshot = None
    if drill.config_snapshot:
        try:
            config_snapshot = json.loads(drill.config_snapshot)
        except (json.JSONDecodeError, TypeError):
            config_snapshot = drill.config_snapshot

    return {
        "config_snapshot": config_snapshot,
        "judgments": full["judgments"],
        "alarm_changes": full["alarm_changes"],
        "operation_logs": full["operation_logs"]
    }
