"""
交接班巡检清单全面测试
覆盖：
1. 权限验证（admin/operator 可创建/提交/更新，observer 只能查看）
2. 重复班次冲突检测（同一库区同一班次不能重复创建）
3. 撤回未提交清单（撤回后可重建）
4. 已提交清单不可修改
5. 追加检查结果、异常备注和处理人
6. 快照不被旧数据改写（导入新读数后快照不变）
7. 列表筛选
8. CSV/JSON 导出一致性（报警数量和检查项状态与 API 查询一致）
9. 跨服务重启数据持久化
"""
import json
import urllib.request
import urllib.error
import io
import csv

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
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code


def http_put(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code


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
print("交接班巡检清单全面测试")
print("=" * 70)

print("\n--- 初始化：获取基础数据 ---")
persons, _ = http_get_json("/persons")
sensors, _ = http_get_json("/sensors")
zones, _ = http_get_json("/zones")

p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]

z_a = [z for z in zones if z["name"] == "冷冻库区A"][0]
z_b = [z for z in zones if z["name"] == "冷冻库区B"][0]

sensors_a = [s for s in sensors if s["zone_id"] == z_a["id"]]
sensors_b = [s for s in sensors if s["zone_id"] == z_b["id"]]

print(f"  admin={p_admin['id']}, operator={p_op['id']}, observer={p_obs['id']}")
print(f"  冷冻库区A={z_a['id']} (传感器{len(sensors_a)}个), 冷冻库区B={z_b['id']} (传感器{len(sensors_b)}个)")

# ========== TEST 1: 权限验证 ==========
print()
print("=" * 70)
print("TEST 1: 权限验证")
print("=" * 70)

print("\n--- 1.1 observer 不能创建清单 (403) ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_a["id"],
    "shift_date": "2099-01-01",
    "shift_type": "morning",
    "created_by": p_obs["id"]
})
assert_eq(s, 403, "observer 创建返回 403")
assert_contains(r.get("detail", ""), "Permission denied", "错误信息包含 Permission denied")

print("\n--- 1.2 admin 可以创建清单 ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_a["id"],
    "shift_date": "2099-01-01",
    "shift_type": "morning",
    "created_by": p_admin["id"],
    "general_remark": "测试用清单"
})
assert_eq(s, 200, "admin 创建成功")
assert_eq(r["status"], "draft", "初始状态为 draft")
checklist_admin_id = r["id"]
print(f"  清单 ID: {checklist_admin_id}")

print("\n--- 1.3 operator 可以创建清单 ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_b["id"],
    "shift_date": "2099-01-01",
    "shift_type": "morning",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "operator 创建成功")
checklist_op_id = r["id"]

print("\n--- 1.4 observer 可以查看清单列表和详情 ---")
r_list, s_list = http_get_json("/shift-checklists")
assert_eq(s_list, 200, "observer 查看列表成功 (200)")
assert_true(len(r_list) >= 2, "列表至少有 2 条清单")

r_detail, s_detail = http_get_json(f"/shift-checklists/{checklist_admin_id}")
assert_eq(s_detail, 200, "observer 查看详情成功 (200)")
assert_eq(r_detail["id"], checklist_admin_id, "详情 ID 正确")

print("\n--- 1.5 observer 不能提交清单 (403) ---")
r, s = http_post(f"/shift-checklists/{checklist_op_id}/submit", {
    "person_id": p_obs["id"]
})
assert_eq(s, 403, "observer 提交返回 403")

print("\n--- 1.6 observer 不能撤回清单 (403) ---")
r, s = http_post(f"/shift-checklists/{checklist_op_id}/revoke", {
    "person_id": p_obs["id"]
})
assert_eq(s, 403, "observer 撤回返回 403")

print("\n--- 1.7 observer 不能更新检查项 (403) ---")
sensor_items = r_detail.get("sensor_items", [])
if sensor_items:
    r, s = http_put(
        f"/shift-checklists/{checklist_admin_id}/sensor-items/{sensor_items[0]['id']}",
        {"person_id": p_obs["id"], "check_status": "normal"}
    )
    assert_eq(s, 403, "observer 更新传感器检查项返回 403")

manual_items = r_detail.get("manual_items", [])
if manual_items:
    r, s = http_put(
        f"/shift-checklists/{checklist_admin_id}/manual-items/{manual_items[0]['id']}",
        {"person_id": p_obs["id"], "check_status": "normal"}
    )
    assert_eq(s, 403, "observer 更新手动检查项返回 403")

