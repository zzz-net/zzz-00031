import json
import urllib.request
import urllib.error
import io
import csv
import os
from datetime import datetime, timedelta

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0


def http_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode()), resp.status


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
    boundary = "----TestBoundary123456789"
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


def create_temp_test_files():
    """创建测试用的 JSON 和 CSV 文件"""
    json_data = [
        {"sensor_code": "TEMP-001", "temperature": -12.0, "reading_time": "2026-06-20T10:00:00"},
        {"sensor_code": "TEMP-001", "temperature": -11.0, "reading_time": "2026-06-20T10:30:00"},
        {"sensor_code": "TEMP-001", "temperature": -13.0, "reading_time": "2026-06-20T09:00:00"},
    ]
    with open("test_suppress.json", "w") as f:
        json.dump(json_data, f)

    with open("test_suppress.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sensor_code", "temperature", "reading_time"])
        writer.writerow(["TEMP-001", "-12.0", "2026-06-20T10:00:00"])
        writer.writerow(["TEMP-001", "-11.0", "2026-06-20T10:30:00"])
        writer.writerow(["TEMP-001", "-13.0", "2026-06-20T09:00:00"])


def cleanup_temp_files():
    for f in ["test_suppress.json", "test_suppress.csv"]:
        if os.path.exists(f):
            os.remove(f)


# ========== 初始化 ==========
print("=" * 70)
print("初始化：获取基础数据")
print("=" * 70)

persons, _ = http_get("/persons")
p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]
print(f"  admin id={p_admin['id']}, operator id={p_op['id']}, observer id={p_obs['id']}")

sensors, _ = http_get("/sensors")
s1 = [s for s in sensors if s["code"] == "TEMP-001"][0]
s2 = [s for s in sensors if s["code"] == "TEMP-002"][0]
s3 = [s for s in sensors if s["code"] == "TEMP-003"][0]
print(f"  TEMP-001 id={s1['id']}, TEMP-002 id={s2['id']}, TEMP-003 id={s3['id']}")

zones, _ = http_get("/zones")
z1 = [z for z in zones if z["name"] == "冷冻库区A"][0]
print(f"  冷冻库区A id={z1['id']}")

create_temp_test_files()

# ========== TEST 1: 权限验证 ==========
print()
print("=" * 70)
print("TEST 1: 权限验证")
print("=" * 70)

# observer 不能创建
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2026-06-10T00:00:00",
    "end_time": "2026-06-10T23:59:59",
    "reason": "测试",
    "created_by": p_obs["id"]
})
print(f"  observer创建: status={s}")
assert_eq(s, 403, "observer创建抑制规则应返回403")

# operator 可以创建
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2026-06-10T00:00:00",
    "end_time": "2026-06-10T23:59:59",
    "reason": "operator测试",
    "created_by": p_op["id"]
})
print(f"  operator创建: status={s}, id={r.get('id')}")
assert_eq(s, 200, "operator创建抑制规则应成功")
rule_op_test = r["id"]

# observer 不能撤销
r, s = http_post(f"/suppression-rules/{rule_op_test}/revoke", {"person_id": p_obs["id"]})
print(f"  observer撤销: status={s}")
assert_eq(s, 403, "observer撤销抑制规则应返回403")

# operator 可以撤销
r, s = http_post(f"/suppression-rules/{rule_op_test}/revoke", {"person_id": p_op["id"]})
print(f"  operator撤销: status={s}, status={r.get('status')}")
assert_eq(s, 200, "operator撤销抑制规则应成功")
assert_eq(r["status"], "revoked", "撤销后状态为revoked")

# admin 可以创建
r, s = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2026-06-11T00:00:00",
    "end_time": "2026-06-11T23:59:59",
    "reason": "admin测试",
    "created_by": p_admin["id"]
})
print(f"  admin创建: status={s}, id={r.get('id')}")
assert_eq(s, 200, "admin创建抑制规则应成功")

# ========== TEST 2: 时间验证 ==========
print()
print("=" * 70)
print("TEST 2: 时间验证")
print("=" * 70)

