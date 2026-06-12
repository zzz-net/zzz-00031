"""
冷库巡检工单全面测试
覆盖：
1. 权限验证（admin 可管理模板，operator 可操作工单，observer 只能查看）
2. 模板状态流转（草稿 -> 启用 -> 停用，启用后不可修改）
3. 重复工单生成冲突（同一库区同一班次同一日期不能重复生成）
4. 工单生命周期（待领取 -> 已领取 -> 已完成）
5. 巡检项目填写（温度、照片、备注、异常处理）
6. 逾期状态自动计算（deadline 已过且未完成时 is_overdue=true）
7. 报警关联（关联报警时保存快照，解除关联）
8. 工单日志记录
9. 列表筛选（库区、状态、负责人、班次、日期范围、逾期）
10. CSV/JSON 导出一致性（导出数据与列表 API 一致）
11. 详情导出一致性（详情导出与详情 API 一致）
12. 跨服务重启数据持久化验证
"""
import json
import urllib.request
import urllib.error
import io
import csv
from datetime import date, timedelta

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0


def http_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode(), resp.status


def http_get_json(path):
    body, status = http_get(path)
    return json.loads(body), status


def http_post(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            try:
                return json.loads(body), resp.status
            except json.JSONDecodeError:
                return {"detail": body}, resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body), e.code
        except json.JSONDecodeError:
            return {"detail": body}, e.code


def http_put(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            try:
                return json.loads(body), resp.status
            except json.JSONDecodeError:
                return {"detail": body}, resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body), e.code
        except json.JSONDecodeError:
            return {"detail": body}, e.code


def http_delete(path):
    req = urllib.request.Request(
        f"{BASE}{path}",
        method="DELETE"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            try:
                return json.loads(body), resp.status
            except json.JSONDecodeError:
                return {"detail": body}, resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body), e.code
        except json.JSONDecodeError:
            return {"detail": body}, e.code


def assert_eq(actual, expected, msg):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  [PASS] {msg}: {actual}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}: 期望 {expected}, 实际 {actual}")


def assert_true(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")


def assert_contains(text, keyword, msg):
    global PASS, FAIL
    if keyword in str(text):
        PASS += 1
        print(f"  [PASS] {msg} (包含 '{keyword}')")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg} (未找到 '{keyword}')")


# ========== 初始化 ==========
print("=" * 70)
print("冷库巡检工单全面测试")
print("=" * 70)

print("\n--- 初始化：获取基础数据 ---")
persons, _ = http_get_json("/persons")
zones, _ = http_get_json("/zones")
alarms, _ = http_get_json("/alarms")

p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]

z_a = [z for z in zones if "A" in z["name"]][0]
z_b = [z for z in zones if "B" in z["name"]][0]

test_alarm = alarms[0] if alarms else None

print(f"  admin={p_admin['id']} ({p_admin['name']})")
print(f"  operator={p_op['id']} ({p_op['name']})")
print(f"  observer={p_obs['id']} ({p_obs['name']})")
print(f"  库区A={z_a['id']}, 库区B={z_b['id']}")
print(f"  测试用报警ID: {test_alarm['id'] if test_alarm else 'N/A'}")

import time
UNIQUE_OFFSET = int(time.time() * 1000) % 100000 + 2000
WORK_DATE = date.today().isoformat()
WORK_DATE_FUTURE = (date.today() + timedelta(days=UNIQUE_OFFSET)).isoformat()
WORK_DATE_FAR_FUTURE = (date.today() + timedelta(days=UNIQUE_OFFSET + 500)).isoformat()

# ========== TEST 1: 模板权限验证 ==========
print()
print("=" * 70)
print("TEST 1: 模板权限验证")
print("=" * 70)

print("\n--- 1.1 admin 可以创建草稿模板 ---")
r, s = http_post("/inspection-templates", {
    "name": "A区早班巡检模板",
    "zone_id": z_a["id"],
    "shift_type": "morning",
    "deadline_hours": 8.0,
    "created_by": p_admin["id"],
    "checkpoints": [
        {"name": "入口温度检测", "description": "检查入口处温度", "sort_order": 1, "require_temperature": True, "require_photo": False},
        {"name": "货架温度检测", "description": "检查货架区域温度", "sort_order": 2, "require_temperature": True, "require_photo": True},
        {"name": "库门密封检查", "description": "检查库门密封性", "sort_order": 3, "require_temperature": False, "require_photo": True}
    ]
})
assert_eq(s, 200, "admin 创建模板成功")
assert_eq(r["status"], "draft", "初始状态为 draft")
assert_eq(len(r["checkpoints"]), 3, "包含 3 个巡检点")
template_a_morning_id = r["id"]
print(f"  模板 ID: {template_a_morning_id}")