# ========== TEST 2: 清单内容验证 ==========
print()
print("=" * 70)
print("TEST 2: 清单内容验证（传感器快照 + 手动检查项）")
print("=" * 70)

print("\n--- 2.1 传感器检查项包含阈值快照 ---")
detail, _ = http_get_json(f"/shift-checklists/{checklist_admin_id}")
sensor_items = detail.get("sensor_items", [])
assert_true(len(sensor_items) >= 1, f"至少有 1 个传感器检查项 (实际{len(sensor_items)})")

for si in sensor_items:
    assert_true(si["snapshot_threshold_upper"] is not None, f"传感器{si['sensor_code']}有上限阈值快照")
    assert_true(si["snapshot_threshold_lower"] is not None, f"传感器{si['sensor_code']}有下限阈值快照")
    assert_eq(si["check_status"], "pending", f"传感器{si['sensor_code']}初始状态为 pending")
    assert_true(si["sensor_code"] is not None, f"传感器检查项有 sensor_code")

print("\n--- 2.2 手动检查项已自动生成 ---")
manual_items = detail.get("manual_items", [])
assert_true(len(manual_items) >= 5, f"至少有 5 个手动检查项 (实际{len(manual_items)})")

expected_items = ["制冷机组运行状态", "库门密封检查", "传感器外观及固定", "库区卫生情况", "应急设备检查"]
for expected in expected_items:
    found = any(mi["item_name"] == expected for mi in manual_items)
    assert_true(found, f"包含检查项: {expected}")

print("\n--- 2.3 未处理报警快照内部一致性 ---")
for si in sensor_items:
    if si["snapshot_open_alarm_ids"]:
        alarm_ids = json.loads(si["snapshot_open_alarm_ids"])
        assert_eq(si["snapshot_open_alarm_count"], len(alarm_ids),
                  f"传感器{si['sensor_code']} 报警数与ID列表一致: count={si['snapshot_open_alarm_count']}, ids={len(alarm_ids)}")
    else:
        assert_eq(si["snapshot_open_alarm_count"], 0,
                  f"传感器{si['sensor_code']} 无报警时count=0")

# ========== TEST 3: 重复班次冲突 ==========
print()
print("=" * 70)
print("TEST 3: 重复班次冲突检测")
print("=" * 70)

print("\n--- 3.1 同一库区同一班次不能重复创建 (409) ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_a["id"],
    "shift_date": "2099-01-01",
    "shift_type": "morning",
    "created_by": p_admin["id"]
})
assert_eq(s, 409, "重复班次返回 409")
assert_contains(r.get("detail", ""), "Duplicate", "错误信息包含 Duplicate")

print("\n--- 3.2 同一库区不同班次可以创建 ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_a["id"],
    "shift_date": "2099-01-01",
    "shift_type": "afternoon",
    "created_by": p_admin["id"]
})
assert_eq(s, 200, "不同班次创建成功")
checklist_afternoon_id = r["id"]

print("\n--- 3.3 不同库区同一班次可以创建 ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_b["id"],
    "shift_date": "2099-01-01",
    "shift_type": "night",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "不同库区同一班次创建成功")

# ========== TEST 4: 追加检查结果 ==========
print()
print("=" * 70)
print("TEST 4: 追加检查结果、异常备注和处理人")
print("=" * 70)

detail, _ = http_get_json(f"/shift-checklists/{checklist_admin_id}")
sensor_items = detail.get("sensor_items", [])
manual_items = detail.get("manual_items", [])

print("\n--- 4.1 更新传感器检查项为 normal ---")
if sensor_items:
    si = sensor_items[0]
    r, s = http_put(
        f"/shift-checklists/{checklist_admin_id}/sensor-items/{si['id']}",
        {"person_id": p_op["id"], "check_status": "normal"}
    )
    assert_eq(s, 200, "更新传感器检查项成功")
    assert_eq(r["check_status"], "normal", "状态变为 normal")
    assert_eq(r["checked_by"], p_op["id"], "checked_by 正确")
    assert_true(r["checked_at"] is not None, "checked_at 已设置")