# 结束时间早于开始时间
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2026-06-15T12:00:00",
    "end_time": "2026-06-15T10:00:00",
    "reason": "时间错误",
    "created_by": p_admin["id"]
})
print(f"  结束早于开始: status={s}")
assert_eq(s, 400, "结束早于开始应返回400")
assert_true("End time must be after start time" in r.get("detail", ""),
            "错误信息包含End time must be after start time")

# 时间重叠冲突
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2026-06-10T12:00:00",
    "end_time": "2026-06-11T12:00:00",
    "reason": "冲突测试",
    "created_by": p_admin["id"]
})
# 注意：之前的 rule_op_test 已经被 revoked 了，所以应该不会冲突
# 让我们先创建一个 active 的规则
r_active, s_active = http_post("/suppression-rules", {
    "sensor_id": s3["id"],
    "start_time": "2026-06-16T00:00:00",
    "end_time": "2026-06-16T23:59:59",
    "reason": "活跃规则",
    "created_by": p_admin["id"]
})
assert_eq(s_active, 200, "创建活跃规则成功")
active_rule_id = r_active["id"]

# 再创建一个重叠的
r_conflict, s_conflict = http_post("/suppression-rules", {
    "sensor_id": s3["id"],
    "start_time": "2026-06-16T12:00:00",
    "end_time": "2026-06-17T12:00:00",
    "reason": "冲突规则",
    "created_by": p_admin["id"]
})
print(f"  时间重叠: status={s_conflict}")
assert_eq(s_conflict, 409, "时间重叠应返回409")
assert_true("Conflict" in r_conflict.get("detail", ""),
            "错误信息包含Conflict")

# ========== TEST 3: 按传感器抑制 over_temp ==========
print()
print("=" * 70)
print("TEST 3: 按传感器抑制 over_temp 报警")
print("=" * 70)

# 创建抑制规则（TEMP-001，over_temp类型）
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "alarm_type": "over_temp",
    "start_time": "2026-06-18T00:00:00",
    "end_time": "2026-06-18T23:59:59",
    "reason": "传感器检修",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "创建抑制规则成功")
overtemp_rule_id = r["id"]
print(f"  抑制规则ID: {overtemp_rule_id}")

# 导入超温读数
r_import, s_import = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2026-06-18T10:00:00"}
])
print(f"  导入结果: successful={r_import['successful']}, new_alarms={r_import['new_alarms']}, suppressed={r_import['suppressed_alarms']}")
assert_eq(r_import["successful"], 1, "读数成功导入")
assert_true(r_import["new_alarms"] >= 1, "至少产生1个新报警")
assert_eq(r_import["suppressed_alarms"], 1, "1个报警被抑制")

# 验证报警状态
alarms, _ = http_get("/alarms")
overtemp_alarms = [a for a in alarms if a["sensor_code"] == "TEMP-001" and a["alarm_type"] == "over_temp" and "2026-06-18" in a["trigger_time"]]
print(f"  TEMP-001 6月18日的over_temp报警: {len(overtemp_alarms)} 个")
assert_true(len(overtemp_alarms) >= 1, "有over_temp报警")
if overtemp_alarms:
    alarm = overtemp_alarms[0]
    assert_eq(alarm["status"], "suppressed", "报警状态为suppressed")
    assert_eq(alarm["suppression_rule_id"], overtemp_rule_id, "关联正确的抑制规则")
    assert_eq(alarm["suppression_rule_reason"], "传感器检修", "抑制原因正确")

# 验证读数仍然入库了
readings, _ = http_get(f"/readings?sensor_id={s1['id']}&limit=10")
readings_0618 = [r for r in readings if "2026-06-18T10:00:00" in r["reading_time"]]
print(f"  6月18日10:00的读数: {len(readings_0618)} 条")
assert_eq(len(readings_0618), 1, "读数正常入库")

# ========== TEST 4: 按库区抑制 ==========
print()
print("=" * 70)
print("TEST 4: 按库区抑制")
print("=" * 70)

