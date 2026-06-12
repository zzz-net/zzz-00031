"""
报警静音计划（抑制规则）全面回归测试
覆盖：
1. 权限验证（admin/operator可操作，observer只能查看）
2. 时间冲突检测（同一范围不能重叠）
3. 撤销恢复（撤销后新异常产生open报警）
4. 导入触发一致性（JSON/CSV/直接导入走同一套命中逻辑）
5. 命中日志审计（可追溯：关联计划、触发读数、时间、原因）
6. CSV导出一致性（报警/静音计划/命中记录对得上）
7. 读数正常入库（静音窗口内读数仍写入数据库）
"""
import json
import urllib.request
import urllib.error
import io
import csv
import os

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


def http_post_file(path, file_path, field_name="file"):
    boundary = "----TestBoundaryFullReg98765"
    with open(file_path, "rb") as f:
        file_content = f.read()

    filename = os.path.basename(file_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n"
        f"\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
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


def create_test_files(prefix="regression"):
    json_data = [
        {"sensor_code": "TEMP-002", "temperature": -15.0, "reading_time": "2099-03-15T10:00:00"},
        {"sensor_code": "TEMP-002", "temperature": -14.0, "reading_time": "2099-03-15T10:30:00"},
    ]
    json_path = f"test_{prefix}_import.json"
    with open(json_path, "w") as f:
        json.dump(json_data, f)

    csv_path = f"test_{prefix}_import.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sensor_code", "temperature", "reading_time"])
        writer.writerow(["TEMP-002", "-15.0", "2099-03-15T10:00:00"])
        writer.writerow(["TEMP-002", "-14.0", "2099-03-15T10:30:00"])

    return json_path, csv_path


def cleanup_test_files(paths):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)


# ========== 初始化 ==========
print("=" * 70)
print("报警静音计划全面回归测试")
print("=" * 70)

print("\n--- 初始化：获取基础数据 ---")
persons, _ = http_get_json("/persons")
sensors, _ = http_get_json("/sensors")
zones, _ = http_get_json("/zones")

p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]

s1 = [s for s in sensors if s["code"] == "TEMP-001"][0]
s2 = [s for s in sensors if s["code"] == "TEMP-002"][0]
s3 = [s for s in sensors if s["code"] == "TEMP-003"][0]

z_a = [z for z in zones if z["name"] == "冷冻库区A"][0]

print(f"  admin={p_admin['id']}, operator={p_op['id']}, observer={p_obs['id']}")
print(f"  TEMP-001={s1['id']}, TEMP-002={s2['id']}, TEMP-003={s3['id']}")
print(f"  冷冻库区A={z_a['id']}")

# 准备测试文件
json_file, csv_file = create_test_files("suppr_regression")

# ========== TEST 1: 权限验证 ==========
print()
print("=" * 70)
print("TEST 1: 权限验证")
print("=" * 70)

print("\n--- 1.1 observer 不能创建静音计划 (403) ---")
r, s = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2099-01-10T00:00:00",
    "end_time": "2099-01-10T23:59:59",
    "reason": "observer非法创建",
    "created_by": p_obs["id"]
})
assert_eq(s, 403, "observer 创建返回 403")
assert_contains(r.get("detail", ""), "Permission denied", "错误信息包含 Permission denied")

print("\n--- 1.2 observer 不能撤销静音计划 (403) ---")
r_op_create, s_op_create = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2099-01-11T00:00:00",
    "end_time": "2099-01-11T23:59:59",
    "reason": "operator创建用于测试撤销权限",
    "created_by": p_op["id"]
})
assert_eq(s_op_create, 200, "operator 创建成功")
test_revoke_perm_id = r_op_create["id"]

r_revoke, s_revoke = http_post(f"/suppression-rules/{test_revoke_perm_id}/revoke",
                               {"person_id": p_obs["id"]})
assert_eq(s_revoke, 403, "observer 撤销返回 403")

print("\n--- 1.3 observer 可以查看（列表和详情） ---")
rules_list, s_list = http_get_json("/suppression-rules")
assert_eq(s_list, 200, "observer 查看列表成功 (200)")
assert_true(len(rules_list) >= 1, "列表至少有 1 条规则")

