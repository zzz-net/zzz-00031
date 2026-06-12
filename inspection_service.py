from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
import json

import models
import schemas
import crud
import alarm_service


SHIFT_START_HOURS = {
    models.ShiftEnum.MORNING: 8,
    models.ShiftEnum.AFTERNOON: 16,
    models.ShiftEnum.NIGHT: 0,
}


def _get_shift_start_time(work_date: date, shift_type: models.ShiftEnum) -> datetime:
    hour = SHIFT_START_HOURS.get(shift_type, 8)
    return datetime.combine(work_date, datetime.min.time()) + timedelta(hours=hour)


def _is_overdue(deadline: datetime, status: models.InspectionWorkOrderStatus) -> bool:
    if status == models.InspectionWorkOrderStatus.COMPLETED:
        return False
    return datetime.now() > deadline


def create_template(
    db: Session,
    template_data: schemas.InspectionTemplateCreate
) -> Tuple[Optional[models.InspectionTemplate], Optional[str]]:
    person = crud.get_person(db, template_data.created_by)
    if not person:
        return None, "Person not found"
    if person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only admin can create inspection templates"

    zone = crud.get_zone(db, template_data.zone_id)
    if not zone:
        return None, "Zone not found"

    if template_data.deadline_hours <= 0:
        return None, "Deadline hours must be positive"

    db_template = models.InspectionTemplate(
        zone_id=template_data.zone_id,
        shift_type=template_data.shift_type,
        name=template_data.name,
        description=template_data.description,
        deadline_hours=template_data.deadline_hours,
        status=models.InspectionTemplateStatus.DRAFT,
        created_by=template_data.created_by,
    )
    db.add(db_template)
    db.flush()

    for idx, cp in enumerate(template_data.checkpoints):
        db_cp = models.InspectionCheckpoint(
            template_id=db_template.id,
            name=cp.name,
            description=cp.description,
            sort_order=cp.sort_order if cp.sort_order != 0 else idx + 1,
            require_photo=cp.require_photo,
            require_temperature=cp.require_temperature,
        )
        db.add(db_cp)

    db.commit()
    db.refresh(db_template)
    return db_template, None


def get_template(db: Session, template_id: int) -> Optional[models.InspectionTemplate]:
    return (
        db.query(models.InspectionTemplate)
        .filter(models.InspectionTemplate.id == template_id)
        .first()
    )


def list_templates(
    db: Session,
    zone_id: Optional[int] = None,
    status: Optional[models.InspectionTemplateStatus] = None,
    shift_type: Optional[models.ShiftEnum] = None,
    skip: int = 0,
    limit: int = 100
) -> List[models.InspectionTemplate]:
    query = db.query(models.InspectionTemplate)
    if zone_id:
        query = query.filter(models.InspectionTemplate.zone_id == zone_id)
    if status:
        query = query.filter(models.InspectionTemplate.status == status)
    if shift_type:
        query = query.filter(models.InspectionTemplate.shift_type == shift_type)
    return query.order_by(desc(models.InspectionTemplate.created_at)).offset(skip).limit(limit).all()


def update_template(
    db: Session,
    template_id: int,
    update_data: schemas.InspectionTemplateUpdate
) -> Tuple[Optional[models.InspectionTemplate], Optional[str]]:
    template = get_template(db, template_id)
    if not template:
        return None, "Template not found"

    if template.status in [models.InspectionTemplateStatus.ACTIVE, models.InspectionTemplateStatus.DISABLED]:
        return None, f"Cannot modify template in {template.status.value} status: historical fields are immutable after activation"

    data = update_data.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template, None


def activate_template(
    db: Session,
    template_id: int,
    person_id: int
) -> Tuple[Optional[models.InspectionTemplate], Optional[str]]:
    template = get_template(db, template_id)
    if not template:
        return None, "Template not found"

    person = crud.get_person(db, person_id)
    if not person:
        return None, "Person not found"
    if person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only admin can activate templates"

    if template.status not in [models.InspectionTemplateStatus.DRAFT, models.InspectionTemplateStatus.DISABLED]:
        return None, f"Cannot activate template in status: {template.status.value}"

    if not template.checkpoints or len(template.checkpoints) == 0:
        return None, "Cannot activate template with no checkpoints"

    template.status = models.InspectionTemplateStatus.ACTIVE
    template.activated_by = person_id
    template.activated_at = datetime.now()

    db.commit()
    db.refresh(template)
    return template, None