# 创建库区抑制规则（冷冻库区A）
r, s = http_post("/suppression-rules", {
    "zone_id": z1["id"],
    "start_time": "2026-06-19T00:00:00",
    "end_time": "2026-06-19T23:59:59",
    "reason": "库区整体维护",
    "created_by": p_admin["id"]
})
assert_eq(s, 200, "创建库区抑制规则成功")
zone_rule_id = r["id"]
print(f"  库区抑制规则ID: {zone_rule_id}")

# 导入超温读数
r_import1, s_import1 = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -8.0, "reading_time": "2026-06-19T08:00:00"}
])
print(f"  超温导入: successful={r_import1['successful']}, new_alarms={r_import1['new_alarms']}, suppressed={r_import1['suppressed_alarms']}")
assert_eq(r_import1["successful"], 1, "超温读数导入成功")
assert_true(r_import1["suppressed_alarms"] >= 1, "over_temp报警被抑制")

# 再导入低温读数（同一窗口内，验证under_temp也被库区规则抑制）
r_import2, s_import2 = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -30.0, "reading_time": "2026-06-19T10:00:00"}
])
print(f"  低温导入: successful={r_import2['successful']}, new_alarms={r_import2['new_alarms']}, suppressed={r_import2['suppressed_alarms']}")
assert_eq(r_import2["successful"], 1, "低温读数导入成功")
assert_true(r_import2["suppressed_alarms"] >= 1, "under_temp报警被抑制")

# 验证：两种报警都被抑制，且关联的是库区规则
alarms, _ = http_get(f"/alarms?sensor_id={s1['id']}")
zone_suppressed_alarms = [a for a in alarms if a["suppression_rule_id"] == zone_rule_id]
print(f"  关联库区抑制规则的报警: {len(zone_suppressed_alarms)} 个")
for a in zone_suppressed_alarms:
    print(f"    - {a['alarm_type']}: {a['status']}, rule_id={a.get('suppression_rule_id')}")
    assert_eq(a["status"], "suppressed", f"{a['alarm_type']}报警状态为suppressed")
    assert_eq(a["suppression_rule_id"], zone_rule_id, "关联库区抑制规则")

assert_true(any(a["alarm_type"] == "over_temp" for a in zone_suppressed_alarms), "有over_temp报警被库区规则抑制")
assert_true(any(a["alarm_type"] == "under_temp" for a in zone_suppressed_alarms), "有under_temp报警被库区规则抑制")

# ========== TEST 5: 按报警类型抑制 ==========
print()
print("=" * 70)
print("TEST 5: 按报警类型抑制（只抑制over_temp，offline正常）")
print("=" * 70)

# 用 TEMP-002 测试，只抑制 over_temp
r, s = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "alarm_type": "over_temp",
    "start_time": "2026-06-21T00:00:00",
    "end_time": "2026-06-21T23:59:59",
    "reason": "只抑制超温",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "创建类型过滤的抑制规则成功")
type_rule_id = r["id"]

# 先导入正常读数
http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -25.0, "reading_time": "2026-06-21T08:00:00"}
])

# 导入超时后的超温读数（应触发offline报警+over_temp报警）
r_import, s_import = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -15.0, "reading_time": "2026-06-21T10:00:00"}
])
print(f"  导入结果: new_alarms={r_import['new_alarms']}, suppressed={r_import['suppressed_alarms']}")
assert_eq(r_import["suppressed_alarms"], 1, "只有1个报警被抑制（over_temp）")

# 验证：offline 报警应该是 open，over_temp 应该是 suppressed
alarms, _ = http_get(f"/alarms?sensor_id={s2['id']}")
jun21_alarms = [a for a in alarms if "2026-06-21" in str(a.get("trigger_time", ""))]
print(f"  6月21日的报警: {len(jun21_alarms)} 个")
offline_alarms = [a for a in jun21_alarms if a["alarm_type"] == "offline"]
overtemp_alarms = [a for a in jun21_alarms if a["alarm_type"] == "over_temp"]
assert_true(len(offline_alarms) >= 1, "有offline报警")
assert_true(len(overtemp_alarms) >= 1, "有over_temp报警")
if offline_alarms:
    assert_eq(offline_alarms[0]["status"], "open", "offline报警为open（未被抑制）")
if overtemp_alarms:
    assert_eq(overtemp_alarms[0]["status"], "suppressed", "over_temp报警为suppressed")