rule_detail, s_detail = http_get_json(f"/suppression-rules/{test_revoke_perm_id}")
assert_eq(s_detail, 200, "observer 查看详情成功 (200)")
assert_eq(rule_detail["id"], test_revoke_perm_id, "详情 ID 正确")

hits_list, s_hits = http_get_json(f"/suppression-rules/{test_revoke_perm_id}/hits")
assert_eq(s_hits, 200, "observer 查看命中日志成功 (200)")

print("\n--- 1.4 operator 可以创建和撤销 ---")
r2, s2_status = http_post("/suppression-rules", {
    "sensor_id": s3["id"],
    "start_time": "2099-01-12T00:00:00",
    "end_time": "2099-01-12T23:59:59",
    "reason": "operator创建测试",
    "created_by": p_op["id"]
})
assert_eq(s2_status, 200, "operator 创建成功")
assert_eq(r2["status"], "active", "规则状态为 active")

r_rev, s_rev = http_post(f"/suppression-rules/{r2['id']}/revoke", {"person_id": p_op["id"]})
assert_eq(s_rev, 200, "operator 撤销成功")
assert_eq(r_rev["status"], "revoked", "撤销后状态为 revoked")

print("\n--- 1.5 admin 可以创建和撤销 ---")
r3, s3_status = http_post("/suppression-rules", {
    "sensor_id": s3["id"],
    "start_time": "2099-01-13T00:00:00",
    "end_time": "2099-01-13T23:59:59",
    "reason": "admin创建测试",
    "created_by": p_admin["id"]
})
assert_eq(s3_status, 200, "admin 创建成功")

r_rev3, s_rev3 = http_post(f"/suppression-rules/{r3['id']}/revoke", {"person_id": p_admin["id"]})
assert_eq(s_rev3, 200, "admin 撤销成功")

# ========== TEST 2: 时间冲突检测 ==========
print()
print("=" * 70)
print("TEST 2: 时间冲突检测")
print("=" * 70)

print("\n--- 2.1 结束时间早于开始时间 (400) ---")
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-02-01T12:00:00",
    "end_time": "2099-02-01T10:00:00",
    "reason": "时间错误测试",
    "created_by": p_admin["id"]
})
assert_eq(s, 400, "结束早于开始返回 400")
assert_contains(r.get("detail", ""), "End time must be after start time", "错误信息正确")

print("\n--- 2.2 缺少 sensor_id 和 zone_id (400) ---")
r, s = http_post("/suppression-rules", {
    "start_time": "2099-02-02T00:00:00",
    "end_time": "2099-02-02T23:59:59",
    "reason": "缺少范围测试",
    "created_by": p_admin["id"]
})
assert_eq(s, 400, "缺少范围返回 400")
assert_contains(r.get("detail", ""), "Either sensor_id or zone_id must be provided", "错误信息正确")

print("\n--- 2.3 完全重叠的时间窗口 (409) ---")
# 先创建一个 active 规则
r_active, s_active = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-02-10T00:00:00",
    "end_time": "2099-02-10T23:59:59",
    "reason": "冲突测试-基准",
    "created_by": p_admin["id"]
})
assert_eq(s_active, 200, "创建基准规则成功")
conflict_base_id = r_active["id"]

# 再创建完全重叠的
r_conflict, s_conflict = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-02-10T00:00:00",
    "end_time": "2099-02-10T23:59:59",
    "reason": "冲突测试-完全重叠",
    "created_by": p_admin["id"]
})
assert_eq(s_conflict, 409, "完全重叠返回 409")
assert_contains(r_conflict.get("detail", ""), "Conflict", "错误信息包含 Conflict")

print("\n--- 2.4 部分重叠的时间窗口 (409) ---")
r_partial, s_partial = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-02-10T12:00:00",
    "end_time": "2099-02-11T12:00:00",
    "reason": "冲突测试-部分重叠",
    "created_by": p_admin["id"]
})
assert_eq(s_partial, 409, "部分重叠返回 409")

print("\n--- 2.5 包含关系的时间窗口 (409) ---")
r_include, s_include = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-02-09T00:00:00",
    "end_time": "2099-02-11T23:59:59",
    "reason": "冲突测试-包含",
    "created_by": p_admin["id"]
})
assert_eq(s_include, 409, "包含关系返回 409")

print("\n--- 2.6 revoked 规则不参与冲突检测 ---")
# 撤销基准规则
http_post(f"/suppression-rules/{conflict_base_id}/revoke", {"person_id": p_admin["id"]})