print("\n--- 1.2 observer 不能创建模板 (403) ---")
r, s = http_post("/inspection-templates", {
    "name": "B区早班模板",
    "zone_id": z_b["id"],
    "shift_type": "morning",
    "deadline_hours": 8.0,
    "created_by": p_obs["id"],
    "checkpoints": [{"name": "测试", "sort_order": 1}]
})
assert_eq(s, 403, "observer 创建模板返回 403")

print("\n--- 1.3 operator 不能创建模板 (403) ---")
r, s = http_post("/inspection-templates", {
    "name": "B区早班模板",
    "zone_id": z_b["id"],
    "shift_type": "morning",
    "deadline_hours": 8.0,
    "created_by": p_op["id"],
    "checkpoints": [{"name": "测试", "sort_order": 1}]
})
assert_eq(s, 403, "operator 创建模板返回 403")

print("\n--- 1.4 observer 可以查看模板列表和详情 ---")
r_list, s_list = http_get_json("/inspection-templates")
assert_eq(s_list, 200, "observer 查看列表成功 (200)")
assert_true(len(r_list) >= 1, "列表至少有 1 个模板")

r_detail, s_detail = http_get_json(f"/inspection-templates/{template_a_morning_id}")
assert_eq(s_detail, 200, "查看详情成功 (200)")
assert_eq(r_detail["id"], template_a_morning_id, "详情 ID 正确")

print("\n--- 1.5 observer 不能启用模板 (403) ---")
r, s = http_post(f"/inspection-templates/{template_a_morning_id}/activate", {
    "person_id": p_obs["id"]
})
assert_eq(s, 403, "observer 启用模板返回 403")

print("\n--- 1.6 observer 不能停用模板 (403) ---")
r, s = http_post(f"/inspection-templates/{template_a_morning_id}/disable", {
    "person_id": p_obs["id"]
})
assert_eq(s, 403, "observer 停用模板返回 403")

# ========== TEST 2: 模板状态流转与不可变性 ==========
print()
print("=" * 70)
print("TEST 2: 模板状态流转与不可变性")
print("=" * 70)

print("\n--- 2.1 admin 启用模板 ---")
r, s = http_post(f"/inspection-templates/{template_a_morning_id}/activate", {
    "person_id": p_admin["id"]
})
assert_eq(s, 200, "admin 启用模板成功")
assert_eq(r["status"], "active", "状态变为 active")

print("\n--- 2.2 启用后不能修改模板基本信息 ---")
r, s = http_put(f"/inspection-templates/{template_a_morning_id}", {
    "name": "已修改的名称"
})
assert_eq(s, 400, "修改启用模板返回 400")

print("\n--- 2.3 启用后不能添加巡检点 ---")
r, s = http_post(f"/inspection-templates/{template_a_morning_id}/checkpoints", {
    "name": "新增巡检点", "sort_order": 4
})
assert_eq(s, 400, "启用后添加巡检点返回 400")

print("\n--- 2.4 启用后不能修改巡检点 ---")
cps = r_detail["checkpoints"]
if cps:
    cp = cps[0]
    r, s = http_put(f"/inspection-templates/{template_a_morning_id}/checkpoints/{cp['id']}", {
        "name": "已修改的巡检点"
    })
    assert_eq(s, 400, "启用后修改巡检点返回 400")

print("\n--- 2.5 启用后不能删除巡检点 ---")
if cps:
    cp = cps[0]
    r, s = http_delete(f"/inspection-templates/{template_a_morning_id}/checkpoints/{cp['id']}")
    assert_eq(s, 400, "启用后删除巡检点返回 400")

print("\n--- 2.6 admin 停用模板 ---")
r, s = http_post(f"/inspection-templates/{template_a_morning_id}/disable", {
    "person_id": p_admin["id"]
})
assert_eq(s, 200, "admin 停用模板成功")
assert_eq(r["status"], "disabled", "状态变为 disabled")

print("\n--- 2.7 停用后也不能修改（保持历史完整性） ---")
r, s = http_put(f"/inspection-templates/{template_a_morning_id}", {
    "name": "已修改的名称"
})
assert_eq(s, 400, "修改停用模板返回 400")

# 重新启用以便后续测试使用
r, s = http_post(f"/inspection-templates/{template_a_morning_id}/activate", {
    "person_id": p_admin["id"]
})
assert_eq(s, 200, "重新启用模板成功")

