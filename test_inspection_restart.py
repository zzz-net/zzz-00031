"""
冷库巡检工单 - 跨服务重启数据一致性验证
在重启服务后运行此脚本，验证：
1. 所有模板数据仍然存在
2. 所有工单数据仍然存在
3. 工单状态保持不变
4. 巡检项数据保持不变
5. 报警关联仍然存在
6. 操作日志仍然存在
7. 逾期状态计算正确
8. 导出数据与列表API一致
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


# ========== 初始化 ==========
print("=" * 70)
print("冷库巡检工单 - 跨服务重启数据一致性验证")
print("=" * 70)

print("\n--- 初始化：获取基础数据 ---")
persons, _ = http_get_json("/persons")
zones, _ = http_get_json("/zones")

p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]

z_a = [z for z in zones if "A" in z["name"]][0]
z_b = [z for z in zones if "B" in z["name"]][0]

print(f"  admin={p_admin['id']}, operator={p_op['id']}, observer={p_obs['id']}")
print(f"  库区A={z_a['id']}, 库区B={z_b['id']}")

# ========== TEST 1: 模板数据持久化 ==========
print()
print("=" * 70)
print("TEST 1: 模板数据持久化")
print("=" * 70)

print("\n--- 1.1 模板列表不为空 ---")
templates, s = http_get_json("/inspection-templates")
assert_eq(s, 200, "获取模板列表成功")
assert_true(len(templates) >= 3, f"至少有 3 个模板 (实际{len(templates)}个)")

print("\n--- 1.2 模板状态正确 ---")
active_templates = [t for t in templates if t["status"] == "active"]
assert_true(len(active_templates) >= 2, f"至少有 2 个启用状态的模板")

print("\n--- 1.3 模板巡检点数据完整 ---")
if templates:
    t = templates[0]
    detail, s = http_get_json(f"/inspection-templates/{t['id']}")
    assert_eq(s, 200, "获取模板详情成功")
    assert_true("checkpoints" in detail, "包含巡检点")
    assert_true(len(detail["checkpoints"]) >= 1, "至少有 1 个巡检点")
    for cp in detail["checkpoints"]:
        assert_true("name" in cp, "巡检点包含 name")
        assert_true("sort_order" in cp, "巡检点包含 sort_order")

# ========== TEST 2: 工单数据持久化 ==========
print()
print("=" * 70)
print("TEST 2: 工单数据持久化")
print("=" * 70)

print("\n--- 2.1 工单列表不为空 ---")
work_orders, s = http_get_json("/inspection-work-orders")
assert_eq(s, 200, "获取工单列表成功")
assert_true(len(work_orders) >= 3, f"至少有 3 个工单 (实际{len(work_orders)}个)")

print("\n--- 2.2 不同状态的工单都存在 ---")
pending_count = sum(1 for w in work_orders if w["status"] == "pending")
claimed_count = sum(1 for w in work_orders if w["status"] == "claimed")
completed_count = sum(1 for w in work_orders if w["status"] == "completed")
print(f"  pending: {pending_count}, claimed: {claimed_count}, completed: {completed_count}")
assert_true(pending_count >= 1, "至少有 1 个 pending 状态工单")
assert_true(claimed_count >= 1, "至少有 1 个 claimed 状态工单")
assert_true(completed_count >= 1, "至少有 1 个 completed 状态工单")

print("\n--- 2.3 工单详情数据完整 ---")
if work_orders:
    wo = work_orders[0]
    detail, s = http_get_json(f"/inspection-work-orders/{wo['id']}")
    assert_eq(s, 200, "获取工单详情成功")
    assert_true("items" in detail, "包含巡检项")
    assert_true("logs" in detail, "包含操作日志")
    assert_true("associated_alarms" in detail, "包含关联报警")

# ========== TEST 3: 工单状态持久化 ==========
print()
print("=" * 70)
print("TEST 3: 工单状态持久化")
print("=" * 70)

print("\n--- 3.1 已完成工单状态保持 completed ---")
completed_wo = [w for w in work_orders if w["status"] == "completed"]
if completed_wo:
    wo = completed_wo[0]
    detail, _ = http_get_json(f"/inspection-work-orders/{wo['id']}")
    assert_eq(detail["status"], "completed", "状态仍为 completed")
    assert_true(detail["completed_by"] is not None, "completed_by 存在")
    assert_true(detail["completed_at"] is not None, "completed_at 存在")
    assert_true(detail["completer_name"] is not None, "completer_name 存在")

print("\n--- 3.2 已领取工单状态保持 claimed ---")
claimed_wo = [w for w in work_orders if w["status"] == "claimed"]
if claimed_wo:
    wo = claimed_wo[0]
    detail, _ = http_get_json(f"/inspection-work-orders/{wo['id']}")
    assert_eq(detail["status"], "claimed", "状态仍为 claimed")
    assert_true(detail["claimed_by"] is not None, "claimed_by 存在")
    assert_true(detail["claimed_at"] is not None, "claimed_at 存在")
    assert_true(detail["claimer_name"] is not None, "claimer_name 存在")

# ========== TEST 4: 巡检项数据持久化 ==========
print()
print("=" * 70)
print("TEST 4: 巡检项数据持久化")
print("=" * 70)

print("\n--- 4.1 已检查的巡检项数据完整 ---")
if claimed_wo:
    wo = claimed_wo[0]
    detail, _ = http_get_json(f"/inspection-work-orders/{wo['id']}")
    items = detail["items"]
    checked_items = [i for i in items if i["check_status"] != "pending"]
    assert_true(len(checked_items) >= 1, "至少有 1 个已检查的巡检项")
    
    for item in checked_items:
        assert_true(item["checked_by"] is not None, f"巡检项{item['id']} checked_by 存在")
        assert_true(item["checked_at"] is not None, f"巡检项{item['id']} checked_at 存在")
        assert_true(item["checked_by_name"] is not None, f"巡检项{item['id']} checked_by_name 存在")

print("\n--- 4.2 异常巡检项有异常处理数据 ---")
abnormal_items = []
if claimed_wo:
    wo = claimed_wo[0]
    detail, _ = http_get_json(f"/inspection-work-orders/{wo['id']}")
    abnormal_items = [i for i in detail["items"] if i["check_status"] == "abnormal"]

if abnormal_items:
    item = abnormal_items[0]
    assert_true(item["exception_action"] is not None, "异常项有 exception_action")
    assert_true(item["handler_id"] is not None, "异常项有 handler_id")
    assert_true(item["handler_name"] is not None, "异常项有 handler_name")

# ========== TEST 5: 操作日志持久化 ==========
print()
print("=" * 70)
print("TEST 5: 操作日志持久化")
print("=" * 70)

print("\n--- 5.1 工单有操作日志 ---")
if work_orders:
    wo = work_orders[0]
    detail, _ = http_get_json(f"/inspection-work-orders/{wo['id']}")
    logs = detail["logs"]
    assert_true(len(logs) >= 1, f"至少有 1 条操作日志 (实际{len(logs)}条)")
    
    for log in logs:
        assert_true("action" in log, "日志包含 action")
        assert_true("operator_name" in log, "日志包含 operator_name")
        assert_true("created_at" in log, "日志包含 created_at")

# ========== TEST 6: 逾期状态计算正确 ==========
print()
print("=" * 70)
print("TEST 6: 逾期状态计算正确")
print("=" * 70)

print("\n--- 6.1 按逾期状态筛选有效 ---")
overdue_wo, s = http_get_json("/inspection-work-orders?is_overdue=true")
assert_eq(s, 200, "按逾期筛选成功")
print(f"  逾期工单数量: {len(overdue_wo)}")

not_overdue_wo, s = http_get_json("/inspection-work-orders?is_overdue=false")
assert_eq(s, 200, "按未逾期筛选成功")
print(f"  未逾期工单数量: {len(not_overdue_wo)}")

print("\n--- 6.2 已完成工单不标记为逾期 ---")
completed_overdue = [w for w in work_orders if w["status"] == "completed" and w.get("is_overdue")]
assert_eq(len(completed_overdue), 0, "已完成工单都不逾期")

# ========== TEST 7: 报警关联持久化 ==========
print()
print("=" * 70)
print("TEST 7: 报警关联数据验证")
print("=" * 70)

print("\n--- 7.1 工单列表显示 alarm_count ---")
for wo in work_orders:
    assert_true("alarm_count" in wo, f"工单{wo['id']} 包含 alarm_count")

print("\n--- 7.2 工单详情包含关联报警列表 ---")
if work_orders:
    wo = work_orders[0]
    detail, _ = http_get_json(f"/inspection-work-orders/{wo['id']}")
    assert_true("associated_alarms" in detail, "详情包含 associated_alarms")
    alarms = detail["associated_alarms"]
    if alarms:
        alarm = alarms[0]
        assert_true("alarm_snapshot" in alarm, "包含报警快照")
        assert_true("associator_name" in alarm, "包含关联人名称")

# ========== TEST 8: 列表/导出一致性（重启后） ==========
print()
print("=" * 70)
print("TEST 8: 列表/导出数据一致性（重启后验证）")
print("=" * 70)

print("\n--- 8.1 JSON 导出与列表 API 一致 ---")
json_text, s_json = http_get("/inspection-work-orders/export.json")
assert_eq(s_json, 200, "JSON 导出成功")
json_data = json.loads(json_text)

api_list, s_api = http_get_json("/inspection-work-orders")
assert_eq(s_api, 200, "列表 API 成功")

assert_eq(len(json_data), len(api_list), "JSON 导出条数 = 列表 API 条数")

for api_item in api_list:
    export_item = next((e for e in json_data if e["id"] == api_item["id"]), None)
    assert_true(export_item is not None, f"JSON导出中找到工单{api_item['id']}")
    if export_item:
        assert_eq(export_item["status"], api_item["status"],
                  f"工单{api_item['id']} status 一致")
        assert_eq(export_item["pending_count"], api_item["pending_count"],
                  f"工单{api_item['id']} pending_count 一致")
        assert_eq(export_item["abnormal_count"], api_item["abnormal_count"],
                  f"工单{api_item['id']} abnormal_count 一致")
        assert_eq(export_item["alarm_count"], api_item["alarm_count"],
                  f"工单{api_item['id']} alarm_count 一致")

print("\n--- 8.2 CSV 导出与列表 API 一致 ---")
csv_text, s_csv = http_get("/inspection-work-orders/export.csv")
assert_eq(s_csv, 200, "CSV 导出成功")
csv_reader = csv.reader(io.StringIO(csv_text))
csv_rows = list(csv_reader)
csv_header = csv_rows[0]

assert_eq(len(csv_rows) - 1, len(api_list), "CSV 数据行数 = API 返回工单数")

for row in csv_rows[1:]:
    row_id = int(row[csv_header.index("id")])
    api_wo = next((w for w in api_list if w["id"] == row_id), None)
    assert_true(api_wo is not None, f"CSV中找到工单{row_id}")
    if api_wo:
        csv_status = row[csv_header.index("status")]
        assert_eq(csv_status, api_wo["status"], f"CSV工单{row_id} status 一致")

print("\n--- 8.3 详情导出与详情 API 一致 ---")
if work_orders:
    wo_id = work_orders[0]["id"]
    detail_api, _ = http_get_json(f"/inspection-work-orders/{wo_id}")
    
    export_text, _ = http_get(f"/inspection-work-orders/{wo_id}/export.json")
    export_detail = json.loads(export_text)
    
    assert_eq(export_detail["id"], detail_api["id"], "详情导出 id 一致")
    assert_eq(export_detail["status"], detail_api["status"], "详情导出 status 一致")
    assert_eq(len(export_detail["items"]), len(detail_api["items"]), "详情导出 items 数量一致")

# ========== TEST 9: 权限验证（重启后仍然有效） ==========
print()
print("=" * 70)
print("TEST 9: 权限验证（重启后仍然有效）")
print("=" * 70)

print("\n--- 9.1 observer 不能创建模板 (403) ---")
r, s = http_post("/inspection-templates", {
    "name": "重启测试模板",
    "zone_id": z_a["id"],
    "shift_type": "afternoon",
    "deadline_hours": 4.0,
    "created_by": p_obs["id"],
    "checkpoints": [{"name": "测试", "sort_order": 1}]
})
assert_eq(s, 403, "observer 创建模板返回 403")

print("\n--- 9.2 observer 不能生成工单 (403) ---")
active_t = [t for t in templates if t["status"] == "active"][0]
r, s = http_post("/inspection-work-orders/generate", {
    "template_id": active_t["id"],
    "work_date": "2099-12-31",
    "created_by": p_obs["id"],
})
assert_eq(s, 403, "observer 生成工单返回 403")

# ========== 总结 ==========
print()
print("=" * 70)
print(f"跨服务重启数据一致性验证汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 所有跨重启验证通过！数据持久化正常。")
else:
    print(f"\n[FAIL] 有 {FAIL} 个验证失败。")
    exit(1)