# 再创建相同时间的规则，应该成功（因为基准已 revoked）
r_after_revoke, s_after_revoke = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-02-10T00:00:00",
    "end_time": "2099-02-10T23:59:59",
    "reason": "撤销后重新创建",
    "created_by": p_admin["id"]
})
assert_eq(s_after_revoke, 200, "撤销后同时间可创建新规则")

# ========== TEST 3: 按传感器静音 + 读数正常入库 ==========
print()
print("=" * 70)
print("TEST 3: 按传感器静音 + 读数正常入库")
print("=" * 70)

# 创建静音计划
r_rule, s_rule = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "alarm_type": "over_temp",
    "start_time": "2099-03-01T00:00:00",
    "end_time": "2099-03-01T23:59:59",
    "reason": "传感器校准检修",
    "created_by": p_op["id"]
})
assert_eq(s_rule, 200, "创建按传感器静音计划成功")
sensor_rule_id = r_rule["id"]
print(f"  静音计划 ID: {sensor_rule_id}")

# 先导入一个正常读数作为基准（避免 offline 干扰）
http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -25.0, "reading_time": "2099-03-01T09:50:00"}
])

# 导入超温读数（在静音窗口内）
r_import, s_import = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -15.0, "reading_time": "2099-03-01T10:00:00"}
])
print(f"  导入结果: successful={r_import['successful']}, new_alarms={r_import['new_alarms']}, "
      f"suppressed={r_import.get('suppressed_alarms')}")
assert_eq(r_import["successful"], 1, "读数成功导入")
assert_true(r_import.get("suppressed_alarms", 0) >= 1, "至少 1 个报警被静音")

print("\n--- 3.1 读数正常入库 ---")
readings, _ = http_get_json(f"/readings?sensor_id={s2['id']}&limit=20")
target_readings = [r for r in readings if "2099-03-01T10:00:00" in r["reading_time"]]
assert_eq(len(target_readings), 1, "静音窗口内读数正常入库")
assert_eq(target_readings[0]["temperature"], -15.0, "读数温度值正确")

print("\n--- 3.2 报警状态为 suppressed 且关联静音计划 ---")
alarms, _ = http_get_json(f"/alarms?sensor_id={s2['id']}")
suppressed_alarms = [
    a for a in alarms
    if a["alarm_type"] == "over_temp"
    and a["status"] == "suppressed"
    and a.get("suppression_rule_id") == sensor_rule_id
    and "2099-03-01" in str(a.get("trigger_time", ""))
]
assert_true(len(suppressed_alarms) >= 1, "有 suppressed 状态的 over_temp 报警")
if suppressed_alarms:
    alarm = suppressed_alarms[0]
    assert_eq(alarm["suppression_rule_id"], sensor_rule_id, "关联正确的静音计划 ID")
    assert_eq(alarm["suppression_rule_reason"], "传感器校准检修", "静音原因正确")
    assert_eq(alarm["trigger_value"], -15.0, "触发值正确")

# ========== TEST 4: 按库区静音 ==========
print()
print("=" * 70)
print("TEST 4: 按库区静音（覆盖库区所有传感器）")
print("=" * 70)

# 创建库区静音计划
r_zone_rule, s_zone = http_post("/suppression-rules", {
    "zone_id": z_a["id"],
    "start_time": "2099-04-01T00:00:00",
    "end_time": "2099-04-01T23:59:59",
    "reason": "库区A设备巡检",
    "created_by": p_admin["id"]
})
assert_eq(s_zone, 200, "创建库区静音计划成功")
zone_rule_id = r_zone_rule["id"]

# 先导入基准读数
http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -20.0, "reading_time": "2099-04-01T09:50:00"},
])

# 导入 TEMP-001 超温（在库区A内）
r_over, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2099-04-01T10:00:00"}
])
assert_true(r_over.get("suppressed_alarms", 0) >= 1, "库区A传感器超温被静音")

# 导入 TEMP-001 低温（在库区A内）
r_under, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -28.0, "reading_time": "2099-04-01T10:30:00"}
])
assert_true(r_under.get("suppressed_alarms", 0) >= 1, "库区A传感器低温被静音")