def disable_template(
    db: Session,
    template_id: int,
    person_id: int
) -> Tuple[Optional[models.InspectionTemplate], Optional[str]]:
    template = get_template(db, template_id)
    if not template:
        return None, "Template not found"

    person = crud.get_person(db, person_id)
    if not person:
        return None, "Person not found"
    if person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only admin can disable templates"

    if template.status != models.InspectionTemplateStatus.ACTIVE:
        return None, f"Cannot disable template in status: {template.status.value}"

    template.status = models.InspectionTemplateStatus.DISABLED
    template.disabled_by = person_id
    template.disabled_at = datetime.now()

    db.commit()
    db.refresh(template)
    return template, None


def add_checkpoint(
    db: Session,
    template_id: int,
    checkpoint_data: schemas.InspectionCheckpointCreate
) -> Tuple[Optional[models.InspectionCheckpoint], Optional[str]]:
    template = get_template(db, template_id)
    if not template:
        return None, "Template not found"

    if template.status in [models.InspectionTemplateStatus.ACTIVE, models.InspectionTemplateStatus.DISABLED]:
        return None, f"Cannot add checkpoints to template in {template.status.value} status: historical fields are immutable"

    existing_count = len(template.checkpoints) if template.checkpoints else 0
    db_cp = models.InspectionCheckpoint(
        template_id=template_id,
        name=checkpoint_data.name,
        description=checkpoint_data.description,
        sort_order=checkpoint_data.sort_order if checkpoint_data.sort_order != 0 else existing_count + 1,
        require_photo=checkpoint_data.require_photo,
        require_temperature=checkpoint_data.require_temperature,
    )
    db.add(db_cp)
    db.commit()
    db.refresh(db_cp)
    return db_cp, None


def update_checkpoint(
    db: Session,
    template_id: int,
    checkpoint_id: int,
    update_data: schemas.InspectionCheckpointUpdate
) -> Tuple[Optional[models.InspectionCheckpoint], Optional[str]]:
    template = get_template(db, template_id)
    if not template:
        return None, "Template not found"

    if template.status in [models.InspectionTemplateStatus.ACTIVE, models.InspectionTemplateStatus.DISABLED]:
        return None, f"Cannot modify checkpoints of template in {template.status.value} status: historical fields are immutable"

    checkpoint = (
        db.query(models.InspectionCheckpoint)
        .filter(
            models.InspectionCheckpoint.id == checkpoint_id,
            models.InspectionCheckpoint.template_id == template_id
        )
        .first()
    )
    if not checkpoint:
        return None, "Checkpoint not found in this template"

    data = update_data.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(checkpoint, key, value)

    db.commit()
    db.refresh(checkpoint)
    return checkpoint, None


def delete_checkpoint(
    db: Session,
    template_id: int,
    checkpoint_id: int
) -> Tuple[bool, Optional[str]]:
    template = get_template(db, template_id)
    if not template:
        return False, "Template not found"

    if template.status in [models.InspectionTemplateStatus.ACTIVE, models.InspectionTemplateStatus.DISABLED]:
        return False, f"Cannot delete checkpoints from template in {template.status.value} status: historical fields are immutable"

    checkpoint = (
        db.query(models.InspectionCheckpoint)
        .filter(
            models.InspectionCheckpoint.id == checkpoint_id,
            models.InspectionCheckpoint.template_id == template_id
        )
        .first()
    )
    if not checkpoint:
        return False, "Checkpoint not found in this template"

    db.delete(checkpoint)
    db.commit()
    return True, None


def check_work_order_conflict(
    db: Session,
    zone_id: int,
    work_date: date,
    shift_type: models.ShiftEnum,
    exclude_work_order_id: Optional[int] = None
) -> Optional[models.InspectionWorkOrder]:
    query = db.query(models.InspectionWorkOrder).filter(
        models.InspectionWorkOrder.zone_id == zone_id,
        models.InspectionWorkOrder.work_date == work_date,
        models.InspectionWorkOrder.shift_type == shift_type,
    )
    if exclude_work_order_id:
        query = query.filter(models.InspectionWorkOrder.id != exclude_work_order_id)
    return query.first()