# 创建B区早班模板（用于重复生成测试）
print("\n--- 2.8 创建 B 区晚班模板并启用 ---")
r, s = http_post("/inspection-templates", {
    "name": "B区晚班巡检模板",
    "zone_id": z_b["id"],
    "shift_type": "night",
    "deadline_hours": 6.0,
    "created_by": p_admin["id"],
    "checkpoints": [
        {"name": "入口温度", "description": "入口检测", "sort_order": 1, "require_temperature": True, "require_photo": False},
        {"name": "设备状态", "description": "设备检查", "sort_order": 2, "require_temperature": False, "require_photo": True}
    ]
})
template_b_night_id = r["id"]
r2, s2 = http_post(f"/inspection-templates/{template_b_night_id}/activate", {
    "person_id": p_admin["id"]
})
assert_eq(s2, 200, "B区晚班模板启用成功")

# 创建一个短截止时间模板用于逾期测试
print("\n--- 2.9 创建短截止时间模板（用于逾期测试） ---")
r, s = http_post("/inspection-templates", {
    "name": "A区短时测试模板",
    "zone_id": z_a["id"],
    "shift_type": "afternoon",
    "deadline_hours": 0.001,
    "created_by": p_admin["id"],
    "checkpoints": [
        {"name": "快速检测点", "sort_order": 1, "require_temperature": False, "require_photo": False}
    ]
})
template_short_deadline_id = r["id"]
r2, s2 = http_post(f"/inspection-templates/{template_short_deadline_id}/activate", {
    "person_id": p_admin["id"]
})
assert_eq(s2, 200, "短时模板启用成功")

# ========== TEST 3: 工单生成与重复冲突 ==========
print()
print("=" * 70)
print("TEST 3: 工单生成与重复冲突检测")
print("=" * 70)

print("\n--- 3.1 admin 可以生成工单 ---")
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": template_a_morning_id,
    "work_date": WORK_DATE_FUTURE,
    "created_by": p_admin["id"]
})
assert_eq(s, 200, "admin 生成工单成功")
assert_eq(r["status"], "pending", "初始状态为 pending")
assert_eq(r["work_date"], WORK_DATE_FUTURE, "工作日期正确")
assert_eq(r["shift_type"], "morning", "班次类型正确")
assert_eq(len(r["items"]), 3, "工单包含 3 个巡检项")
wo_a_morning_id = r["id"]
print(f"  工单 ID: {wo_a_morning_id}")

print("\n--- 3.2 同一模板同一日期同一班次不能重复生成 (409) ---")
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": template_a_morning_id,
    "work_date": WORK_DATE_FUTURE,
    "created_by": p_admin["id"]
})
assert_eq(s, 409, "重复生成返回 409")
assert_contains(r.get("detail", ""), "Conflict", "错误信息包含 Conflict")

print("\n--- 3.3 operator 不能生成工单 (403) ---")
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": template_b_night_id,
    "work_date": WORK_DATE_FUTURE,
    "created_by": p_op["id"]
})
assert_eq(s, 403, "operator 生成工单返回 403")

print("\n--- 3.4 observer 不能生成工单 (403) ---")
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": template_b_night_id,
    "work_date": WORK_DATE_FUTURE,
    "created_by": p_obs["id"]
})
assert_eq(s, 403, "observer 生成工单返回 403")

print("\n--- 3.5 不同库区同一班次可以生成 ---")
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": template_b_night_id,
    "work_date": WORK_DATE_FAR_FUTURE,
    "created_by": p_admin["id"]
})
assert_eq(s, 200, "不同库区生成成功")
wo_b_night_id = r["id"]

print("\n--- 3.6 生成短时截止时间工单（用于逾期测试） ---")
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": template_short_deadline_id,
    "work_date": WORK_DATE,
    "created_by": p_admin["id"]
})
wo_short_deadline_id = None
if s == 409:
    r_list, _ = http_get_json(f"/inspection-work-orders?zone_id={z_a['id']}&work_date_from={WORK_DATE}&work_date_to={WORK_DATE}&shift_type=afternoon")
    if r_list:
        wo_short_deadline_id = r_list[0]["id"]
        print(f"  短时工单已存在，使用现有 ID: {wo_short_deadline_id}")
    else:
        assert_eq(s, 200, "短时工单生成成功")
else:
    assert_eq(s, 200, "短时工单生成成功")
    wo_short_deadline_id = r["id"]
    print(f"  短时工单 ID: {wo_short_deadline_id}, deadline: {r['deadline']}")

# ========== TEST 4: 工单生命周期（领取、填写、完成） ==========
print()
print("=" * 70)
print("TEST 4: 工单生命周期")
print("=" * 70)