print("\n--- 4.2 更新传感器检查项为 abnormal（带备注和处理人） ---")
if len(sensor_items) > 1:
    si = sensor_items[1]
    r, s = http_put(
        f"/shift-checklists/{checklist_admin_id}/sensor-items/{si['id']}",
        {
            "person_id": p_op["id"],
            "check_status": "abnormal",
            "abnormal_remark": "温度偏离正常范围",
            "handler_id": p_admin["id"]
        }
    )
    assert_eq(s, 200, "更新传感器检查项为 abnormal 成功")
    assert_eq(r["check_status"], "abnormal", "状态变为 abnormal")
    assert_eq(r["abnormal_remark"], "温度偏离正常范围", "异常备注正确")
    assert_eq(r["handler_id"], p_admin["id"], "处理人 ID 正确")
    assert_eq(r["handler_name"], p_admin["name"], "处理人名称正确")

print("\n--- 4.3 更新手动检查项 ---")
if manual_items:
    mi = manual_items[0]
    r, s = http_put(
        f"/shift-checklists/{checklist_admin_id}/manual-items/{mi['id']}",
        {
            "person_id": p_admin["id"],
            "check_status": "normal"
        }
    )
    assert_eq(s, 200, "更新手动检查项成功")
    assert_eq(r["check_status"], "normal", "手动检查项状态变为 normal")

if len(manual_items) > 1:
    mi = manual_items[1]
    r, s = http_put(
        f"/shift-checklists/{checklist_admin_id}/manual-items/{mi['id']}",
        {
            "person_id": p_op["id"],
            "check_status": "abnormal",
            "abnormal_remark": "库门密封条老化需要更换",
            "handler_id": p_op["id"]
        }
    )
    assert_eq(s, 200, "更新手动检查项为 abnormal 成功")
    assert_eq(r["abnormal_remark"], "库门密封条老化需要更换", "异常备注正确")

# ========== TEST 5: 已提交清单不可修改 ==========
print()
print("=" * 70)
print("TEST 5: 已提交清单不可修改")
print("=" * 70)

print("\n--- 5.1 operator 可以提交清单 ---")
r, s = http_post(f"/shift-checklists/{checklist_op_id}/submit", {
    "person_id": p_op["id"],
    "general_remark": "B区早班巡检完毕"
})
assert_eq(s, 200, "operator 提交清单成功")
assert_eq(r["status"], "submitted", "状态变为 submitted")
assert_eq(r["submitted_by"], p_op["id"], "submitted_by 正确")
assert_eq(r["general_remark"], "B区早班巡检完毕", "备注正确")

print("\n--- 5.2 已提交清单不能再修改检查项 ---")
detail_submitted, _ = http_get_json(f"/shift-checklists/{checklist_op_id}")
si_submitted = detail_submitted.get("sensor_items", [])
if si_submitted:
    r, s = http_put(
        f"/shift-checklists/{checklist_op_id}/sensor-items/{si_submitted[0]['id']}",
        {"person_id": p_op["id"], "check_status": "normal"}
    )
    assert_eq(s, 400, "已提交清单修改检查项返回 400")
    assert_contains(r.get("detail", ""), "Cannot modify submitted", "错误信息正确")

print("\n--- 5.3 已提交清单不能再提交 ---")
r, s = http_post(f"/shift-checklists/{checklist_op_id}/submit", {
    "person_id": p_op["id"]
})
assert_eq(s, 400, "已提交清单再次提交返回 400")

print("\n--- 5.4 已提交清单不能撤回 ---")
r, s = http_post(f"/shift-checklists/{checklist_op_id}/revoke", {
    "person_id": p_op["id"]
})
assert_eq(s, 400, "已提交清单不能撤回")

# ========== TEST 6: 撤回未提交清单 ==========
print()
print("=" * 70)
print("TEST 6: 撤回未提交清单")
print("=" * 70)

print("\n--- 6.1 admin 可以撤回 draft 清单 ---")
r, s = http_post(f"/shift-checklists/{checklist_afternoon_id}/revoke", {
    "person_id": p_admin["id"]
})
assert_eq(s, 200, "admin 撤回清单成功")
assert_eq(r["status"], "revoked", "状态变为 revoked")
assert_eq(r["revoked_by"], p_admin["id"], "revoked_by 正确")