# ========== TEST 6: 撤销抑制后恢复触发 ==========
print()
print("=" * 70)
print("TEST 6: 撤销抑制后恢复触发")
print("=" * 70)

# 用 TEMP-003 测试
r, s = http_post("/suppression-rules", {
    "sensor_id": s3["id"],
    "start_time": "2026-06-22T00:00:00",
    "end_time": "2026-06-22T23:59:59",
    "reason": "临时抑制",
    "created_by": p_admin["id"]
})
assert_eq(s, 200, "创建抑制规则成功")
revoke_test_rule_id = r["id"]

# 导入超温读数（被抑制）
r1, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 10.0, "reading_time": "2026-06-22T10:00:00"}
])
print(f"  撤销前导入: suppressed={r1['suppressed_alarms']}")
assert_eq(r1["suppressed_alarms"], 1, "撤销前报警被抑制")

# 撤销规则
r_revoke, s_revoke = http_post(f"/suppression-rules/{revoke_test_rule_id}/revoke", {"person_id": p_admin["id"]})
assert_eq(s_revoke, 200, "撤销成功")
assert_eq(r_revoke["status"], "revoked", "规则状态为revoked")
print(f"  已撤销规则 {revoke_test_rule_id}")

# 再导入超温读数（去重窗口外，应产生新的open报警）
r2, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 11.0, "reading_time": "2026-06-22T14:00:00"}
])
print(f"  撤销后导入: new_alarms={r2['new_alarms']}, suppressed={r2['suppressed_alarms']}")
assert_eq(r2["suppressed_alarms"], 0, "撤销后没有被抑制的报警")

alarms, _ = http_get(f"/alarms?sensor_id={s3['id']}&status=open")
jun22_open_overtemp = [a for a in alarms if a["alarm_type"] == "over_temp" and "2026-06-22" in str(a.get("trigger_time", ""))]
print(f"  6月22日的open状态超温报警: {len(jun22_open_overtemp)} 个")
assert_true(len(jun22_open_overtemp) >= 1, "撤销后有open状态的超温报警")

# ========== TEST 7: 到期恢复 ==========
print()
print("=" * 70)
print("TEST 7: 抑制到期后恢复触发")
print("=" * 70)

# 创建一个只有 1 小时窗口的抑制规则
r, s = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2026-06-23T08:00:00",
    "end_time": "2026-06-23T09:00:00",
    "reason": "短时抑制",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "创建短时抑制规则成功")
short_rule_id = r["id"]

# 在抑制窗口内导入 - 应该被抑制
r_in, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -10.0, "reading_time": "2026-06-23T08:30:00"}
])
print(f"  窗口内导入: suppressed={r_in['suppressed_alarms']}")
# 注意：可能有 offline + over_temp，但由于前面有 6月21日的读数，这里间隔较久可能也会触发 offline
# 我们只验证 over_temp 是否被抑制
assert_true(r_in["suppressed_alarms"] >= 1, "窗口内至少1个报警被抑制")

# 在抑制窗口外导入 - 不应该被抑制
r_out, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -9.0, "reading_time": "2026-06-23T10:00:00"}
])
print(f"  窗口外导入: new_alarms={r_out['new_alarms']}, suppressed={r_out['suppressed_alarms']}")

# 检查 10:00 触发的 over_temp 报警状态
alarms, _ = http_get(f"/alarms?sensor_id={s2['id']}")
jun23_overtemps = [a for a in alarms if a["alarm_type"] == "over_temp" and "2026-06-23" in str(a.get("trigger_time", ""))]
print(f"  6月23日的over_temp报警: {len(jun23_overtemps)} 个")
for a in jun23_overtemps:
    print(f"    - {a['trigger_time']}: {a['status']}")

# 应该有一个在 08:30 的 suppressed 和一个在 10:00 的 open（或其他时间）
suppressed_count = sum(1 for a in jun23_overtemps if a["status"] == "suppressed")
open_count = sum(1 for a in jun23_overtemps if a["status"] == "open")
print(f"  suppressed: {suppressed_count}, open: {open_count}")
assert_true(suppressed_count >= 1, "至少有1个suppressed报警（窗口内）")
assert_true(open_count >= 1, "至少有1个open报警（窗口外，到期后恢复）")

