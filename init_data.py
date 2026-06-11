import sys
from datetime import datetime

sys.path.insert(0, '.')

from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    zones = [
        models.Zone(name="冷冻库区A", description="肉类冷冻存储区，设定温度-18℃"),
        models.Zone(name="冷冻库区B", description="海鲜冷冻存储区，设定温度-22℃"),
        models.Zone(name="冷藏库区C", description="蔬菜水果冷藏区，设定温度0-4℃"),
    ]
    for z in zones:
        existing = db.query(models.Zone).filter_by(name=z.name).first()
        if not existing:
            db.add(z)

    db.flush()

    persons = [
        models.Person(name="张管理", role=models.RoleEnum.ADMIN, phone="13800000001", email="zhang@example.com"),
        models.Person(name="李值班", role=models.RoleEnum.OPERATOR, phone="13800000002", email="li@example.com"),
        models.Person(name="王观察", role=models.RoleEnum.OBSERVER, phone="13800000003", email="wang@example.com"),
    ]
    for p in persons:
        existing = db.query(models.Person).filter_by(name=p.name).first()
        if not existing:
            db.add(p)

    db.flush()

    zone_a = db.query(models.Zone).filter_by(name="冷冻库区A").first()
    zone_b = db.query(models.Zone).filter_by(name="冷冻库区B").first()
    zone_c = db.query(models.Zone).filter_by(name="冷藏库区C").first()

    sensors = [
        models.Sensor(code="TEMP-001", name="A区入口传感器", zone_id=zone_a.id, is_active=True, offline_timeout_minutes=30),
        models.Sensor(code="TEMP-002", name="B区深冷传感器", zone_id=zone_b.id, is_active=True, offline_timeout_minutes=30),
        models.Sensor(code="TEMP-003", name="C区果蔬传感器", zone_id=zone_c.id, is_active=True, offline_timeout_minutes=30),
        models.Sensor(code="TEMP-004", name="A区备用传感器", zone_id=zone_a.id, is_active=False, offline_timeout_minutes=60),
    ]
    for s in sensors:
        existing = db.query(models.Sensor).filter_by(code=s.code).first()
        if not existing:
            db.add(s)

    db.flush()

    effective_time = datetime.fromisoformat("2026-06-01T00:00:00")

    sensor_001 = db.query(models.Sensor).filter_by(code="TEMP-001").first()
    sensor_002 = db.query(models.Sensor).filter_by(code="TEMP-002").first()
    sensor_003 = db.query(models.Sensor).filter_by(code="TEMP-003").first()

    thresholds = [
        models.ThresholdVersion(sensor_id=sensor_001.id, version=1, upper_limit=-15.0, lower_limit=-25.0,
                                dedup_window_minutes=60, effective_from=effective_time),
        models.ThresholdVersion(sensor_id=sensor_002.id, version=1, upper_limit=-20.0, lower_limit=-30.0,
                                dedup_window_minutes=60, effective_from=effective_time),
        models.ThresholdVersion(sensor_id=sensor_003.id, version=1, upper_limit=6.0, lower_limit=-2.0,
                                dedup_window_minutes=60, effective_from=effective_time),
    ]
    for t in thresholds:
        existing = db.query(models.ThresholdVersion).filter_by(
            sensor_id=t.sensor_id, version=t.version
        ).first()
        if not existing:
            db.add(t)

    db.commit()
    print("Sample data initialized successfully!")
    print(f"Zones: {db.query(models.Zone).count()}")
    print(f"Persons: {db.query(models.Person).count()}")
    print(f"Sensors: {db.query(models.Sensor).count()}")
    print(f"Threshold versions: {db.query(models.ThresholdVersion).count()}")

except Exception as e:
    db.rollback()
    print(f"Error initializing sample data: {e}")
    raise
finally:
    db.close()