# 验证：两种报警都关联库区静音计划
alarms, _ = http_get_json(f"/alarms?sensor_id={s1['id']}")
zone_suppressed = [
    a for a in alarms
    if a.get("suppression_rule_id") == zone_rule_id
    and "2099-04-01" in str(a.get("trigger_time", ""))
]
print(f"  关联库区静音计划的报警: {len(zone_suppressed)} 个")
assert_true(any(a["alarm_type"] == "over_temp" for a in zone_suppressed), "有 over_temp 被库区规则静音")
assert_true(any(a["alarm_type"] == "under_temp" for a in zone_suppressed), "有 under_temp 被库区规则静音")

# ========== TEST 5: 撤销静音后恢复 open 报警 ==========
print()
print("=" * 70)
print("TEST 5: 撤销静音计划后恢复触发 open 报警")
print("=" * 70)

# 用 TEMP-003 测试
r_test_rule, s_test = http_post("/suppression-rules", {
    "sensor_id": s3["id"],
    "start_time": "2099-05-01T00:00:00",
    "end_time": "2099-05-01T23:59:59",
    "reason": "临时静音测试",
    "created_by": p_op["id"]
})
assert_eq(s_test, 200, "创建测试静音计划成功")
revoke_test_rule_id = r_test_rule["id"]

# 先导入基准
http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 2.0, "reading_time": "2099-05-01T09:50:00"}
])

# 导入超温（静音中）
r_before, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 10.0, "reading_time": "2099-05-01T10:00:00"}
])
print(f"  撤销前: suppressed_alarms={r_before.get('suppressed_alarms')}")
assert_eq(r_before.get("suppressed_alarms", 0), 1, "撤销前报警被静音")

# 撤销静音计划
r_revoke, s_revoke = http_post(
    f"/suppression-rules/{revoke_test_rule_id}/revoke",
    {"person_id": p_op["id"]}
)
assert_eq(s_revoke, 200, "撤销静音计划成功")
assert_eq(r_revoke["status"], "revoked", "规则状态变为 revoked")

# 先导入基准（距离后面的读数10分钟，避免offline）
http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 2.0, "reading_time": "2099-05-01T13:50:00"}
])

# 再导入超温（规则已撤销，应产生 open 报警）
r_after, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 9.0, "reading_time": "2099-05-01T14:00:00"}
])
print(f"  撤销后: new_alarms={r_after['new_alarms']}, suppressed_alarms={r_after.get('suppressed_alarms')}")
assert_eq(r_after.get("suppressed_alarms", 0), 0, "撤销后无被静音的报警")
assert_true(r_after["new_alarms"] >= 1, "撤销后产生新报警")

# 验证有 open 状态的报警
alarms, _ = http_get_json(f"/alarms?sensor_id={s3['id']}")
open_after_revoke = [
    a for a in alarms
    if a["status"] == "open"
    and a["alarm_type"] == "over_temp"
    and "2099-05-01T14:00:00" in str(a.get("trigger_time", ""))
]
assert_true(len(open_after_revoke) >= 1, "撤销后有 open 状态的超温报警")

# ========== TEST 6: 命中日志审计 ==========
print()
print("=" * 70)
print("TEST 6: 静音命中日志（可追溯）")
print("=" * 70)

# 查询静音计划的命中日志
hits, s_hits = http_get_json(f"/suppression-rules/{sensor_rule_id}/hits")
print(f"  规则 {sensor_rule_id} 命中数: {len(hits)}")
assert_eq(s_hits, 200, "获取命中日志成功")
assert_true(len(hits) >= 1, "至少有 1 条命中记录")

print("\n--- 6.1 命中日志包含必要信息 ---")
if hits:
    hit = hits[0]
    assert_eq(hit["rule_id"], sensor_rule_id, "命中日志关联正确的规则 ID")
    assert_true("alarm_id" in hit and hit["alarm_id"] is not None, "命中日志有 alarm_id")
    assert_true("alarm_type" in hit, "命中日志有 alarm_type")
    assert_true("trigger_value" in hit, "命中日志有 trigger_value")
    assert_true("trigger_time" in hit, "命中日志有 trigger_time")
    assert_true("sensor_code" in hit, "命中日志有 sensor_code")
    print(f"    命中: id={hit['id']}, alarm_type={hit['alarm_type']}, "
          f"trigger_value={hit['trigger_value']}, trigger_time={hit['trigger_time']}")