print("\n--- 6.2 撤回后可以重建同班次清单 ---")
r, s = http_post("/shift-checklists", {
    "zone_id": z_a["id"],
    "shift_date": "2099-01-01",
    "shift_type": "afternoon",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "撤回后重建成功")
checklist_rebuilt_id = r["id"]
print(f"  重建清单 ID: {checklist_rebuilt_id}")

print("\n--- 6.3 撤回后清单不能修改检查项 ---")
r_detail_revoked, _ = http_get_json(f"/shift-checklists/{checklist_afternoon_id}")
si_revoked = r_detail_revoked.get("sensor_items", [])
if si_revoked:
    r, s = http_put(
        f"/shift-checklists/{checklist_afternoon_id}/sensor-items/{si_revoked[0]['id']}",
        {"person_id": p_op["id"], "check_status": "normal"}
    )
    assert_eq(s, 400, "已撤回清单修改检查项返回 400")
    assert_contains(r.get("detail", ""), "revoked", "错误信息包含 revoked")

# ========== TEST 7: 快照不被旧数据改写 ==========
print()
print("=" * 70)
print("TEST 7: 导入新读数后清单快照不被旧数据改写")
print("=" * 70)

print("\n--- 7.1 记录当前快照数据 ---")
detail_before, _ = http_get_json(f"/shift-checklists/{checklist_admin_id}")
si_before = detail_before.get("sensor_items", [])
snapshot_data_before = {}
for si in si_before:
    snapshot_data_before[si["sensor_id"]] = {
        "threshold_upper": si["snapshot_threshold_upper"],
        "threshold_lower": si["snapshot_threshold_lower"],
        "latest_reading_value": si["snapshot_latest_reading_value"],
        "latest_reading_time": si["snapshot_latest_reading_time"],
        "open_alarm_count": si["snapshot_open_alarm_count"],
        "open_alarm_ids": si["snapshot_open_alarm_ids"],
    }

print("\n--- 7.2 导入新的温度读数 ---")
r_import, s_import = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -13.0, "reading_time": "2099-08-01T10:00:00"}
])
print(f"  导入结果: successful={r_import['successful']}, new_alarms={r_import['new_alarms']}")

print("\n--- 7.3 修改阈值 ---")
s1 = [s for s in sensors if s["code"] == "TEMP-001"][0]
r_thresh, s_thresh = http_post("/thresholds", {
    "sensor_id": s1["id"],
    "upper_limit": -10.0,
    "lower_limit": -30.0,
    "dedup_window_minutes": 60,
    "effective_from": "2099-08-01T00:00:00"
})
assert_eq(s_thresh, 200, "新阈值版本创建成功")

print("\n--- 7.4 验证清单快照不变 ---")
detail_after, _ = http_get_json(f"/shift-checklists/{checklist_admin_id}")
si_after = detail_after.get("sensor_items", [])

for si in si_after:
    sid = si["sensor_id"]
    if sid in snapshot_data_before:
        before = snapshot_data_before[sid]
        assert_eq(si["snapshot_threshold_upper"], before["threshold_upper"],
                  f"传感器{si.get('sensor_code', sid)} 阈值上限快照不变")
        assert_eq(si["snapshot_threshold_lower"], before["threshold_lower"],
                  f"传感器{si.get('sensor_code', sid)} 阈值下限快照不变")
        assert_eq(si["snapshot_latest_reading_value"], before["latest_reading_value"],
                  f"传感器{si.get('sensor_code', sid)} 最近读数值快照不变")
        assert_eq(si["snapshot_open_alarm_count"], before["open_alarm_count"],
                  f"传感器{si.get('sensor_code', sid)} 未处理报警数快照不变")

# ========== TEST 8: 列表筛选 ==========
print()
print("=" * 70)
print("TEST 8: 列表筛选")
print("=" * 70)

print("\n--- 8.1 按库区筛选 ---")
r, s = http_get_json(f"/shift-checklists?zone_id={z_a['id']}")
assert_eq(s, 200, "按库区筛选成功")
for c in r:
    assert_eq(c["zone_id"], z_a["id"], f"清单{c['id']}属于库区A")

print("\n--- 8.2 按状态筛选 ---")
r, s = http_get_json("/shift-checklists?status=submitted")
assert_eq(s, 200, "按 submitted 状态筛选成功")
for c in r:
    assert_eq(c["status"], "submitted", f"清单{c['id']}状态为 submitted")

print("\n--- 8.3 按班次类型筛选 ---")
r, s = http_get_json("/shift-checklists?shift_type=morning")
assert_eq(s, 200, "按 morning 班次筛选成功")
for c in r:
    assert_eq(c["shift_type"], "morning", f"清单{c['id']}班次为 morning")

print("\n--- 8.4 按创建人筛选 ---")
r, s = http_get_json(f"/shift-checklists?created_by={p_admin['id']}")
assert_eq(s, 200, "按创建人筛选成功")
for c in r:
    assert_eq(c["created_by"], p_admin["id"], f"清单{c['id']}创建人为 admin")

