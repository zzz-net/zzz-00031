from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import List, Optional
import io
import csv
import json

from database import engine, get_db, Base
import models
import schemas
import crud
import alarm_service
import drill_service

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="冷库温控报警确认 API",
    description="Cold Storage Temperature Alarm Confirmation API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {"message": "Cold Storage Temperature Alarm API", "version": "1.0.0"}


# ========== Zone APIs ==========

@app.post("/zones", response_model=schemas.Zone, tags=["Zones"])
def create_zone(zone: schemas.ZoneCreate, db: Session = Depends(get_db)):
    db_zone = crud.get_zone_by_name(db, name=zone.name)
    if db_zone:
        raise HTTPException(status_code=400, detail="Zone with this name already exists")
    return crud.create_zone(db=db, zone=zone)


@app.get("/zones", response_model=List[schemas.Zone], tags=["Zones"])
def list_zones(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_zones(db, skip=skip, limit=limit)


@app.get("/zones/{zone_id}", response_model=schemas.Zone, tags=["Zones"])
def get_zone(zone_id: int, db: Session = Depends(get_db)):
    db_zone = crud.get_zone(db, zone_id=zone_id)
    if db_zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return db_zone


# ========== Person APIs ==========

@app.post("/persons", response_model=schemas.Person, tags=["Persons"])
def create_person(person: schemas.PersonCreate, db: Session = Depends(get_db)):
    return crud.create_person(db=db, person=person)


@app.get("/persons", response_model=List[schemas.Person], tags=["Persons"])
def list_persons(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_persons(db, skip=skip, limit=limit)


@app.get("/persons/{person_id}", response_model=schemas.Person, tags=["Persons"])
def get_person(person_id: int, db: Session = Depends(get_db)):
    db_person = crud.get_person(db, person_id=person_id)
    if db_person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return db_person


# ========== Sensor APIs ==========

@app.post("/sensors", response_model=schemas.Sensor, tags=["Sensors"])
def create_sensor(sensor: schemas.SensorCreate, db: Session = Depends(get_db)):
    db_sensor = crud.get_sensor_by_code(db, code=sensor.code)
    if db_sensor:
        raise HTTPException(status_code=400, detail="Sensor with this code already exists")
    db_zone = crud.get_zone(db, zone_id=sensor.zone_id)
    if db_zone is None:
        raise HTTPException(status_code=400, detail="Zone not found")
    return crud.create_sensor(db=db, sensor=sensor)


@app.get("/sensors", response_model=List[schemas.Sensor], tags=["Sensors"])
def list_sensors(zone_id: Optional[int] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_sensors(db, zone_id=zone_id, skip=skip, limit=limit)


@app.get("/sensors/{sensor_id}", response_model=schemas.Sensor, tags=["Sensors"])
def get_sensor(sensor_id: int, db: Session = Depends(get_db)):
    db_sensor = crud.get_sensor(db, sensor_id=sensor_id)
    if db_sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return db_sensor


@app.put("/sensors/{sensor_id}", response_model=schemas.Sensor, tags=["Sensors"])
def update_sensor(sensor_id: int, sensor_update: schemas.SensorUpdate, db: Session = Depends(get_db)):
    db_sensor = crud.update_sensor(db, sensor_id=sensor_id, sensor_update=sensor_update)
    if db_sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return db_sensor


# ========== Threshold APIs ==========

@app.post("/thresholds", response_model=schemas.ThresholdVersion, tags=["Thresholds"])
def create_threshold(threshold: schemas.ThresholdVersionCreate, db: Session = Depends(get_db)):
    db_sensor = crud.get_sensor(db, sensor_id=threshold.sensor_id)
    if db_sensor is None:
        raise HTTPException(status_code=400, detail="Sensor not found")
    return crud.create_threshold_version(db=db, threshold=threshold)


@app.get("/sensors/{sensor_id}/thresholds", response_model=List[schemas.ThresholdVersion], tags=["Thresholds"])
def list_thresholds(sensor_id: int, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud.get_threshold_versions(db, sensor_id=sensor_id, skip=skip, limit=limit)


# ========== Reading APIs ==========

@app.post("/readings/import", response_model=schemas.ReadingImportResult, tags=["Readings"])
def import_readings(readings: List[schemas.TemperatureReadingCreate], db: Session = Depends(get_db)):
    return alarm_service.import_readings(db, readings)


@app.post("/readings/import-json", response_model=schemas.ReadingImportResult, tags=["Readings"])
async def import_readings_json(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    try:
        data = json.loads(contents)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="JSON must be a list of readings")

    readings = []
    for item in data:
        try:
            reading = schemas.TemperatureReadingCreate(**item)
            readings.append(reading)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid reading item: {str(e)}")

    return alarm_service.import_readings(db, readings)


@app.post("/readings/import-csv", response_model=schemas.ReadingImportResult, tags=["Readings"])
async def import_readings_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    content_str = contents.decode('utf-8')

    reader = csv.DictReader(io.StringIO(content_str))
    readings = []

    required_fields = {'sensor_code', 'temperature', 'reading_time'}
    if not required_fields.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns: {', '.join(required_fields)}"
        )

    for row in reader:
        try:
            reading = schemas.TemperatureReadingCreate(
                sensor_code=row['sensor_code'],
                temperature=float(row['temperature']),
                reading_time=datetime.fromisoformat(row['reading_time'])
            )
            readings.append(reading)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid row {row}: {str(e)}")

    return alarm_service.import_readings(db, readings)


@app.get("/readings", response_model=List[schemas.TemperatureReading], tags=["Readings"])
def list_readings(
    sensor_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    return crud.list_readings(db, sensor_id=sensor_id, start=start, end=end, skip=skip, limit=limit)


@app.get("/readings/export.csv", tags=["Readings"])
def export_readings_csv(
    sensor_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    readings = crud.list_readings(db, sensor_id=sensor_id, start=start, end=end, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'sensor_id', 'temperature', 'reading_time', 'imported_at'])

    for r in readings:
        writer.writerow([r.id, r.sensor_id, r.temperature, r.reading_time.isoformat(), r.imported_at.isoformat()])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=readings.csv"}
    )


# ========== Alarm APIs ==========

@app.get("/alarms", tags=["Alarms"])
def list_alarms(
    status: Optional[schemas.AlarmStatusEnum] = None,
    sensor_id: Optional[int] = None,
    alarm_type: Optional[schemas.AlarmTypeEnum] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return alarm_service.list_alarms(db, status=status, sensor_id=sensor_id, alarm_type=alarm_type, skip=skip, limit=limit)


@app.get("/alarms/export.csv", tags=["Alarms"])
def export_alarms_csv(
    status: Optional[schemas.AlarmStatusEnum] = None,
    sensor_id: Optional[int] = None,
    alarm_type: Optional[schemas.AlarmTypeEnum] = None,
    db: Session = Depends(get_db)
):
    alarms = alarm_service.list_alarms(db, status=status, sensor_id=sensor_id, alarm_type=alarm_type, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'sensor_code', 'sensor_name', 'zone_name', 'alarm_type',
        'status', 'suppression_rule_id', 'suppression_rule_reason',
        'trigger_value', 'trigger_time', 'latest_value',
        'latest_time', 'resolution_note', 'created_at', 'updated_at'
    ])

    for a in alarms:
        alarm_type_val = a['alarm_type'].value if hasattr(a['alarm_type'], 'value') else str(a['alarm_type'])
        status_val = a['status'].value if hasattr(a['status'], 'value') else str(a['status'])
        writer.writerow([
            a['id'], a['sensor_code'], a['sensor_name'], a['zone_name'],
            alarm_type_val,
            status_val,
            a.get('suppression_rule_id') or '',
            a.get('suppression_rule_reason') or '',
            a['trigger_value'],
            a['trigger_time'].isoformat() if a['trigger_time'] else '',
            a['latest_value'],
            a['latest_time'].isoformat() if a['latest_time'] else '',
            a['resolution_note'] or '',
            a['created_at'].isoformat() if a['created_at'] else '',
            a['updated_at'].isoformat() if a['updated_at'] else ''
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alarms.csv"}
    )


@app.get("/alarms/export.json", tags=["Alarms"])
def export_alarms_json(
    status: Optional[schemas.AlarmStatusEnum] = None,
    sensor_id: Optional[int] = None,
    alarm_type: Optional[schemas.AlarmTypeEnum] = None,
    db: Session = Depends(get_db)
):
    alarms = alarm_service.list_alarms(db, status=status, sensor_id=sensor_id, alarm_type=alarm_type, limit=10000)

    json_str = json.dumps(alarms, default=str, ensure_ascii=False, indent=2)

    return StreamingResponse(
        io.BytesIO(json_str.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=alarms.json"}
    )


@app.get("/alarms/{alarm_id}", tags=["Alarms"])
def get_alarm(alarm_id: int, db: Session = Depends(get_db)):
    detail = alarm_service.get_alarm_detail(db, alarm_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return detail


@app.post("/alarms/{alarm_id}/acknowledge", tags=["Alarms"])
def acknowledge_alarm(alarm_id: int, update: schemas.AlarmStatusUpdate, db: Session = Depends(get_db)):
    alarm, error = alarm_service.transition_alarm_status(
        db, alarm_id, update.person_id, schemas.AlarmStatusEnum.ACKNOWLEDGED, update.note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return alarm_service.get_alarm_detail(db, alarm_id)


@app.post("/alarms/{alarm_id}/processing", tags=["Alarms"])
def set_processing_alarm(alarm_id: int, update: schemas.AlarmStatusUpdate, db: Session = Depends(get_db)):
    alarm, error = alarm_service.transition_alarm_status(
        db, alarm_id, update.person_id, schemas.AlarmStatusEnum.PROCESSING, update.note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return alarm_service.get_alarm_detail(db, alarm_id)


@app.post("/alarms/{alarm_id}/escalate", tags=["Alarms"])
def escalate_alarm(alarm_id: int, update: schemas.AlarmStatusUpdate, db: Session = Depends(get_db)):
    alarm, error = alarm_service.transition_alarm_status(
        db, alarm_id, update.person_id, schemas.AlarmStatusEnum.ESCALATED, update.note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return alarm_service.get_alarm_detail(db, alarm_id)


@app.post("/alarms/{alarm_id}/close", tags=["Alarms"])
def close_alarm(alarm_id: int, update: schemas.AlarmCloseUpdate, db: Session = Depends(get_db)):
    alarm, error = alarm_service.transition_alarm_status(
        db, alarm_id, update.person_id, schemas.AlarmStatusEnum.CLOSED,
        update.resolution_note, require_note=True
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return alarm_service.get_alarm_detail(db, alarm_id)


# ========== Suppression Rule APIs ==========

def _can_manage_suppression(person: models.Person) -> bool:
    return person.role in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]


def _build_suppression_detail(db: Session, rule: models.SuppressionRule) -> dict:
    sensor = rule.sensor
    zone = rule.zone
    creator = rule.creator
    revoker = rule.revoker
    hit_count = len(rule.hits) if rule.hits else 0

    return {
        "id": rule.id,
        "sensor_id": rule.sensor_id,
        "zone_id": rule.zone_id,
        "alarm_type": rule.alarm_type,
        "start_time": rule.start_time,
        "end_time": rule.end_time,
        "reason": rule.reason,
        "status": rule.status,
        "created_by": rule.created_by,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
        "sensor_code": sensor.code if sensor else None,
        "sensor_name": sensor.name if sensor else None,
        "zone_name": zone.name if zone else None,
        "creator_name": creator.name if creator else None,
        "creator_role": creator.role if creator else None,
        "revoked_by": rule.revoked_by,
        "revoked_at": rule.revoked_at,
        "revoker_name": revoker.name if revoker else None,
        "hit_count": hit_count
    }


@app.post("/suppression-rules", response_model=schemas.SuppressionRuleDetail, tags=["Suppression Rules"])
def create_suppression_rule(rule: schemas.SuppressionRuleCreate, db: Session = Depends(get_db)):
    person = crud.get_person(db, rule.created_by)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_suppression(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can create suppression rules")

    if rule.sensor_id is None and rule.zone_id is None:
        raise HTTPException(status_code=400, detail="Either sensor_id or zone_id must be provided")

    if rule.end_time <= rule.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    if rule.sensor_id:
        sensor = crud.get_sensor(db, rule.sensor_id)
        if not sensor:
            raise HTTPException(status_code=400, detail="Sensor not found")

    if rule.zone_id:
        zone = crud.get_zone(db, rule.zone_id)
        if not zone:
            raise HTTPException(status_code=400, detail="Zone not found")

    conflicts = crud.check_suppression_conflict(
        db,
        sensor_id=rule.sensor_id,
        zone_id=rule.zone_id,
        alarm_type=rule.alarm_type,
        start_time=rule.start_time,
        end_time=rule.end_time
    )
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=f"Conflict with existing suppression rule(s): {[c.id for c in conflicts]}"
        )

    db_rule = crud.create_suppression_rule(db, rule)
    return _build_suppression_detail(db, db_rule)


@app.get("/suppression-rules", response_model=List[schemas.SuppressionRuleDetail], tags=["Suppression Rules"])
def list_suppression_rules(
    sensor_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    status: Optional[schemas.SuppressionRuleStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    rules = crud.list_suppression_rules(db, sensor_id=sensor_id, zone_id=zone_id, status=status, skip=skip, limit=limit)
    return [_build_suppression_detail(db, r) for r in rules]


@app.get("/suppression-rules/export.csv", tags=["Suppression Rules"])
def export_suppression_rules_csv(
    status: Optional[schemas.SuppressionRuleStatus] = None,
    db: Session = Depends(get_db)
):
    rules = crud.list_suppression_rules(db, status=status, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'sensor_id', 'sensor_code', 'zone_id', 'zone_name',
        'alarm_type', 'start_time', 'end_time', 'reason', 'status',
        'created_by', 'creator_name', 'created_at', 'revoked_by', 'revoked_at', 'hit_count'
    ])

    for rule in rules:
        detail = _build_suppression_detail(db, rule)
        alarm_type_val = detail['alarm_type'].value if detail['alarm_type'] and hasattr(detail['alarm_type'], 'value') else (detail['alarm_type'] or '')
        status_val = detail['status'].value if hasattr(detail['status'], 'value') else str(detail['status'])
        writer.writerow([
            detail['id'],
            detail['sensor_id'] or '',
            detail['sensor_code'] or '',
            detail['zone_id'] or '',
            detail['zone_name'] or '',
            alarm_type_val,
            detail['start_time'].isoformat() if detail['start_time'] else '',
            detail['end_time'].isoformat() if detail['end_time'] else '',
            detail['reason'],
            status_val,
            detail['created_by'],
            detail['creator_name'] or '',
            detail['created_at'].isoformat() if detail['created_at'] else '',
            detail['revoked_by'] or '',
            detail['revoked_at'].isoformat() if detail['revoked_at'] else '',
            detail['hit_count']
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=suppression_rules.csv"}
    )


@app.get("/suppression-rules/{rule_id}", response_model=schemas.SuppressionRuleDetail, tags=["Suppression Rules"])
def get_suppression_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = crud.get_suppression_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Suppression rule not found")
    return _build_suppression_detail(db, rule)


@app.post("/suppression-rules/{rule_id}/revoke", response_model=schemas.SuppressionRuleDetail, tags=["Suppression Rules"])
def revoke_suppression_rule(rule_id: int, body: dict, db: Session = Depends(get_db)):
    person_id = body.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="person_id is required")

    person = crud.get_person(db, person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_suppression(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can revoke suppression rules")

    rule = crud.revoke_suppression_rule(db, rule_id, person_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Suppression rule not found")
    return _build_suppression_detail(db, rule)


@app.get("/suppression-rules/{rule_id}/hits", response_model=List[schemas.SuppressionHit], tags=["Suppression Rules"])
def list_suppression_hits(rule_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    rule = crud.get_suppression_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Suppression rule not found")

    hits = crud.list_suppression_hits(db, rule_id=rule_id, skip=skip, limit=limit)
    result = []
    for hit in hits:
        sensor = crud.get_sensor(db, hit.sensor_id)
        result.append({
            "id": hit.id,
            "rule_id": hit.rule_id,
            "alarm_id": hit.alarm_id,
            "sensor_id": hit.sensor_id,
            "sensor_code": sensor.code if sensor else None,
            "alarm_type": hit.alarm_type,
            "trigger_value": hit.trigger_value,
            "trigger_time": hit.trigger_time,
            "created_at": hit.created_at
        })
    return result


@app.get("/suppression-hits/export.csv", tags=["Suppression Rules"])
def export_suppression_hits_csv(
    rule_id: Optional[int] = None,
    sensor_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    hits = crud.list_suppression_hits(db, rule_id=rule_id, sensor_id=sensor_id, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'rule_id', 'alarm_id', 'sensor_id', 'sensor_code',
        'alarm_type', 'trigger_value', 'trigger_time', 'created_at'
    ])

    for hit in hits:
        sensor = crud.get_sensor(db, hit.sensor_id)
        alarm_type_val = hit.alarm_type.value if hasattr(hit.alarm_type, 'value') else str(hit.alarm_type)
        writer.writerow([
            hit.id, hit.rule_id, hit.alarm_id, hit.sensor_id,
            sensor.code if sensor else '',
            alarm_type_val,
            hit.trigger_value if hit.trigger_value is not None else '',
            hit.trigger_time.isoformat() if hit.trigger_time else '',
            hit.created_at.isoformat() if hit.created_at else ''
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=suppression_hits.csv"}
    )


# ========== Shift Checklist APIs ==========

def _can_manage_checklist(person: models.Person) -> bool:
    return person.role in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]


def _build_sensor_item_detail(db: Session, item: models.ShiftChecklistSensorItem) -> dict:
    sensor = item.sensor
    checker = item.checker
    handler = item.handler
    return {
        "id": item.id,
        "checklist_id": item.checklist_id,
        "sensor_id": item.sensor_id,
        "sensor_code": sensor.code if sensor else None,
        "sensor_name": sensor.name if sensor else None,
        "snapshot_threshold_upper": item.snapshot_threshold_upper,
        "snapshot_threshold_lower": item.snapshot_threshold_lower,
        "snapshot_latest_reading_value": item.snapshot_latest_reading_value,
        "snapshot_latest_reading_time": item.snapshot_latest_reading_time,
        "snapshot_open_alarm_count": item.snapshot_open_alarm_count,
        "snapshot_open_alarm_ids": item.snapshot_open_alarm_ids,
        "check_status": item.check_status,
        "checked_by": item.checked_by,
        "checked_by_name": checker.name if checker else None,
        "checked_at": item.checked_at,
        "abnormal_remark": item.abnormal_remark,
        "handler_id": item.handler_id,
        "handler_name": handler.name if handler else None,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _build_manual_item_detail(db: Session, item: models.ShiftChecklistManualItem) -> dict:
    checker = item.checker
    handler = item.handler
    return {
        "id": item.id,
        "checklist_id": item.checklist_id,
        "item_name": item.item_name,
        "item_description": item.item_description,
        "check_status": item.check_status,
        "checked_by": item.checked_by,
        "checked_by_name": checker.name if checker else None,
        "checked_at": item.checked_at,
        "abnormal_remark": item.abnormal_remark,
        "handler_id": item.handler_id,
        "handler_name": handler.name if handler else None,
        "sort_order": item.sort_order,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _build_checklist_detail(db: Session, checklist: models.ShiftChecklist) -> dict:
    zone = checklist.zone
    creator = checklist.creator
    submitter = checklist.submitter
    revoker = checklist.revoker

    sensor_items = [
        _build_sensor_item_detail(db, si) for si in checklist.sensor_items
    ]
    manual_items = [
        _build_manual_item_detail(db, mi) for mi in checklist.manual_items
    ]

    return {
        "id": checklist.id,
        "zone_id": checklist.zone_id,
        "zone_name": zone.name if zone else None,
        "shift_date": checklist.shift_date,
        "shift_type": checklist.shift_type,
        "status": checklist.status,
        "created_by": checklist.created_by,
        "creator_name": creator.name if creator else None,
        "creator_role": creator.role if creator else None,
        "submitted_by": checklist.submitted_by,
        "submitter_name": submitter.name if submitter else None,
        "submitted_at": checklist.submitted_at,
        "revoked_by": checklist.revoked_by,
        "revoker_name": revoker.name if revoker else None,
        "revoked_at": checklist.revoked_at,
        "general_remark": checklist.general_remark,
        "created_at": checklist.created_at,
        "updated_at": checklist.updated_at,
        "sensor_items": sensor_items,
        "manual_items": manual_items,
    }


def _build_checklist_list_item(db: Session, checklist: models.ShiftChecklist) -> dict:
    zone = checklist.zone
    creator = checklist.creator
    submitter = checklist.submitter
    revoker = checklist.revoker

    sensor_item_count = len(checklist.sensor_items) if checklist.sensor_items else 0
    manual_item_count = len(checklist.manual_items) if checklist.manual_items else 0

    all_items = (checklist.sensor_items or []) + (checklist.manual_items or [])
    pending_count = sum(1 for i in all_items if i.check_status == models.CheckItemStatus.PENDING)
    abnormal_count = sum(1 for i in all_items if i.check_status == models.CheckItemStatus.ABNORMAL)

    return {
        "id": checklist.id,
        "zone_id": checklist.zone_id,
        "zone_name": zone.name if zone else None,
        "shift_date": checklist.shift_date,
        "shift_type": checklist.shift_type,
        "status": checklist.status,
        "created_by": checklist.created_by,
        "creator_name": creator.name if creator else None,
        "creator_role": creator.role if creator else None,
        "submitted_by": checklist.submitted_by,
        "submitter_name": submitter.name if submitter else None,
        "submitted_at": checklist.submitted_at,
        "revoked_by": checklist.revoked_by,
        "revoker_name": revoker.name if revoker else None,
        "revoked_at": checklist.revoked_at,
        "general_remark": checklist.general_remark,
        "created_at": checklist.created_at,
        "updated_at": checklist.updated_at,
        "sensor_item_count": sensor_item_count,
        "manual_item_count": manual_item_count,
        "pending_count": pending_count,
        "abnormal_count": abnormal_count,
    }


@app.post("/shift-checklists", response_model=schemas.ShiftChecklistDetail, tags=["Shift Checklists"])
def create_shift_checklist(checklist: schemas.ShiftChecklistCreate, db: Session = Depends(get_db)):
    person = crud.get_person(db, checklist.created_by)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_checklist(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can create shift checklists")

    zone = crud.get_zone(db, checklist.zone_id)
    if not zone:
        raise HTTPException(status_code=400, detail="Zone not found")

    conflict = crud.check_shift_checklist_conflict(
        db, zone_id=checklist.zone_id,
        shift_date=checklist.shift_date,
        shift_type=checklist.shift_type
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate shift checklist: zone_id={checklist.zone_id}, "
                   f"shift_date={checklist.shift_date}, shift_type={checklist.shift_type} "
                   f"already exists (id={conflict.id}, status={conflict.status.value})"
        )

    db_checklist = crud.create_shift_checklist(db, checklist)
    return _build_checklist_detail(db, db_checklist)


@app.get("/shift-checklists", response_model=List[schemas.ShiftChecklistList], tags=["Shift Checklists"])
def list_shift_checklists(
    zone_id: Optional[int] = None,
    status: Optional[schemas.ChecklistStatus] = None,
    shift_type: Optional[schemas.ShiftEnum] = None,
    shift_date_from: Optional[date] = None,
    shift_date_to: Optional[date] = None,
    created_by: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    checklists = crud.list_shift_checklists(
        db, zone_id=zone_id, status=status, shift_type=shift_type,
        shift_date_from=shift_date_from, shift_date_to=shift_date_to,
        created_by=created_by, skip=skip, limit=limit
    )
    return [_build_checklist_list_item(db, c) for c in checklists]


@app.get("/shift-checklists/export.csv", tags=["Shift Checklists"])
def export_shift_checklists_csv(
    zone_id: Optional[int] = None,
    status: Optional[schemas.ChecklistStatus] = None,
    shift_type: Optional[schemas.ShiftEnum] = None,
    shift_date_from: Optional[date] = None,
    shift_date_to: Optional[date] = None,
    db: Session = Depends(get_db)
):
    checklists = crud.list_shift_checklists(
        db, zone_id=zone_id, status=status, shift_type=shift_type,
        shift_date_from=shift_date_from, shift_date_to=shift_date_to,
        limit=10000
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'zone_id', 'zone_name', 'shift_date', 'shift_type', 'status',
        'created_by', 'creator_name', 'submitted_by', 'submitter_name',
        'submitted_at', 'revoked_by', 'revoker_name', 'revoked_at',
        'general_remark', 'sensor_item_count', 'manual_item_count',
        'pending_count', 'abnormal_count', 'created_at', 'updated_at'
    ])

    for checklist in checklists:
        detail = _build_checklist_list_item(db, checklist)
        status_val = detail['status'].value if hasattr(detail['status'], 'value') else str(detail['status'])
        shift_type_val = detail['shift_type'].value if hasattr(detail['shift_type'], 'value') else str(detail['shift_type'])
        writer.writerow([
            detail['id'],
            detail['zone_id'],
            detail['zone_name'] or '',
            detail['shift_date'],
            shift_type_val,
            status_val,
            detail['created_by'],
            detail['creator_name'] or '',
            detail['submitted_by'] or '',
            detail['submitter_name'] or '',
            detail['submitted_at'].isoformat() if detail['submitted_at'] else '',
            detail['revoked_by'] or '',
            detail['revoker_name'] or '',
            detail['revoked_at'].isoformat() if detail['revoked_at'] else '',
            detail['general_remark'] or '',
            detail['sensor_item_count'],
            detail['manual_item_count'],
            detail['pending_count'],
            detail['abnormal_count'],
            detail['created_at'].isoformat() if detail['created_at'] else '',
            detail['updated_at'].isoformat() if detail['updated_at'] else ''
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=shift_checklists.csv"}
    )


@app.get("/shift-checklists/export.json", tags=["Shift Checklists"])
def export_shift_checklists_json(
    zone_id: Optional[int] = None,
    status: Optional[schemas.ChecklistStatus] = None,
    shift_type: Optional[schemas.ShiftEnum] = None,
    shift_date_from: Optional[date] = None,
    shift_date_to: Optional[date] = None,
    db: Session = Depends(get_db)
):
    checklists = crud.list_shift_checklists(
        db, zone_id=zone_id, status=status, shift_type=shift_type,
        shift_date_from=shift_date_from, shift_date_to=shift_date_to,
        limit=10000
    )

    result = [_build_checklist_list_item(db, c) for c in checklists]
    json_str = json.dumps(result, default=str, ensure_ascii=False, indent=2)

    return StreamingResponse(
        io.BytesIO(json_str.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=shift_checklists.json"}
    )


@app.get("/shift-checklists/{checklist_id}", response_model=schemas.ShiftChecklistDetail, tags=["Shift Checklists"])
def get_shift_checklist(checklist_id: int, db: Session = Depends(get_db)):
    checklist = crud.get_shift_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(status_code=404, detail="Shift checklist not found")
    return _build_checklist_detail(db, checklist)


@app.post("/shift-checklists/{checklist_id}/submit", response_model=schemas.ShiftChecklistDetail, tags=["Shift Checklists"])
def submit_shift_checklist(checklist_id: int, body: schemas.ShiftChecklistSubmit, db: Session = Depends(get_db)):
    person = crud.get_person(db, body.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_checklist(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can submit shift checklists")

    checklist = crud.submit_shift_checklist(db, checklist_id, body.person_id, body.general_remark)
    if not checklist:
        cl = crud.get_shift_checklist(db, checklist_id)
        if not cl:
            raise HTTPException(status_code=404, detail="Shift checklist not found")
        raise HTTPException(status_code=400, detail=f"Cannot submit checklist in status: {cl.status.value}")

    return _build_checklist_detail(db, checklist)


@app.post("/shift-checklists/{checklist_id}/revoke", response_model=schemas.ShiftChecklistDetail, tags=["Shift Checklists"])
def revoke_shift_checklist(checklist_id: int, body: schemas.ShiftChecklistRevoke, db: Session = Depends(get_db)):
    person = crud.get_person(db, body.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_checklist(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can revoke shift checklists")

    checklist = crud.revoke_shift_checklist(db, checklist_id, body.person_id)
    if not checklist:
        cl = crud.get_shift_checklist(db, checklist_id)
        if not cl:
            raise HTTPException(status_code=404, detail="Shift checklist not found")
        raise HTTPException(status_code=400, detail=f"Cannot revoke checklist in status: {cl.status.value}")

    return _build_checklist_detail(db, checklist)


@app.put("/shift-checklists/{checklist_id}/sensor-items/{item_id}", response_model=schemas.ShiftChecklistSensorItem, tags=["Shift Checklists"])
def update_shift_checklist_sensor_item(
    checklist_id: int,
    item_id: int,
    update: schemas.ShiftChecklistSensorItemUpdate,
    db: Session = Depends(get_db)
):
    person = crud.get_person(db, update.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_checklist(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can update checklist items")

    if update.handler_id is not None:
        handler = crud.get_person(db, update.handler_id)
        if not handler:
            raise HTTPException(status_code=400, detail="Handler person not found")

    item, error = crud.update_shift_checklist_sensor_item(
        db, checklist_id, item_id, update.person_id,
        update.check_status, update.abnormal_remark, update.handler_id
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return _build_sensor_item_detail(db, item)


@app.put("/shift-checklists/{checklist_id}/manual-items/{item_id}", response_model=schemas.ShiftChecklistManualItem, tags=["Shift Checklists"])
def update_shift_checklist_manual_item(
    checklist_id: int,
    item_id: int,
    update: schemas.ShiftChecklistManualItemUpdate,
    db: Session = Depends(get_db)
):
    person = crud.get_person(db, update.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_manage_checklist(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can update checklist items")

    if update.handler_id is not None:
        handler = crud.get_person(db, update.handler_id)
        if not handler:
            raise HTTPException(status_code=400, detail="Handler person not found")

    item, error = crud.update_shift_checklist_manual_item(
        db, checklist_id, item_id, update.person_id,
        update.check_status, update.abnormal_remark, update.handler_id
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return _build_manual_item_detail(db, item)


# ========== Drill APIs ==========

def _can_create_drill(person: models.Person) -> bool:
    return person.role == models.RoleEnum.ADMIN


def _can_start_drill(person: models.Person) -> bool:
    return person.role in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]


def _can_cancel_drill(person: models.Person) -> bool:
    return person.role == models.RoleEnum.ADMIN


def _can_export_drill(person: models.Person) -> bool:
    return person.role == models.RoleEnum.ADMIN


@app.post("/drills", response_model=schemas.DrillDetail, tags=["Drills"])
def create_drill(drill: schemas.DrillCreate, db: Session = Depends(get_db)):
    person = crud.get_person(db, drill.created_by)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_create_drill(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin can create drills")

    zone = crud.get_zone(db, drill.zone_id)
    if not zone:
        raise HTTPException(status_code=400, detail="Zone not found")

    if drill.allowed_fluctuation <= 0:
        raise HTTPException(status_code=400, detail="Allowed fluctuation must be positive")

    if drill.duration_minutes <= 0:
        raise HTTPException(status_code=400, detail="Duration minutes must be positive")

    db_drill = drill_service.create_drill(db, drill)
    return drill_service.build_drill_detail(db, db_drill)


@app.get("/drills", response_model=List[schemas.DrillDetail], tags=["Drills"])
def list_drills(
    zone_id: Optional[int] = None,
    status: Optional[schemas.DrillStatusEnum] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    status_model = None
    if status:
        status_model = models.DrillStatus(status.value)
    drills = drill_service.list_drills(db, zone_id=zone_id, status=status_model, skip=skip, limit=limit)
    return [drill_service.build_drill_detail(db, d) for d in drills]


@app.get("/drills/export.csv", tags=["Drills"])
def export_drills_csv(
    zone_id: Optional[int] = None,
    status: Optional[schemas.DrillStatusEnum] = None,
    db: Session = Depends(get_db)
):
    status_model = None
    if status:
        status_model = models.DrillStatus(status.value)
    drills = drill_service.list_drills(db, zone_id=zone_id, status=status_model, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'zone_id', 'zone_name', 'name', 'target_temp', 'allowed_fluctuation',
        'duration_minutes', 'status', 'upper_limit', 'lower_limit',
        'created_by', 'creator_name', 'started_by', 'starter_name',
        'started_at', 'completed_at', 'cancelled_by', 'canceller_name',
        'cancelled_at', 'reading_count', 'judgment_count', 'alarm_change_count',
        'created_at', 'updated_at'
    ])

    for drill in drills:
        detail = drill_service.build_drill_detail(db, drill)
        status_val = detail['status'].value if hasattr(detail['status'], 'value') else str(detail['status'])
        writer.writerow([
            detail['id'],
            detail['zone_id'],
            detail['zone_name'] or '',
            detail['name'],
            detail['target_temp'],
            detail['allowed_fluctuation'],
            detail['duration_minutes'],
            status_val,
            detail['upper_limit'],
            detail['lower_limit'],
            detail['created_by'],
            detail['creator_name'] or '',
            detail['started_by'] or '',
            detail['starter_name'] or '',
            detail['started_at'].isoformat() if detail['started_at'] else '',
            detail['completed_at'].isoformat() if detail['completed_at'] else '',
            detail['cancelled_by'] or '',
            detail['canceller_name'] or '',
            detail['cancelled_at'].isoformat() if detail['cancelled_at'] else '',
            detail['reading_count'],
            detail['judgment_count'],
            detail['alarm_change_count'],
            detail['created_at'].isoformat() if detail['created_at'] else '',
            detail['updated_at'].isoformat() if detail['updated_at'] else ''
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=drills.csv"}
    )


@app.get("/drills/{drill_id}", response_model=schemas.DrillFullDetail, tags=["Drills"])
def get_drill(drill_id: int, db: Session = Depends(get_db)):
    drill = drill_service.get_drill(db, drill_id)
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")
    return drill_service.build_drill_full_detail(db, drill)


@app.post("/drills/{drill_id}/start", response_model=schemas.DrillFullDetail, tags=["Drills"])
def start_drill(drill_id: int, body: schemas.DrillStart, db: Session = Depends(get_db)):
    person = crud.get_person(db, body.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_start_drill(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin or operator can start drills")

    drill, error = drill_service.start_drill(db, drill_id, body.person_id)
    if error:
        drill_obj = drill_service.get_drill(db, drill_id)
        if not drill_obj:
            raise HTTPException(status_code=404, detail="Drill not found")
        if "Conflict" in error:
            raise HTTPException(status_code=409, detail=error)
        raise HTTPException(status_code=400, detail=error)
    return drill_service.build_drill_full_detail(db, drill)


@app.post("/drills/{drill_id}/cancel", response_model=schemas.DrillDetail, tags=["Drills"])
def cancel_drill(drill_id: int, body: schemas.DrillCancel, db: Session = Depends(get_db)):
    person = crud.get_person(db, body.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_cancel_drill(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin can cancel drills")

    drill, error = drill_service.cancel_drill(db, drill_id, body.person_id)
    if error:
        drill_obj = drill_service.get_drill(db, drill_id)
        if not drill_obj:
            raise HTTPException(status_code=404, detail="Drill not found")
        raise HTTPException(status_code=400, detail=error)
    return drill_service.build_drill_detail(db, drill)


@app.post("/drills/{drill_id}/complete", response_model=schemas.DrillDetail, tags=["Drills"])
def complete_drill(drill_id: int, body: schemas.DrillCancel, db: Session = Depends(get_db)):
    person = crud.get_person(db, body.person_id)
    if not person:
        raise HTTPException(status_code=400, detail="Person not found")
    if not _can_cancel_drill(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin can complete drills")

    drill, error = drill_service.complete_drill(db, drill_id, body.person_id)
    if error:
        drill_obj = drill_service.get_drill(db, drill_id)
        if not drill_obj:
            raise HTTPException(status_code=404, detail="Drill not found")
        raise HTTPException(status_code=400, detail=error)
    return drill_service.build_drill_detail(db, drill)


@app.post("/drills/{drill_id}/readings/import-json", tags=["Drills"])
async def import_drill_readings_json(
    drill_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    drill = drill_service.get_drill(db, drill_id)
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")

    if drill.status != models.DrillStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot import readings: drill is not in draft status")

    person = crud.get_person(db, drill.created_by)
    if not person or not _can_create_drill(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin can import drill readings")

    contents = await file.read()
    try:
        data = json.loads(contents)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="JSON must be a list of readings")

    readings = []
    for item in data:
        try:
            reading = schemas.DrillReadingCreate(**item)
            readings.append(reading)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid reading item: {str(e)}")

    successful, failed, errors = drill_service.import_drill_readings(db, drill_id, readings)
    return {"total": len(readings), "successful": successful, "failed": failed, "errors": errors}


@app.post("/drills/{drill_id}/readings/import-csv", tags=["Drills"])
async def import_drill_readings_csv(
    drill_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    drill = drill_service.get_drill(db, drill_id)
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")

    if drill.status != models.DrillStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot import readings: drill is not in draft status")

    person = crud.get_person(db, drill.created_by)
    if not person or not _can_create_drill(person):
        raise HTTPException(status_code=403, detail="Permission denied: only admin can import drill readings")

    contents = await file.read()
    content_str = contents.decode('utf-8')

    reader = csv.DictReader(io.StringIO(content_str))
    readings = []

    required_fields = {'sensor_code', 'temperature', 'reading_time'}
    if not required_fields.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns: {', '.join(required_fields)}"
        )

    for row in reader:
        try:
            reading = schemas.DrillReadingCreate(
                sensor_code=row['sensor_code'],
                temperature=float(row['temperature']),
                reading_time=datetime.fromisoformat(row['reading_time'])
            )
            readings.append(reading)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid row {row}: {str(e)}")

    successful, failed, errors = drill_service.import_drill_readings(db, drill_id, readings)
    return {"total": len(readings), "successful": successful, "failed": failed, "errors": errors}


@app.get("/drills/{drill_id}/export.json", tags=["Drills"])
def export_drill_json(drill_id: int, db: Session = Depends(get_db)):
    drill = drill_service.get_drill(db, drill_id)
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")

    export_data = drill_service.build_drill_export(db, drill)
    json_str = json.dumps(export_data, default=str, ensure_ascii=False, indent=2)

    return StreamingResponse(
        io.BytesIO(json_str.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=drill_{drill_id}_export.json"}
    )