print("\n--- 6.2 规则详情 hit_count 与实际命中数一致 ---")
rule_detail, _ = http_get_json(f"/suppression-rules/{sensor_rule_id}")
assert_eq(rule_detail["hit_count"], len(hits), "规则详情 hit_count 与命中日志数一致")

print("\n--- 6.3 命中日志与报警可互查 ---")
# 从报警找命中
suppressed_alarms_list, _ = http_get_json("/alarms?status=suppressed")
assert_true(len(suppressed_alarms_list) >= 1, "至少有 1 个 suppressed 报警")

# 验证每个 suppressed 报警都有对应的命中记录
for alarm in suppressed_alarms_list[:3]:
    if alarm.get("suppression_rule_id"):
        rule_hits, _ = http_get_json(f"/suppression-rules/{alarm['suppression_rule_id']}/hits")
        matching_hits = [h for h in rule_hits if h["alarm_id"] == alarm["id"]]
        assert_true(len(matching_hits) >= 1,
                    f"报警 {alarm['id']} 能在命中日志中找到对应记录")

# ========== TEST 7: 导入触发一致性（JSON/CSV/直接提交） ==========
print()
print("=" * 70)
print("TEST 7: 三种导入方式走同一套命中逻辑")
print("=" * 70)

# 用 TEMP-002 的一个新时间窗口
r_test_import, s_test_import = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2099-06-01T00:00:00",
    "end_time": "2099-06-03T23:59:59",
    "reason": "导入一致性测试",
    "created_by": p_admin["id"]
})
assert_eq(s_test_import, 200, "创建测试静音计划成功")
import_test_rule_id = r_test_import["id"]

# 方式1：直接提交
r_direct, s_direct = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -25.0, "reading_time": "2099-06-01T08:00:00"},
    {"sensor_code": "TEMP-002", "temperature": -12.0, "reading_time": "2099-06-01T09:00:00"}
])
print(f"  直接提交: total={r_direct['total']}, successful={r_direct['successful']}, "
      f"failed={r_direct['failed']}, suppressed_alarms={r_direct.get('suppressed_alarms')}")
assert_true("suppressed_alarms" in r_direct, "直接提交结果有 suppressed_alarms 字段")
assert_eq(r_direct["total"], r_direct["successful"] + r_direct["failed"], "total = successful + failed")
assert_eq(len(r_direct["errors"]), r_direct["failed"], "errors 长度 = failed 数")

# 方式2：JSON 文件导入
# 先创建测试文件
json_data = [
    {"sensor_code": "TEMP-001", "temperature": -20.0, "reading_time": "2099-06-02T08:00:00"},
    {"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2099-06-02T09:00:00"},
]
test_json_path = "test_regression_import.json"
with open(test_json_path, "w") as f:
    json.dump(json_data, f)

r_json, s_json = http_post_file("/readings/import-json", test_json_path)
print(f"  JSON文件导入: total={r_json['total']}, successful={r_json['successful']}, "
      f"failed={r_json['failed']}, suppressed_alarms={r_json.get('suppressed_alarms')}")
assert_true("suppressed_alarms" in r_json, "JSON导入结果有 suppressed_alarms 字段")
assert_eq(r_json["total"], r_json["successful"] + r_json["failed"], "JSON: total = successful + failed")
assert_eq(len(r_json["errors"]), r_json["failed"], "JSON: errors 长度 = failed 数")

# 方式3：CSV 文件导入
test_csv_path = "test_regression_import.csv"
with open(test_csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["sensor_code", "temperature", "reading_time"])
    writer.writerow(["TEMP-002", "-25.0", "2099-06-03T08:00:00"])
    writer.writerow(["TEMP-002", "-11.0", "2099-06-03T09:00:00"])

r_csv, s_csv = http_post_file("/readings/import-csv", test_csv_path)
print(f"  CSV文件导入: total={r_csv['total']}, successful={r_csv['successful']}, "
      f"failed={r_csv['failed']}, suppressed_alarms={r_csv.get('suppressed_alarms')}")
assert_true("suppressed_alarms" in r_csv, "CSV导入结果有 suppressed_alarms 字段")
assert_eq(r_csv["total"], r_csv["successful"] + r_csv["failed"], "CSV: total = successful + failed")
assert_eq(len(r_csv["errors"]), r_csv["failed"], "CSV: errors 长度 = failed 数")