print("\n--- 4.1 operator 可以领取工单 ---")
r, s = http_post(f"/inspection-work-orders/{wo_a_morning_id}/claim", {
    "person_id": p_op["id"]
})
assert_eq(s, 200, "operator 领取工单成功")
assert_eq(r["status"], "claimed", "状态变为 claimed")
assert_eq(r["claimed_by"], p_op["id"], "claimed_by 正确")
assert_eq(r["claimer_name"], p_op["name"], "claimer_name 正确")
assert_true(r["claimed_at"] is not None, "claimed_at 已设置")

print("\n--- 4.2 observer 不能领取工单 (403) ---")
r, s = http_post(f"/inspection-work-orders/{wo_b_night_id}/claim", {
    "person_id": p_obs["id"]
})
assert_eq(s, 403, "observer 领取工单返回 403")

print("\n--- 4.3 已领取的工单不能再次领取 ---")
r, s = http_post(f"/inspection-work-orders/{wo_a_morning_id}/claim", {
    "person_id": p_admin["id"]
})
assert_eq(s, 400, "重复领取返回 400")

print("\n--- 4.4 填写巡检项（温度、照片、备注、异常处理） ---")
detail, _ = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
items = detail["items"]
assert_true(len(items) >= 3, "至少有 3 个巡检项")

# 第一项：正常（带温度）
item1 = items[0]
r, s = http_put(
    f"/inspection-work-orders/{wo_a_morning_id}/items/{item1['id']}",
    {
        "person_id": p_op["id"],
        "check_status": "normal",
        "temperature_value": -18.5,
        "remark": "温度正常"
    }
)
assert_eq(s, 200, "更新巡检项1成功")
assert_eq(r["check_status"], "normal", "状态变为 normal")
assert_eq(r["temperature_value"], -18.5, "温度值正确")
assert_eq(r["checked_by"], p_op["id"], "checked_by 正确")
assert_true(r["checked_at"] is not None, "checked_at 已设置")

# 第二项：异常（带照片和异常处理）
item2 = items[1]
r, s = http_put(
    f"/inspection-work-orders/{wo_a_morning_id}/items/{item2['id']}",
    {
        "person_id": p_op["id"],
        "check_status": "abnormal",
        "temperature_value": -12.0,
        "photo_urls": ["http://example.com/photo1.jpg", "http://example.com/photo2.jpg"],
        "remark": "温度偏高，发现异常",
        "exception_action": "已通知维修人员处理",
        "handler_id": p_admin["id"]
    }
)
assert_eq(s, 200, "更新巡检项2成功")
assert_eq(r["check_status"], "abnormal", "状态变为 abnormal")
assert_eq(len(r["photo_urls"]), 2, "照片URL数量正确")
assert_eq(r["exception_action"], "已通知维修人员处理", "异常处理动作正确")
assert_eq(r["handler_id"], p_admin["id"], "处理人ID正确")
assert_eq(r["handler_name"], p_admin["name"], "处理人名称正确")

# 第三项：正常（带照片）
item3 = items[2]
r, s = http_put(
    f"/inspection-work-orders/{wo_a_morning_id}/items/{item3['id']}",
    {
        "person_id": p_op["id"],
        "check_status": "normal",
        "photo_urls": ["http://example.com/door.jpg"],
        "remark": "密封良好"
    }
)
assert_eq(s, 200, "更新巡检项3成功")

print("\n--- 4.5 未全部检查不能完成工单 ---")
# 先把其中一项恢复为 pending 状态来测试
# 实际上所有项都已检查，我们用另一个未完成的工单来测
r, s = http_post(f"/inspection-work-orders/{wo_b_night_id}/claim", {
    "person_id": p_op["id"]
})
assert_eq(s, 200, "领取B区工单成功")

r, s = http_post(f"/inspection-work-orders/{wo_b_night_id}/complete", {
    "person_id": p_op["id"],
    "general_remark": "测试未全部检查"
})
assert_eq(s, 400, "未全部检查完成返回 400")
assert_contains(r.get("detail", ""), "pending", "错误信息提示需全部检查")

print("\n--- 4.6 全部检查后可以完成工单 ---")
detail_b, _ = http_get_json(f"/inspection-work-orders/{wo_b_night_id}")
items_b = detail_b["items"]
for i, item in enumerate(items_b):
    http_put(
        f"/inspection-work-orders/{wo_b_night_id}/items/{item['id']}",
        {"person_id": p_op["id"], "check_status": "normal", "remark": f"检查项{i+1}正常"}
    )