def generate_work_order(
    db: Session,
    generate_data: schemas.InspectionWorkOrderGenerate
) -> Tuple[Optional[models.InspectionWorkOrder], Optional[str]]:
    person = crud.get_person(db, generate_data.created_by)
    if not person:
        return None, "Person not found"
    if person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only admin can generate work orders"

    template = get_template(db, generate_data.template_id)
    if not template:
        return None, "Template not found"
    if template.status != models.InspectionTemplateStatus.ACTIVE:
        return None, "Can only generate work orders from active templates"

    conflict = check_work_order_conflict(
        db, zone_id=template.zone_id,
        work_date=generate_data.work_date,
        shift_type=template.shift_type
    )
    if conflict:
        return None, (
            f"Conflict: work order for zone {template.zone_id}, "
            f"date {generate_data.work_date}, shift {template.shift_type.value} "
            f"already exists (id={conflict.id}, status={conflict.status.value})"
        )

    shift_start = _get_shift_start_time(generate_data.work_date, template.shift_type)
    deadline = shift_start + timedelta(hours=template.deadline_hours)

    db_order = models.InspectionWorkOrder(
        template_id=template.id,
        zone_id=template.zone_id,
        shift_type=template.shift_type,
        work_date=generate_data.work_date,
        deadline=deadline,
        status=models.InspectionWorkOrderStatus.PENDING,
        created_by=generate_data.created_by,
    )
    db.add(db_order)
    db.flush()

    checkpoints = sorted(template.checkpoints, key=lambda cp: cp.sort_order)
    for cp in checkpoints:
        item = models.InspectionWorkOrderItem(
            work_order_id=db_order.id,
            checkpoint_id=cp.id,
            checkpoint_name=cp.name,
            checkpoint_description=cp.description,
            sort_order=cp.sort_order,
            require_photo=cp.require_photo,
            require_temperature=cp.require_temperature,
            check_status=models.CheckItemStatus.PENDING,
        )
        db.add(item)

    _add_log(db, db_order.id, "generated", generate_data.created_by,
             json.dumps({"template_id": template.id, "template_name": template.name}, ensure_ascii=False))

    db.commit()
    db.refresh(db_order)
    return db_order, None


def get_work_order(db: Session, work_order_id: int) -> Optional[models.InspectionWorkOrder]:
    return (
        db.query(models.InspectionWorkOrder)
        .filter(models.InspectionWorkOrder.id == work_order_id)
        .first()
    )


def list_work_orders(
    db: Session,
    zone_id: Optional[int] = None,
    status: Optional[models.InspectionWorkOrderStatus] = None,
    claimed_by: Optional[int] = None,
    shift_type: Optional[models.ShiftEnum] = None,
    work_date_from: Optional[date] = None,
    work_date_to: Optional[date] = None,
    is_overdue: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100
) -> List[models.InspectionWorkOrder]:
    query = db.query(models.InspectionWorkOrder)
    if zone_id:
        query = query.filter(models.InspectionWorkOrder.zone_id == zone_id)
    if status:
        query = query.filter(models.InspectionWorkOrder.status == status)
    if claimed_by:
        query = query.filter(models.InspectionWorkOrder.claimed_by == claimed_by)
    if shift_type:
        query = query.filter(models.InspectionWorkOrder.shift_type == shift_type)
    if work_date_from:
        query = query.filter(models.InspectionWorkOrder.work_date >= work_date_from)
    if work_date_to:
        query = query.filter(models.InspectionWorkOrder.work_date <= work_date_to)

    orders = query.order_by(desc(models.InspectionWorkOrder.created_at)).offset(skip).limit(limit).all()

    if is_overdue is not None:
        orders = [o for o in orders if _is_overdue(o.deadline, o.status) == is_overdue]

    return orders


def claim_work_order(
    db: Session,
    work_order_id: int,
    person_id: int
) -> Tuple[Optional[models.InspectionWorkOrder], Optional[str]]:
    order = get_work_order(db, work_order_id)
    if not order:
        return None, "Work order not found"

    person = crud.get_person(db, person_id)
    if not person:
        return None, "Person not found"
    if person.role not in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]:
        return None, "Permission denied: only admin or operator can claim work orders"

    if order.status != models.InspectionWorkOrderStatus.PENDING:
        return None, f"Cannot claim work order in status: {order.status.value}"

    order.status = models.InspectionWorkOrderStatus.CLAIMED
    order.claimed_by = person_id
    order.claimed_at = datetime.now()

    _add_log(db, order.id, "claimed", person_id,
             json.dumps({"previous_status": models.InspectionWorkOrderStatus.PENDING.value}, ensure_ascii=False))

    db.commit()
    db.refresh(order)
    return order, None