# 清理测试文件
os.remove(test_json_path)
os.remove(test_csv_path)

# ========== TEST 8: CSV 导出一致性 ==========
print()
print("=" * 70)
print("TEST 8: CSV 导出一致性（报警/静音计划/命中记录对得上）")
print("=" * 70)

print("\n--- 8.1 静音计划 CSV 导出 ---")
csv_rules_text, s_rules_csv = http_get("/suppression-rules/export.csv")
assert_eq(s_rules_csv, 200, "静音计划 CSV 导出成功")
rules_reader = csv.reader(io.StringIO(csv_rules_text))
rules_rows = list(rules_reader)
print(f"  静音计划 CSV: {len(rules_rows)} 行（含表头）")
assert_true(len(rules_rows) >= 2, "至少有表头 + 1 行数据")

rules_header = rules_rows[0]
assert_true("id" in rules_header, "CSV 包含 id 列")
assert_true("reason" in rules_header, "CSV 包含 reason 列")
assert_true("status" in rules_header, "CSV 包含 status 列")
assert_true("hit_count" in rules_header, "CSV 包含 hit_count 列")
assert_true("created_by" in rules_header, "CSV 包含 created_by 列")

# 验证 CSV 中的规则数与 API 查询一致
api_rules, _ = http_get_json("/suppression-rules")
assert_eq(len(rules_rows) - 1, len(api_rules), "CSV 数据行数 = API 返回规则数")

print("\n--- 8.2 命中日志 CSV 导出 ---")
csv_hits_text, s_hits_csv = http_get("/suppression-hits/export.csv")
assert_eq(s_hits_csv, 200, "命中日志 CSV 导出成功")
hits_reader = csv.reader(io.StringIO(csv_hits_text))
hits_rows = list(hits_reader)
print(f"  命中日志 CSV: {len(hits_rows)} 行（含表头）")
assert_true(len(hits_rows) >= 2, "至少有表头 + 1 行数据")

hits_header = hits_rows[0]
assert_true("rule_id" in hits_header, "CSV 包含 rule_id 列")
assert_true("alarm_id" in hits_header, "CSV 包含 alarm_id 列")
assert_true("trigger_value" in hits_header, "CSV 包含 trigger_value 列")
assert_true("trigger_time" in hits_header, "CSV 包含 trigger_time 列")

print("\n--- 8.3 报警 CSV 导出包含静音信息 ---")
csv_alarms_text, s_alarms_csv = http_get("/alarms/export.csv")
assert_eq(s_alarms_csv, 200, "报警 CSV 导出成功")
alarms_reader = csv.reader(io.StringIO(csv_alarms_text))
alarms_rows = list(alarms_reader)
alarms_header = alarms_rows[0]
assert_true("suppression_rule_id" in alarms_header, "报警 CSV 包含 suppression_rule_id")
assert_true("suppression_rule_reason" in alarms_header, "报警 CSV 包含 suppression_rule_reason")

print("\n--- 8.4 三方数据对得上 ---")
# 收集所有 suppressed 报警的 suppression_rule_id
csv_suppressed_rule_ids = set()
for row in alarms_rows[1:]:
    if len(row) > 6 and row[6]:  # suppression_rule_id 列
        try:
            csv_suppressed_rule_ids.add(int(row[6]))
        except (ValueError, IndexError):
            pass

# 收集静音计划 CSV 中的规则 ID
csv_rule_ids = set()
for row in rules_rows[1:]:
    if row and row[0]:
        try:
            csv_rule_ids.add(int(row[0]))
        except ValueError:
            pass

# 验证：报警中引用的规则 ID 都存在于规则 CSV 中
assert_true(csv_suppressed_rule_ids.issubset(csv_rule_ids),
            "报警 CSV 中引用的 suppression_rule_id 都能在规则 CSV 中找到")

# 收集命中日志中的 rule_id
csv_hit_rule_ids = set()
for row in hits_rows[1:]:
    if len(row) > 1 and row[1]:
        try:
            csv_hit_rule_ids.add(int(row[1]))
        except (ValueError, IndexError):
            pass