r, s = http_post(f"/inspection-work-orders/{wo_b_night_id}/complete", {
    "person_id": p_op["id"],
    "general_remark": "B区晚班巡检完成，一切正常"
})
assert_eq(s, 200, "完成工单成功")
assert_eq(r["status"], "completed", "状态变为 completed")
assert_eq(r["completed_by"], p_op["id"], "completed_by 正确")
assert_eq(r["completer_name"], p_op["name"], "completer_name 正确")
assert_true(r["completed_at"] is not None, "completed_at 已设置")
assert_eq(r["general_remark"], "B区晚班巡检完成，一切正常", "总备注正确")

print("\n--- 4.7 observer 不能完成工单 (403) ---")
r, s = http_post(f"/inspection-work-orders/{wo_a_morning_id}/complete", {
    "person_id": p_obs["id"],
    "general_remark": "测试"
})
assert_eq(s, 403, "observer 完成工单返回 403")

# ========== TEST 5: 逾期状态自动计算 ==========
print()
print("=" * 70)
print("TEST 5: 逾期状态自动计算")
print("=" * 70)

print("\n--- 5.1 短时截止时间工单应为逾期状态 ---")
import time
time.sleep(1)  # 等待一小段时间确保超过截止时间
detail_short, s = http_get_json(f"/inspection-work-orders/{wo_short_deadline_id}")
assert_eq(s, 200, "获取短时工单成功")
assert_true(detail_short.get("is_overdue") is True, "短时工单 is_overdue=true")
print(f"  deadline: {detail_short['deadline']}")
print(f"  is_overdue: {detail_short['is_overdue']}")

print("\n--- 5.2 未来日期工单不应逾期 ---")
detail_future, s = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
assert_eq(s, 200, "获取未来工单成功")
assert_true(detail_future.get("is_overdue") is False, "未来工单 is_overdue=false")

print("\n--- 5.3 已完成工单即使过了截止时间也不算逾期 ---")
# 验证已完成的 B 区工单（如果它的 deadline 在过去）
# 由于 B 区是晚班，今天的晚班截止时间可能还没到，我们用列表筛选来验证逻辑
# 完成状态的工单 is_overdue 应该为 false
detail_completed, _ = http_get_json(f"/inspection-work-orders/{wo_b_night_id}")
assert_true(detail_completed["status"] == "completed", "工单状态为 completed")
# 即使 deadline 过了，已完成工单也不算逾期
# 这里我们验证逻辑：如果已完成，is_overdue 一定是 false
if detail_completed.get("is_overdue") is not None:
    assert_true(detail_completed["is_overdue"] is False, "已完成工单 is_overdue=false")

print("\n--- 5.4 按逾期状态筛选工单 ---")
r_overdue, s = http_get_json("/inspection-work-orders?is_overdue=true")
assert_eq(s, 200, "按逾期筛选成功")
assert_true(any(o["id"] == wo_short_deadline_id for o in r_overdue), "逾期工单包含短时工单")

r_not_overdue, s = http_get_json("/inspection-work-orders?is_overdue=false")
assert_eq(s, 200, "按未逾期筛选成功")
assert_true(any(o["id"] == wo_a_morning_id for o in r_not_overdue), "未逾期工单包含A区早班工单")

# ========== TEST 6: 报警关联 ==========
print()
print("=" * 70)
print("TEST 6: 报警关联与快照")
print("=" * 70)