def update_work_order_item(
    db: Session,
    work_order_id: int,
    item_id: int,
    update_data: schemas.InspectionWorkOrderItemUpdate
) -> Tuple[Optional[models.InspectionWorkOrderItem], Optional[str]]:
    order = get_work_order(db, work_order_id)
    if not order:
        return None, "Work order not found"

    person = crud.get_person(db, update_data.person_id)
    if not person:
        return None, "Person not found"
    if person.role not in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]:
        return None, "Permission denied: only admin or operator can update work order items"

    if order.status == models.InspectionWorkOrderStatus.COMPLETED:
        return None, "Cannot modify completed work order"

    if order.claimed_by and order.claimed_by != update_data.person_id and person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only the claimed operator or admin can update items"

    item = (
        db.query(models.InspectionWorkOrderItem)
        .filter(
            models.InspectionWorkOrderItem.id == item_id,
            models.InspectionWorkOrderItem.work_order_id == work_order_id
        )
        .first()
    )
    if not item:
        return None, "Item not found in this work order"

    if update_data.handler_id is not None:
        handler = crud.get_person(db, update_data.handler_id)
        if not handler:
            return None, "Handler person not found"

    item.check_status = update_data.check_status
    item.checked_by = update_data.person_id
    item.checked_at = datetime.now()

    if update_data.temperature_value is not None:
        item.temperature_value = update_data.temperature_value
    if update_data.photo_urls is not None:
        item.photo_urls = json.dumps(update_data.photo_urls, ensure_ascii=False) if update_data.photo_urls else None
    if update_data.remark is not None:
        item.remark = update_data.remark
    if update_data.exception_action is not None:
        item.exception_action = update_data.exception_action
    if update_data.handler_id is not None:
        item.handler_id = update_data.handler_id

    db.commit()
    db.refresh(item)
    return item, None


def complete_work_order(
    db: Session,
    work_order_id: int,
    complete_data: schemas.InspectionWorkOrderComplete
) -> Tuple[Optional[models.InspectionWorkOrder], Optional[str]]:
    order = get_work_order(db, work_order_id)
    if not order:
        return None, "Work order not found"

    person = crud.get_person(db, complete_data.person_id)
    if not person:
        return None, "Person not found"
    if person.role not in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]:
        return None, "Permission denied: only admin or operator can complete work orders"

    if order.status != models.InspectionWorkOrderStatus.CLAIMED:
        return None, f"Cannot complete work order in status: {order.status.value}"

    if order.claimed_by and order.claimed_by != complete_data.person_id and person.role != models.RoleEnum.ADMIN:
        return None, "Permission denied: only the claimed operator or admin can complete"

    all_items = order.items or []
    pending_items = [i for i in all_items if i.check_status == models.CheckItemStatus.PENDING]
    if pending_items:
        return None, f"Cannot complete: {len(pending_items)} items are still pending"

    order.status = models.InspectionWorkOrderStatus.COMPLETED
    order.completed_by = complete_data.person_id
    order.completed_at = datetime.now()
    if complete_data.general_remark is not None:
        order.general_remark = complete_data.general_remark

    _add_log(db, order.id, "completed", complete_data.person_id,
             json.dumps({
                 "previous_status": models.InspectionWorkOrderStatus.CLAIMED.value,
                 "general_remark": complete_data.general_remark
             }, ensure_ascii=False))

    db.commit()
    db.refresh(order)
    return order, None


def associate_alarm(
    db: Session,
    work_order_id: int,
    associate_data: schemas.InspectionAlarmAssociate
) -> Tuple[Optional[models.InspectionWorkOrderAlarm], Optional[str]]:
    order = get_work_order(db, work_order_id)
    if not order:
        return None, "Work order not found"

    person = crud.get_person(db, associate_data.associated_by)
    if not person:
        return None, "Person not found"
    if person.role not in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]:
        return None, "Permission denied: only admin or operator can associate alarms"

    alarm = db.query(models.Alarm).filter(models.Alarm.id == associate_data.alarm_id).first()
    if not alarm:
        return None, "Alarm not found"

    existing = (
        db.query(models.InspectionWorkOrderAlarm)
        .filter(
            models.InspectionWorkOrderAlarm.work_order_id == work_order_id,
            models.InspectionWorkOrderAlarm.alarm_id == associate_data.alarm_id
        )
        .first()
    )
    if existing:
        return None, "Alarm already associated with this work order"

    alarm_detail = alarm_service.get_alarm_detail(db, associate_data.alarm_id)
    alarm_snapshot = json.dumps(alarm_detail, default=str, ensure_ascii=False) if alarm_detail else None

    association = models.InspectionWorkOrderAlarm(
        work_order_id=work_order_id,
        alarm_id=associate_data.alarm_id,
        alarm_snapshot=alarm_snapshot,
        associated_by=associate_data.associated_by,
    )
    db.add(association)
    db.flush()

    _add_log(db, work_order_id, "alarm_associated", associate_data.associated_by,
             json.dumps({"alarm_id": associate_data.alarm_id}, ensure_ascii=False))

    db.commit()
    db.refresh(association)
    return association, None