# 验证：命中日志中的 rule_id 都存在于规则 CSV 中
assert_true(csv_hit_rule_ids.issubset(csv_rule_ids),
            "命中日志 CSV 中的 rule_id 都能在规则 CSV 中找到")

# 验证：命中日志中的 alarm_id 都存在于报警 CSV 中
csv_alarm_ids = set()
for row in alarms_rows[1:]:
    if row and row[0]:
        try:
            csv_alarm_ids.add(int(row[0]))
        except ValueError:
            pass

csv_hit_alarm_ids = set()
for row in hits_rows[1:]:
    if len(row) > 2 and row[2]:
        try:
            csv_hit_alarm_ids.add(int(row[2]))
        except (ValueError, IndexError):
            pass

assert_true(csv_hit_alarm_ids.issubset(csv_alarm_ids),
            "命中日志 CSV 中的 alarm_id 都能在报警 CSV 中找到")

# ========== TEST 9: 到期自动恢复 ==========
print()
print("=" * 70)
print("TEST 9: 静音窗口到期后自动恢复")
print("=" * 70)

# 创建一个短窗口的静音计划
r_short, s_short = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2099-07-01T08:00:00",
    "end_time": "2099-07-01T09:00:00",
    "reason": "短时静音测试",
    "created_by": p_op["id"]
})
assert_eq(s_short, 200, "创建短时静音计划成功")
short_rule_id = r_short["id"]

# 窗口内导入 - 应被静音
http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -25.0, "reading_time": "2099-07-01T07:00:00"}
])
r_in, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -10.0, "reading_time": "2099-07-01T08:30:00"}
])
assert_true(r_in.get("suppressed_alarms", 0) >= 1, "窗口内报警被静音")

# 窗口外导入 - 不应被静音
r_out, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -9.0, "reading_time": "2099-07-01T10:00:00"}
])
print(f"  窗口内: suppressed={r_in.get('suppressed_alarms')}, "
      f"窗口外: suppressed={r_out.get('suppressed_alarms')}")

# 检查窗口外的报警状态
alarms, _ = http_get_json(f"/alarms?sensor_id={s2['id']}")
jul1_overtemps = [
    a for a in alarms
    if a["alarm_type"] == "over_temp"
    and "2099-07-01" in str(a.get("trigger_time", ""))
]
suppressed_count = sum(1 for a in jul1_overtemps if a["status"] == "suppressed")
open_count = sum(1 for a in jul1_overtemps if a["status"] == "open")
print(f"  7月1日 over_temp: suppressed={suppressed_count}, open={open_count}")
assert_true(suppressed_count >= 1, "窗口内至少 1 个 suppressed 报警")
assert_true(open_count >= 1, "窗口外至少 1 个 open 报警（到期恢复）")

# ========== TEST 10: 旧手工抑制端点已移除 ==========
print()
print("=" * 70)
print("TEST 10: 旧手工抑制端点已移除（安全回归）")
print("=" * 70)

# 先找一个 open 报警
open_alarms = [
    a for a in alarms if a["status"] == "open" and a["sensor_id"] == s2["id"]
]
assert_true(len(open_alarms) >= 1, "有 open 状态报警用于测试")
test_alarm_id = open_alarms[0]["id"]

# 尝试调用旧端点
r_old, s_old = http_post(f"/alarms/{test_alarm_id}/suppress", {
    "person_id": p_admin["id"],
    "note": "尝试旧抑制",
    "suppress_minutes": 60
})
print(f"  旧端点返回: status={s_old}")
assert_true(s_old in [404, 405, 400], f"旧端点返回错误状态码: {s_old}")

# 验证报警状态未被改变
alarms_after, _ = http_get_json(f"/alarms/{test_alarm_id}")
assert_eq(alarms_after["status"], "open", "旧端点调用后报警仍为 open")
assert_true(alarms_after.get("suppression_rule_id") is None,
            "旧端点调用后 suppression_rule_id 仍为空")

# ========== 总结 ==========
print()
print("=" * 70)
print(f"全面回归测试汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

# 清理
cleanup_test_files([json_file, csv_file])

if FAIL == 0:
    print("\n[OK] 所有静音计划回归测试通过！")
    print("\n提示：可以重启服务后运行 test_restart_consistency.py 验证跨重启一致性。")
else:
    print(f"\n[FAIL] 有 {FAIL} 个测试失败。")
    exit(1)