if test_alarm:
    print("\n--- 6.1 关联报警到工单 ---")
    r, s = http_post(f"/inspection-work-orders/{wo_a_morning_id}/alarms", {
        "alarm_id": test_alarm["id"],
        "associated_by": p_admin["id"]
    })
    assert_eq(s, 200, "关联报警成功")
    assert_eq(r["alarm_id"], test_alarm["id"], "alarm_id 正确")
    assert_true(r["alarm_snapshot"] is not None, "保存了报警快照")
    assert_true("sensor_code" in r["alarm_snapshot"] or "sensor_id" in str(r["alarm_snapshot"]),
                "快照包含传感器信息")
    assoc_alarm_id = r["id"]
    print(f"  关联记录 ID: {assoc_alarm_id}")

    print("\n--- 6.2 工单详情中可以看到关联报警 ---")
    detail_with_alarms, _ = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
    alarms_list = detail_with_alarms.get("associated_alarms", [])
    assert_true(len(alarms_list) >= 1, "工单详情包含关联报警")
    alarm_assoc = alarms_list[0]
    assert_true("alarm_snapshot" in alarm_assoc, "包含报警快照")
    assert_true("associator_name" in alarm_assoc, "包含关联人名称")

    print("\n--- 6.3 工单列表中显示报警数量 ---")
    list_wo, _ = http_get_json(f"/inspection-work-orders?zone_id={z_a['id']}")
    wo_in_list = next((o for o in list_wo if o["id"] == wo_a_morning_id), None)
    assert_true(wo_in_list is not None, "列表中找到工单")
    assert_true(wo_in_list.get("alarm_count", 0) >= 1, "列表中 alarm_count >= 1")

    print("\n--- 6.4 不能重复关联同一报警 (409) ---")
    r, s = http_post(f"/inspection-work-orders/{wo_a_morning_id}/alarms", {
        "alarm_id": test_alarm["id"],
        "associated_by": p_admin["id"]
    })
    assert_eq(s, 409, "重复关联返回 409")

    print("\n--- 6.5 observer 不能关联报警 (403) ---")
    r, s = http_post(f"/inspection-work-orders/{wo_short_deadline_id}/alarms", {
        "alarm_id": test_alarm["id"],
        "associated_by": p_obs["id"]
    })
    assert_eq(s, 403, "observer 关联报警返回 403")

    print("\n--- 6.6 解除报警关联 ---")
    r, s = http_delete(
        f"/inspection-work-orders/{wo_a_morning_id}/alarms/{test_alarm['id']}?person_id={p_admin['id']}"
    )
    assert_eq(s, 200, "解除关联成功")
    assert_true(r.get("success") is True, "返回 success=true")

    # 验证已解除
    detail_after, _ = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
    alarms_after = detail_after.get("associated_alarms", [])
    still_associated = any(a["alarm_id"] == test_alarm["id"] for a in alarms_after)
    assert_true(not still_associated, "解除后不再关联")
else:
    print("\n  [SKIP] 没有可用的报警，跳过报警关联测试")

# ========== TEST 7: 工单日志 ==========
print()
print("=" * 70)
print("TEST 7: 工单操作日志")
print("=" * 70)

print("\n--- 7.1 工单详情包含操作日志 ---")
detail_with_logs, _ = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
logs = detail_with_logs.get("logs", [])
assert_true(len(logs) >= 3, f"至少有 3 条操作日志（生成、领取、更新项等，实际{len(logs)}条）")

log_types = [log["action"] for log in logs]
assert_true("generated" in log_types, "包含 generated 日志")
assert_true("claimed" in log_types, "包含 claimed 日志")

for log in logs:
    assert_true("action" in log, "日志包含 action")
    assert_true("operator_name" in log, "日志包含 operator_name")
    assert_true("created_at" in log, "日志包含 created_at")

# ========== TEST 8: 列表筛选 ==========
print()
print("=" * 70)
print("TEST 8: 工单列表筛选")
print("=" * 70)

print("\n--- 8.1 按库区筛选 ---")
r, s = http_get_json(f"/inspection-work-orders?zone_id={z_a['id']}")
assert_eq(s, 200, "按库区筛选成功")
for wo in r:
    assert_eq(wo["zone_id"], z_a["id"], f"工单{wo['id']}属于A区")

print("\n--- 8.2 按状态筛选 ---")
r, s = http_get_json("/inspection-work-orders?status=completed")
assert_eq(s, 200, "按 completed 状态筛选成功")
for wo in r:
    assert_eq(wo["status"], "completed", f"工单{wo['id']}状态为 completed")

print("\n--- 8.3 按负责人（领取人）筛选 ---")
r, s = http_get_json(f"/inspection-work-orders?claimed_by={p_op['id']}")
assert_eq(s, 200, "按领取人筛选成功")
for wo in r:
    assert_eq(wo["claimed_by"], p_op["id"], f"工单{wo['id']}领取人为 operator")

print("\n--- 8.4 按班次类型筛选 ---")
r, s = http_get_json("/inspection-work-orders?shift_type=morning")
assert_eq(s, 200, "按早班筛选成功")
for wo in r:
    assert_eq(wo["shift_type"], "morning", f"工单{wo['id']}班次为 morning")

print("\n--- 8.5 按日期范围筛选 ---")
r, s = http_get_json(f"/inspection-work-orders?work_date_from={WORK_DATE_FUTURE}&work_date_to={WORK_DATE_FUTURE}")
assert_eq(s, 200, "按日期范围筛选成功")
for wo in r:
    assert_eq(wo["work_date"], WORK_DATE_FUTURE, f"工单{wo['id']}日期正确")

# ========== TEST 9: 列表/导出一致性 ==========
print()
print("=" * 70)
print("TEST 9: 列表/导出数据一致性")
print("=" * 70)

print("\n--- 9.1 JSON 导出与列表 API 数据一致 ---")
json_text, s_json = http_get("/inspection-work-orders/export.json")
assert_eq(s_json, 200, "JSON 导出成功")
json_data = json.loads(json_text)

