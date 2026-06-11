from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
import io
import csv
import json

from database import engine, get_db, Base
import models
import schemas
import crud
import alarm_service

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
        'status', 'trigger_value', 'trigger_time', 'latest_value',
        'latest_time', 'resolution_note', 'created_at', 'updated_at'
    ])

    for a in alarms:
        alarm_type_val = a['alarm_type'].value if hasattr(a['alarm_type'], 'value') else str(a['alarm_type'])
        status_val = a['status'].value if hasattr(a['status'], 'value') else str(a['status'])
        writer.writerow([
            a['id'], a['sensor_code'], a['sensor_name'], a['zone_name'],
            alarm_type_val,
            status_val,
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


@app.post("/alarms/{alarm_id}/suppress", tags=["Alarms"])
def suppress_alarm(alarm_id: int, update: schemas.AlarmSuppressUpdate, db: Session = Depends(get_db)):
    alarm, error = alarm_service.transition_alarm_status(
        db, alarm_id, update.person_id, schemas.AlarmStatusEnum.SUPPRESSED, update.note
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