print("\n--- 8.5 按日期范围筛选 ---")
r, s = http_get_json("/shift-checklists?shift_date_from=2099-01-01&shift_date_to=2099-01-01")
assert_eq(s, 200, "按日期范围筛选成功")
for c in r:
    assert_true(c["shift_date"] is not None, f"清单{c['id']}有日期")

# ========== TEST 9: CSV/JSON 导出一致性 ==========
print()
print("=" * 70)
print("TEST 9: CSV/JSON 导出一致性")
print("=" * 70)

print("\n--- 9.1 CSV 导出 ---")
csv_text, s_csv = http_get("/shift-checklists/export.csv")
assert_eq(s_csv, 200, "CSV 导出成功")
csv_reader = csv.reader(io.StringIO(csv_text))
csv_rows = list(csv_reader)
assert_true(len(csv_rows) >= 2, "至少有表头 + 1 行数据")

csv_header = csv_rows[0]
assert_true("id" in csv_header, "CSV 包含 id 列")
assert_true("zone_name" in csv_header, "CSV 包含 zone_name 列")
assert_true("status" in csv_header, "CSV 包含 status 列")
assert_true("shift_type" in csv_header, "CSV 包含 shift_type 列")
assert_true("sensor_item_count" in csv_header, "CSV 包含 sensor_item_count 列")
assert_true("pending_count" in csv_header, "CSV 包含 pending_count 列")
assert_true("abnormal_count" in csv_header, "CSV 包含 abnormal_count 列")

api_checklists, _ = http_get_json("/shift-checklists")
assert_eq(len(csv_rows) - 1, len(api_checklists), "CSV 数据行数 = API 返回清单数")

print("\n--- 9.2 JSON 导出 ---")
json_text, s_json = http_get("/shift-checklists/export.json")
assert_eq(s_json, 200, "JSON 导出成功")
json_data = json.loads(json_text)
assert_eq(len(json_data), len(api_checklists), "JSON 数据条数 = API 返回清单数")

print("\n--- 9.3 报警快照内部一致性 ---")
for c in api_checklists:
    detail, _ = http_get_json(f"/shift-checklists/{c['id']}")
    for si in detail.get("sensor_items", []):
        if si["snapshot_open_alarm_ids"]:
            alarm_ids = json.loads(si["snapshot_open_alarm_ids"])
            assert_eq(si["snapshot_open_alarm_count"], len(alarm_ids),
                      f"清单{c['id']} 传感器{si.get('sensor_code', '?')} 报警数与ID列表一致: count={si['snapshot_open_alarm_count']}, ids={len(alarm_ids)}")
        else:
            assert_eq(si["snapshot_open_alarm_count"], 0,
                      f"清单{c['id']} 传感器{si.get('sensor_code', '?')} 无报警时count=0")

print("\n--- 9.4 检查项状态与 API 查询一致 ---")
for c in api_checklists:
    detail, _ = http_get_json(f"/shift-checklists/{c['id']}")
    all_items = detail.get("sensor_items", []) + detail.get("manual_items", [])
    pending = sum(1 for i in all_items if i["check_status"] == "pending")
    abnormal = sum(1 for i in all_items if i["check_status"] == "abnormal")

    list_item = next((cl for cl in api_checklists if cl["id"] == c["id"]), None)
    if list_item:
        assert_eq(list_item["pending_count"], pending,
                  f"清单{c['id']} pending_count: 列表={list_item['pending_count']}, 详情={pending}")
        assert_eq(list_item["abnormal_count"], abnormal,
                  f"清单{c['id']} abnormal_count: 列表={list_item['abnormal_count']}, 详情={abnormal}")

print("\n--- 9.5 CSV 中的 pending_count/abnormal_count 与 API 一致 ---")
for row in csv_rows[1:]:
    row_id = int(row[0])
    api_cl = next((cl for cl in api_checklists if cl["id"] == row_id), None)
    if api_cl:
        csv_pending = int(row[csv_header.index("pending_count")])
        csv_abnormal = int(row[csv_header.index("abnormal_count")])
        assert_eq(csv_pending, api_cl["pending_count"],
                  f"CSV清单{row_id} pending_count: CSV={csv_pending}, API={api_cl['pending_count']}")
        assert_eq(csv_abnormal, api_cl["abnormal_count"],
                  f"CSV清单{row_id} abnormal_count: CSV={csv_abnormal}, API={api_cl['abnormal_count']}")