api_list, s_api = http_get_json("/inspection-work-orders")
assert_eq(s_api, 200, "列表 API 成功")

assert_eq(len(json_data), len(api_list), "JSON 导出条数 = 列表 API 条数")

# 验证关键字段一致
for api_item in api_list:
    export_item = next((e for e in json_data if e["id"] == api_item["id"]), None)
    assert_true(export_item is not None, f"JSON导出中找到工单{api_item['id']}")
    if export_item:
        assert_eq(export_item["status"], api_item["status"],
                  f"工单{api_item['id']} status 一致")
        assert_eq(export_item["zone_id"], api_item["zone_id"],
                  f"工单{api_item['id']} zone_id 一致")
        assert_eq(export_item["item_count"], api_item["item_count"],
                  f"工单{api_item['id']} item_count 一致")
        assert_eq(export_item["pending_count"], api_item["pending_count"],
                  f"工单{api_item['id']} pending_count 一致")
        assert_eq(export_item["abnormal_count"], api_item["abnormal_count"],
                  f"工单{api_item['id']} abnormal_count 一致")
        assert_eq(export_item["alarm_count"], api_item["alarm_count"],
                  f"工单{api_item['id']} alarm_count 一致")

print("\n--- 9.2 CSV 导出与列表 API 数据一致 ---")
csv_text, s_csv = http_get("/inspection-work-orders/export.csv")
assert_eq(s_csv, 200, "CSV 导出成功")
csv_reader = csv.reader(io.StringIO(csv_text))
csv_rows = list(csv_reader)
assert_true(len(csv_rows) >= 2, "CSV 至少有表头 + 1 行数据")

csv_header = csv_rows[0]
assert_true("id" in csv_header, "CSV 包含 id 列")
assert_true("status" in csv_header, "CSV 包含 status 列")
assert_true("zone_name" in csv_header, "CSV 包含 zone_name 列")
assert_true("pending_count" in csv_header, "CSV 包含 pending_count 列")
assert_true("abnormal_count" in csv_header, "CSV 包含 abnormal_count 列")
assert_true("alarm_count" in csv_header, "CSV 包含 alarm_count 列")

assert_eq(len(csv_rows) - 1, len(api_list), "CSV 数据行数 = API 返回工单数")

# 验证 CSV 数据与 API 一致
for row in csv_rows[1:]:
    row_id = int(row[csv_header.index("id")])
    api_wo = next((w for w in api_list if w["id"] == row_id), None)
    assert_true(api_wo is not None, f"CSV中找到工单{row_id}")
    if api_wo:
        csv_status = row[csv_header.index("status")]
        assert_eq(csv_status, api_wo["status"], f"CSV工单{row_id} status 一致")
        csv_pending = int(row[csv_header.index("pending_count")])
        assert_eq(csv_pending, api_wo["pending_count"], f"CSV工单{row_id} pending_count 一致")
        csv_abnormal = int(row[csv_header.index("abnormal_count")])
        assert_eq(csv_abnormal, api_wo["abnormal_count"], f"CSV工单{row_id} abnormal_count 一致")
        csv_alarm_count = int(row[csv_header.index("alarm_count")])
        assert_eq(csv_alarm_count, api_wo["alarm_count"], f"CSV工单{row_id} alarm_count 一致")

print("\n--- 9.3 详情导出与详情 API 一致 ---")
detail_api, s_detail = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
assert_eq(s_detail, 200, "详情 API 成功")

export_text, s_export = http_get(f"/inspection-work-orders/{wo_a_morning_id}/export.json")
assert_eq(s_export, 200, "详情导出成功")
export_detail = json.loads(export_text)

assert_eq(export_detail["id"], detail_api["id"], "详情导出 id 一致")
assert_eq(export_detail["status"], detail_api["status"], "详情导出 status 一致")
assert_eq(len(export_detail["items"]), len(detail_api["items"]), "详情导出 items 数量一致")

# ========== TEST 10: 详情完整性 ==========
print()
print("=" * 70)
print("TEST 10: 详情完整性验证")
print("=" * 70)

print("\n--- 10.1 模板详情包含所有必要字段 ---")
template_detail, _ = http_get_json(f"/inspection-templates/{template_a_morning_id}")
template_fields = ["id", "name", "zone_id", "zone_name", "shift_type", "deadline_hours",
                   "status", "created_by", "creator_name", "checkpoints", "created_at"]
for field in template_fields:
    assert_true(field in template_detail, f"模板详情包含字段: {field}")