def disassociate_alarm(
    db: Session,
    work_order_id: int,
    alarm_id: int,
    person_id: int
) -> Tuple[bool, Optional[str]]:
    order = get_work_order(db, work_order_id)
    if not order:
        return False, "Work order not found"

    person = crud.get_person(db, person_id)
    if not person:
        return False, "Person not found"
    if person.role not in [models.RoleEnum.ADMIN, models.RoleEnum.OPERATOR]:
        return False, "Permission denied: only admin or operator can disassociate alarms"

    association = (
        db.query(models.InspectionWorkOrderAlarm)
        .filter(
            models.InspectionWorkOrderAlarm.work_order_id == work_order_id,
            models.InspectionWorkOrderAlarm.alarm_id == alarm_id
        )
        .first()
    )
    if not association:
        return False, "Association not found"

    db.delete(association)
    db.flush()

    _add_log(db, work_order_id, "alarm_disassociated", person_id,
             json.dumps({"alarm_id": alarm_id}, ensure_ascii=False))

    db.commit()
    return True, None


def _add_log(db: Session, work_order_id: int, action: str, operator_id: int, detail: Optional[str] = None):
    log = models.InspectionWorkOrderLog(
        work_order_id=work_order_id,
        action=action,
        operator_id=operator_id,
        detail=detail,
    )
    db.add(log)


def build_template_detail(db: Session, template: models.InspectionTemplate) -> dict:
    zone = template.zone
    creator = template.creator
    activator = template.activator
    disabler = template.disabler
    checkpoint_count = len(template.checkpoints) if template.checkpoints else 0
    work_order_count = len(template.work_orders) if template.work_orders else 0

    checkpoints = []
    for cp in (template.checkpoints or []):
        checkpoints.append({
            "id": cp.id,
            "template_id": cp.template_id,
            "name": cp.name,
            "description": cp.description,
            "sort_order": cp.sort_order,
            "require_photo": cp.require_photo,
            "require_temperature": cp.require_temperature,
            "created_at": cp.created_at,
            "updated_at": cp.updated_at,
        })

    return {
        "id": template.id,
        "zone_id": template.zone_id,
        "zone_name": zone.name if zone else None,
        "shift_type": template.shift_type,
        "name": template.name,
        "description": template.description,
        "deadline_hours": template.deadline_hours,
        "status": template.status,
        "created_by": template.created_by,
        "creator_name": creator.name if creator else None,
        "creator_role": creator.role if creator else None,
        "activated_by": template.activated_by,
        "activator_name": activator.name if activator else None,
        "activated_at": template.activated_at,
        "disabled_by": template.disabled_by,
        "disabler_name": disabler.name if disabler else None,
        "disabled_at": template.disabled_at,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "checkpoints": checkpoints,
        "checkpoint_count": checkpoint_count,
        "work_order_count": work_order_count,
    }


def build_template_list_item(db: Session, template: models.InspectionTemplate) -> dict:
    zone = template.zone
    creator = template.creator
    activator = template.activator
    disabler = template.disabler
    checkpoint_count = len(template.checkpoints) if template.checkpoints else 0
    work_order_count = len(template.work_orders) if template.work_orders else 0

    return {
        "id": template.id,
        "zone_id": template.zone_id,
        "zone_name": zone.name if zone else None,
        "shift_type": template.shift_type,
        "name": template.name,
        "description": template.description,
        "deadline_hours": template.deadline_hours,
        "status": template.status,
        "created_by": template.created_by,
        "creator_name": creator.name if creator else None,
        "creator_role": creator.role if creator else None,
        "activated_by": template.activated_by,
        "activator_name": activator.name if activator else None,
        "activated_at": template.activated_at,
        "disabled_by": template.disabled_by,
        "disabler_name": disabler.name if disabler else None,
        "disabled_at": template.disabled_at,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "checkpoint_count": checkpoint_count,
        "work_order_count": work_order_count,
    }