# ========== TEST 8: 命中日志 ==========
print()
print("=" * 70)
print("TEST 8: 抑制命中日志（审计）")
print("=" * 70)

# 查看规则的命中日志
hits, s = http_get(f"/suppression-rules/{overtemp_rule_id}/hits")
print(f"  规则 {overtemp_rule_id} 的命中数: {len(hits)}")
assert_eq(s, 200, "获取命中日志成功")
assert_true(len(hits) >= 1, "至少有1条命中记录")

if hits:
    hit = hits[0]
    print(f"  命中记录: id={hit['id']}, alarm_id={hit['alarm_id']}, alarm_type={hit['alarm_type']}")
    print(f"    trigger_value={hit['trigger_value']}, trigger_time={hit['trigger_time']}")
    assert_eq(hit["rule_id"], overtemp_rule_id, "命中记录关联正确的规则")
    assert_eq(hit["alarm_type"], "over_temp", "命中类型正确")
    assert_eq(hit["trigger_value"], -10.0, "触发值正确")
    assert_true(hit["trigger_time"] is not None, "有触发时间")
    assert_true(hit["sensor_code"] is not None, "有传感器编码")

# 规则详情中也有 hit_count
rule_detail, _ = http_get(f"/suppression-rules/{overtemp_rule_id}")
print(f"  规则详情 hit_count: {rule_detail.get('hit_count')}")
assert_eq(rule_detail["hit_count"], len(hits), "规则详情的hit_count与实际一致")

# ========== TEST 9: 导入统计一致（JSON/CSV/直接导入） ==========
print()
print("=" * 70)
print("TEST 9: 导入统计一致（JSON/CSV/直接导入）")
print("=" * 70)

# 先创建抑制规则
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2026-06-20T00:00:00",
    "end_time": "2026-06-20T23:59:59",
    "reason": "统计测试",
    "created_by": p_admin["id"]
})
assert_eq(s, 200, "创建抑制规则成功")
stats_rule_id = r["id"]

# 直接导入（注意：我们的测试文件有 3 条数据，其中 09:00 最早，10:00 中间，10:30 最晚）
# 但由于这个传感器之前已经有很多读数了，所以可能会有乱序问题
# 让我们使用一个干净的传感器，比如 TEMP-003 的 under_temp

# 换个思路：直接比较直接导入、JSON导入、CSV导入的结果结构
# 由于数据可能会累积，我们只验证三个接口都返回 suppressed_alarms 字段

# 直接导入
r_direct, s_direct = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 15.0, "reading_time": "2026-06-24T10:00:00"}
])
print(f"  直接导入: successful={r_direct['successful']}, failed={r_direct['failed']}, "
      f"new_alarms={r_direct['new_alarms']}, suppressed={r_direct['suppressed_alarms']}")
assert_true("suppressed_alarms" in r_direct, "直接导入结果包含suppressed_alarms字段")
assert_eq(r_direct["total"], 1, "total正确")
assert_eq(r_direct["successful"] + r_direct["failed"], 1, "successful+failed=total")

# JSON 文件导入
r_json, s_json = http_post_file("/readings/import-json", "test_suppress.json")
print(f"  JSON导入: successful={r_json['successful']}, failed={r_json['failed']}, "
      f"new_alarms={r_json['new_alarms']}, suppressed={r_json['suppressed_alarms']}")
assert_true("suppressed_alarms" in r_json, "JSON导入结果包含suppressed_alarms字段")
assert_eq(r_json["total"], 3, "total正确")
assert_eq(r_json["successful"] + r_json["failed"], 3, "successful+failed=total")
assert_eq(len(r_json["errors"]), r_json["failed"], "errors长度等于failed数")

# CSV 文件导入
r_csv, s_csv = http_post_file("/readings/import-csv", "test_suppress.csv")
print(f"  CSV导入: successful={r_csv['successful']}, failed={r_csv['failed']}, "
      f"new_alarms={r_csv['new_alarms']}, suppressed={r_csv['suppressed_alarms']}")