print("\n--- 10.2 工单列表包含所有必要字段 ---")
if api_list:
    wo_list_item = api_list[0]
    list_fields = ["id", "template_id", "zone_id", "zone_name", "shift_type", "work_date",
                   "deadline", "status", "is_overdue", "claimed_by", "claimer_name",
                   "item_count", "pending_count", "abnormal_count", "alarm_count",
                   "created_at"]
    for field in list_fields:
        assert_true(field in wo_list_item, f"工单列表项包含字段: {field}")

print("\n--- 10.3 工单详情包含所有必要字段 ---")
detail_full_fields = ["id", "template_id", "zone_id", "zone_name", "shift_type", "work_date",
                      "deadline", "status", "is_overdue", "claimed_by", "claimer_name",
                      "claimed_at", "completed_by", "completer_name", "completed_at",
                      "general_remark", "created_by", "creator_name", "items",
                      "associated_alarms", "logs", "created_at", "updated_at"]
for field in detail_full_fields:
    assert_true(field in detail_api, f"工单详情包含字段: {field}")

print("\n--- 10.4 巡检项详情包含所有必要字段 ---")
if detail_api["items"]:
    item = detail_api["items"][0]
    item_fields = ["id", "work_order_id", "checkpoint_id", "checkpoint_name",
                   "checkpoint_description", "sort_order", "require_photo",
                   "require_temperature", "temperature_value", "photo_urls",
                   "check_status", "checked_by", "checked_by_name", "checked_at",
                   "remark", "exception_action", "handler_id", "handler_name",
                   "created_at", "updated_at"]
    for field in item_fields:
        assert_true(field in item, f"巡检项包含字段: {field}")

# ========== TEST 11: 数据持久化验证（服务重启前记录） ==========
print()
print("=" * 70)
print("TEST 11: 数据持久化验证（当前状态记录）")
print("=" * 70)

print("\n--- 11.1 记录所有测试数据 ID ---")
all_templates_before, _ = http_get_json("/inspection-templates")
all_work_orders_before, _ = http_get_json("/inspection-work-orders")
print(f"  模板数量: {len(all_templates_before)}")
print(f"  工单数量: {len(all_work_orders_before)}")

print("\n--- 11.2 验证所有创建的模板存在 ---")
template_ids = [t["id"] for t in all_templates_before]
assert_true(template_a_morning_id in template_ids, f"模板{template_a_morning_id}存在")
assert_true(template_b_night_id in template_ids, f"模板{template_b_night_id}存在")
assert_true(template_short_deadline_id in template_ids, f"模板{template_short_deadline_id}存在")

print("\n--- 11.3 验证所有创建的工单存在 ---")
work_order_ids = [w["id"] for w in all_work_orders_before]
assert_true(wo_a_morning_id in work_order_ids, f"工单{wo_a_morning_id}存在")
assert_true(wo_b_night_id in work_order_ids, f"工单{wo_b_night_id}存在")
assert_true(wo_short_deadline_id in work_order_ids, f"工单{wo_short_deadline_id}存在")

print("\n--- 11.4 验证工单状态持久化 ---")
detail_b_check, _ = http_get_json(f"/inspection-work-orders/{wo_b_night_id}")
assert_eq(detail_b_check["status"], "completed", "B区工单状态仍为 completed")
assert_eq(detail_b_check["completed_by"], p_op["id"], "completed_by 仍为 operator")

detail_a_check, _ = http_get_json(f"/inspection-work-orders/{wo_a_morning_id}")
assert_eq(detail_a_check["status"], "claimed", "A区工单状态仍为 claimed")
assert_eq(detail_a_check["claimed_by"], p_op["id"], "claimed_by 仍为 operator")

print("\n--- 11.5 验证巡检项数据持久化 ---")
detail_items_check = detail_a_check["items"]
checked_item = next((i for i in detail_items_check if i["check_status"] == "normal"), None)
assert_true(checked_item is not None, "存在已检查的巡检项")
if checked_item:
    assert_true(checked_item["checked_at"] is not None, "checked_at 持久化")
    assert_eq(checked_item["checked_by"], p_op["id"], "checked_by 持久化")

print("\n  提示: 重启服务后运行 test_inspection_restart.py 验证跨重启一致性")

# ========== 总结 ==========
print()
print("=" * 70)
print(f"冷库巡检工单全面测试汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 所有冷库巡检工单测试通过！")
    print("\n提示：")
    print("  1. 重启服务后运行 test_inspection_restart.py 验证跨重启一致性")
    print("  2. 查看 README.md 中的 curl 示例了解 API 用法")
else:
    print(f"\n[FAIL] 有 {FAIL} 个测试失败。")
    exit(1)