def build_work_order_list_item(db: Session, order: models.InspectionWorkOrder) -> dict:
    zone = order.zone
    claimer = order.claimer
    completer = order.completer
    creator = order.creator

    items = order.items or []
    item_count = len(items)
    pending_count = sum(1 for i in items if i.check_status == models.CheckItemStatus.PENDING)
    abnormal_count = sum(1 for i in items if i.check_status == models.CheckItemStatus.ABNORMAL)
    alarm_count = len(order.alarm_associations) if order.alarm_associations else 0

    return {
        "id": order.id,
        "template_id": order.template_id,
        "zone_id": order.zone_id,
        "zone_name": zone.name if zone else None,
        "shift_type": order.shift_type,
        "work_date": order.work_date,
        "deadline": order.deadline,
        "status": order.status,
        "is_overdue": _is_overdue(order.deadline, order.status),
        "claimed_by": order.claimed_by,
        "claimer_name": claimer.name if claimer else None,
        "claimed_at": order.claimed_at,
        "completed_by": order.completed_by,
        "completer_name": completer.name if completer else None,
        "completed_at": order.completed_at,
        "general_remark": order.general_remark,
        "created_by": order.created_by,
        "creator_name": creator.name if creator else None,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "item_count": item_count,
        "pending_count": pending_count,
        "abnormal_count": abnormal_count,
        "alarm_count": alarm_count,
    }


def build_work_order_detail(db: Session, order: models.InspectionWorkOrder) -> dict:
    base = build_work_order_list_item(db, order)

    items = []
    for item in (order.items or []):
        checker = item.checker
        handler = item.handler
        try:
            photo_urls_parsed = json.loads(item.photo_urls) if item.photo_urls else []
        except (json.JSONDecodeError, TypeError):
            photo_urls_parsed = item.photo_urls if item.photo_urls else []
        items.append({
            "id": item.id,
            "work_order_id": item.work_order_id,
            "checkpoint_id": item.checkpoint_id,
            "checkpoint_name": item.checkpoint_name,
            "checkpoint_description": item.checkpoint_description,
            "sort_order": item.sort_order,
            "require_photo": item.require_photo,
            "require_temperature": item.require_temperature,
            "temperature_value": item.temperature_value,
            "photo_urls": photo_urls_parsed,
            "check_status": item.check_status,
            "checked_by": item.checked_by,
            "checked_by_name": checker.name if checker else None,
            "checked_at": item.checked_at,
            "remark": item.remark,
            "exception_action": item.exception_action,
            "handler_id": item.handler_id,
            "handler_name": handler.name if handler else None,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        })

    alarm_associations = []
    for assoc in (order.alarm_associations or []):
        associator = assoc.associator
        try:
            snapshot = json.loads(assoc.alarm_snapshot) if assoc.alarm_snapshot else None
        except (json.JSONDecodeError, TypeError):
            snapshot = assoc.alarm_snapshot
        alarm_associations.append({
            "id": assoc.id,
            "work_order_id": assoc.work_order_id,
            "alarm_id": assoc.alarm_id,
            "alarm_snapshot": snapshot,
            "associated_by": assoc.associated_by,
            "associator_name": associator.name if associator else None,
            "created_at": assoc.created_at,
        })

    operation_logs = []
    for log in (order.operation_logs or []):
        operator = log.operator
        operation_logs.append({
            "id": log.id,
            "work_order_id": log.work_order_id,
            "action": log.action,
            "operator_id": log.operator_id,
            "operator_name": operator.name if operator else None,
            "operator_role": operator.role if operator else None,
            "detail": log.detail,
            "created_at": log.created_at,
        })

    base["items"] = sorted(items, key=lambda x: x["sort_order"])
    base["associated_alarms"] = alarm_associations
    base["logs"] = operation_logs
    return base


def build_work_order_export(db: Session, order: models.InspectionWorkOrder) -> dict:
    detail = build_work_order_detail(db, order)

    alarm_details = []
    for assoc in (order.alarm_associations or []):
        try:
            snapshot = json.loads(assoc.alarm_snapshot) if assoc.alarm_snapshot else None
        except (json.JSONDecodeError, TypeError):
            snapshot = assoc.alarm_snapshot
        alarm_details.append({
            "association_id": assoc.id,
            "alarm_id": assoc.alarm_id,
            "alarm_snapshot": snapshot,
            "associated_by": assoc.associated_by,
            "associator_name": assoc.associator.name if assoc.associator else None,
            "created_at": assoc.created_at,
        })

    detail["alarm_associations"] = alarm_details
    return detail