# ========== TEST 10: 详情完整性 ==========
print()
print("=" * 70)
print("TEST 10: 详情完整性")
print("=" * 70)

print("\n--- 10.1 清单详情包含所有必要字段 ---")
detail, _ = http_get_json(f"/shift-checklists/{checklist_admin_id}")
required_fields = ["id", "zone_id", "zone_name", "shift_date", "shift_type", "status",
                   "created_by", "creator_name", "creator_role", "general_remark",
                   "sensor_items", "manual_items", "created_at", "updated_at"]
for field in required_fields:
    assert_true(field in detail, f"详情包含字段: {field}")

print("\n--- 10.2 传感器检查项详情包含必要字段 ---")
if detail.get("sensor_items"):
    si = detail["sensor_items"][0]
    si_fields = ["id", "checklist_id", "sensor_id", "sensor_code", "sensor_name",
                 "snapshot_threshold_upper", "snapshot_threshold_lower",
                 "snapshot_latest_reading_value", "snapshot_latest_reading_time",
                 "snapshot_open_alarm_count", "check_status", "checked_by",
                 "checked_by_name", "checked_at", "abnormal_remark", "handler_id", "handler_name"]
    for field in si_fields:
        assert_true(field in si, f"传感器检查项包含字段: {field}")

print("\n--- 10.3 手动检查项详情包含必要字段 ---")
if detail.get("manual_items"):
    mi = detail["manual_items"][0]
    mi_fields = ["id", "checklist_id", "item_name", "item_description", "check_status",
                 "checked_by", "checked_by_name", "checked_at", "abnormal_remark",
                 "handler_id", "handler_name", "sort_order"]
    for field in mi_fields:
        assert_true(field in mi, f"手动检查项包含字段: {field}")

# ========== TEST 11: admin 可以提交清单 ==========
print()
print("=" * 70)
print("TEST 11: admin 可以提交清单")
print("=" * 70)

print("\n--- 11.1 admin 提交清单 ---")
r, s = http_post(f"/shift-checklists/{checklist_admin_id}/submit", {
    "person_id": p_admin["id"],
    "general_remark": "A区早班巡检完成"
})
assert_eq(s, 200, "admin 提交清单成功")
assert_eq(r["status"], "submitted", "状态变为 submitted")
assert_eq(r["submitted_by"], p_admin["id"], "submitted_by 正确")
assert_eq(r["submitter_name"], p_admin["name"], "submitter_name 正确")
assert_true(r["submitted_at"] is not None, "submitted_at 已设置")

# ========== TEST 12: 跨服务重启数据持久化提示 ==========
print()
print("=" * 70)
print("TEST 12: 跨服务重启数据持久化（本测试仅验证数据落库）")
print("=" * 70)

print("\n--- 12.1 验证所有创建的清单在列表中 ---")
all_checklists, _ = http_get_json("/shift-checklists")
checklist_ids = [c["id"] for c in all_checklists]
assert_true(checklist_admin_id in checklist_ids, f"admin清单{checklist_admin_id}存在")
assert_true(checklist_op_id in checklist_ids, f"operator清单{checklist_op_id}存在")
assert_true(checklist_rebuilt_id in checklist_ids, f"重建清单{checklist_rebuilt_id}存在")

print("\n--- 12.2 验证已提交清单状态持久化 ---")
detail_submitted, _ = http_get_json(f"/shift-checklists/{checklist_op_id}")
assert_eq(detail_submitted["status"], "submitted", "已提交清单状态仍为 submitted")
assert_eq(detail_submitted["submitted_by"], p_op["id"], "submitted_by 仍为 operator")

print("\n--- 12.3 验证已撤回清单状态持久化 ---")
detail_revoked, _ = http_get_json(f"/shift-checklists/{checklist_afternoon_id}")
assert_eq(detail_revoked["status"], "revoked", "已撤回清单状态仍为 revoked")
assert_eq(detail_revoked["revoked_by"], p_admin["id"], "revoked_by 仍为 admin")

print("\n  提示: 重启服务后运行 test_shift_checklist_restart.py 验证跨重启一致性")

# ========== 总结 ==========
print()
print("=" * 70)
print(f"交接班巡检清单全面测试汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 所有交接班巡检清单测试通过！")
    print("\n提示：重启服务后运行 test_shift_checklist_restart.py 验证跨重启一致性。")
else:
    print(f"\n[FAIL] 有 {FAIL} 个测试失败。")
    exit(1)