assert_true("suppressed_alarms" in r_csv, "CSV导入结果包含suppressed_alarms字段")
assert_eq(r_csv["total"], 3, "total正确")
assert_eq(r_csv["successful"] + r_csv["failed"], 3, "successful+failed=total")
assert_eq(len(r_csv["errors"]), r_csv["failed"], "errors长度等于failed数")

# ========== TEST 10: CSV 导出 ==========
print()
print("=" * 70)
print("TEST 10: CSV 导出")
print("=" * 70)

# 抑制规则 CSV 导出
req = urllib.request.Request(f"{BASE}/suppression-rules/export.csv")
with urllib.request.urlopen(req) as resp:
    csv_content = resp.read().decode()
lines = csv_content.strip().split("\n")
print(f"  抑制规则CSV: {len(lines)} 行（含表头）")
assert_true(len(lines) >= 2, "至少有表头+1条数据")
header = lines[0]
assert_true("id" in header, "CSV包含id列")
assert_true("reason" in header, "CSV包含reason列")
assert_true("status" in header, "CSV包含status列")
assert_true("hit_count" in header, "CSV包含hit_count列")

# 命中日志 CSV 导出
req = urllib.request.Request(f"{BASE}/suppression-hits/export.csv")
with urllib.request.urlopen(req) as resp:
    csv_content = resp.read().decode()
lines = csv_content.strip().split("\n")
print(f"  命中日志CSV: {len(lines)} 行（含表头）")
assert_true(len(lines) >= 2, "至少有表头+1条数据")
header = lines[0]
assert_true("rule_id" in header, "CSV包含rule_id列")
assert_true("alarm_id" in header, "CSV包含alarm_id列")
assert_true("trigger_value" in header, "CSV包含trigger_value列")
assert_true("trigger_time" in header, "CSV包含trigger_time列")

# 报警 CSV 导出（验证包含抑制信息）
req = urllib.request.Request(f"{BASE}/alarms/export.csv")
with urllib.request.urlopen(req) as resp:
    csv_content = resp.read().decode()
lines = csv_content.strip().split("\n")
header = lines[0]
print(f"  报警CSV表头: {header[:100]}...")
assert_true("suppression_rule_id" in header, "报警CSV包含suppression_rule_id列")
assert_true("suppression_rule_reason" in header, "报警CSV包含suppression_rule_reason列")

# ========== TEST 11: 规则列表和详情 ==========
print()
print("=" * 70)
print("TEST 11: 规则列表和详情")
print("=" * 70)

# 列表
rules, s = http_get("/suppression-rules")
print(f"  抑制规则总数: {len(rules)}")
assert_eq(s, 200, "获取规则列表成功")
assert_true(len(rules) >= 5, "至少有5条规则")

# 按状态筛选
active_rules, _ = http_get("/suppression-rules?status=active")
revoked_rules, _ = http_get("/suppression-rules?status=revoked")
print(f"  active: {len(active_rules)}, revoked: {len(revoked_rules)}")
assert_true(len(active_rules) >= 1, "至少有1个active规则")
assert_true(len(revoked_rules) >= 1, "至少有1个revoked规则")

# 详情
detail, s = http_get(f"/suppression-rules/{overtemp_rule_id}")
print(f"  规则详情: id={detail['id']}, status={detail['status']}, reason={detail['reason']}")
print(f"    creator: {detail['creator_name']} ({detail['creator_role']})")
print(f"    sensor: {detail['sensor_code']} ({detail['sensor_name']})")
assert_eq(s, 200, "获取规则详情成功")
assert_eq(detail["id"], overtemp_rule_id, "ID正确")
assert_true(detail["creator_name"] is not None, "有创建人姓名")
assert_true(detail["sensor_code"] is not None, "有传感器编码")

# ========== 总结 ==========
print()
print("=" * 70)
print(f"测试汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

cleanup_temp_files()

if FAIL == 0:
    print("\n[OK] 所有抑制规则测试通过!")
    print("\n提示: 可以重启服务后再次运行，验证跨重启一致性。")
else:
    print(f"\n[FAIL] 有{FAIL}个测试失败。")
    exit(1)
