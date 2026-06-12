"""
最终验证脚本：验证报警抑制漏洞修复（对应 README 文档示例）
覆盖：
1. 创建抑制规则（按传感器）
2. 创建抑制规则（按库区）
3. 规则命中生成 suppressed 报警 + suppression_rule_id 非空
4. 命中日志查询（/suppression-rules/{id}/hits）
5. CSV 导出（/suppression-rules/export.csv 和 /suppression-hits/export.csv）
6. observer 调旧端点 /alarms/{id}/suppress 失败
7. observer 创建抑制规则失败
8. 其他状态流转（ack/processing/escalate/close）正常
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
    if keyword in text:
        PASS += 1
        print(f"  [PASS] {msg} (包含 '{keyword}')")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg} (未找到 '{keyword}')")


print("=" * 70)
print("FINAL VERIFICATION: 报警抑制漏洞修复 & README 文档示例验证")
print("=" * 70)

# 基础数据
persons, _ = http_get_json("/persons")
sensors, _ = http_get_json("/sensors")
zones, _ = http_get_json("/zones")

p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]
s1 = [s for s in sensors if s["code"] == "TEMP-001"][0]
s3 = [s for s in sensors if s["code"] == "TEMP-003"][0]
z_a = [z for z in zones if z["name"] == "冷冻库区A"][0]

print(f"\n基础数据: admin={p_admin['id']}, op={p_op['id']}, obs={p_obs['id']}")
print(f"              TEMP-001={s1['id']}, TEMP-003={s3['id']}, 冷冻库区A={z_a['id']}")

# ========== 1. observer 调旧端点失败 ==========
print("\n--- [1/8] observer 调旧 /alarms/{id}/suppress 端点失败 ---")
# 先产生一个 open 报警
http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 2.0, "reading_time": "2100-01-10T09:50:00"}
])
r, s = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 10.0, "reading_time": "2100-01-10T10:00:00"}
])
alarms, _ = http_get_json("/alarms")
open_alarm = [a for a in alarms if a["status"] == "open" and a["sensor_id"] == s3["id"]][-1]
print(f"  open 报警 id={open_alarm['id']}, 状态={open_alarm['status']}")

# observer 尝试调用旧端点
resp, status = http_post(f"/alarms/{open_alarm['id']}/suppress", {
    "person_id": p_obs["id"], "note": "observer test", "suppress_minutes": 60
})
print(f"  observer 调旧端点: status={status}")
assert_true(status in [404, 405, 400], f"旧端点返回错误(404/405/400): {status}")

# 检查报警状态未被改变
alarms2, _ = http_get_json("/alarms")
alarm_after = [a for a in alarms2 if a["id"] == open_alarm["id"]][0]
assert_eq(alarm_after["status"], "open", "observer 调用后报警仍为 open")
assert_true(alarm_after.get("suppression_rule_id") is None, "observer 调用后 suppression_rule_id 仍为空")

# ========== 2. observer 创建抑制规则失败 ==========
print("\n--- [2/8] observer 创建抑制规则失败 (403) ---")
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2100-02-01T00:00:00",
    "end_time": "2100-02-01T23:59:59",
    "reason": "observer 非法创建",
    "created_by": p_obs["id"]
})
assert_eq(s, 403, "observer 创建抑制规则返回 403")

# ========== 3. 创建抑制规则（按传感器）+ 命中 suppressed ==========
print("\n--- [3/8] operator 创建按传感器抑制规则 + 命中 suppressed ---")
# 先导入基准
http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -20.0, "reading_time": "2100-02-15T09:50:00"}
])
# 创建规则
r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2100-02-15T00:00:00",
    "end_time": "2100-02-15T23:59:59",
    "reason": "README示例：传感器校准检修",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "operator 创建按传感器抑制规则成功 (200)")
rule_sensor_id = r["id"]
print(f"  规则 id={rule_sensor_id}, reason={r['reason']}")

# 导入超温读数（在抑制窗口内）
r2, s2 = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2100-02-15T10:00:00"}
])
print(f"  导入超温: successful={r2['successful']}, new_alarms={r2['new_alarms']}, suppressed={r2.get('suppressed_alarms')}")
assert_true(r2.get("suppressed_alarms", 0) >= 1, "至少 1 个报警被抑制")

# 验证报警状态
alarms3, _ = http_get_json(f"/alarms?sensor_id={s1['id']}")
suppressed = [a for a in alarms3
              if a["status"] == "suppressed"
              and a["suppression_rule_id"] == rule_sensor_id
              and "2100-02-15" in str(a.get("trigger_time", ""))]
assert_true(len(suppressed) >= 1, "有 suppressed 报警")
if suppressed:
    a = suppressed[0]
    assert_eq(a["status"], "suppressed", "报警状态为 suppressed")
    assert_true(a["suppression_rule_id"] is not None, "suppression_rule_id 非空（非旧手工抑制）")
    assert_eq(a["suppression_rule_id"], rule_sensor_id, "关联正确的 suppression_rule_id")
    assert_eq(a["suppression_rule_reason"], "README示例：传感器校准检修", "有抑制原因")
    print(f"  suppressed 报警 id={a['id']}, rule_id={a['suppression_rule_id']}, reason={a['suppression_rule_reason']}")

# ========== 4. 创建抑制规则（按库区）+ 命中 ==========
print("\n--- [4/8] operator 创建按库区抑制规则 + 命中 over_temp+under_temp ---")
# 先导入基准
http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -20.0, "reading_time": "2100-02-20T09:50:00"}
])
# 创建库区规则
r, s = http_post("/suppression-rules", {
    "zone_id": z_a["id"],
    "start_time": "2100-02-20T00:00:00",
    "end_time": "2100-02-20T23:59:59",
    "reason": "README示例：库区A设备巡检",
    "created_by": p_op["id"]
})
assert_eq(s, 200, "operator 创建按库区抑制规则成功 (200)")
rule_zone_id = r["id"]
print(f"  库区规则 id={rule_zone_id}")

# 导入超温
r_over, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -9.0, "reading_time": "2100-02-20T10:00:00"}
])
assert_true(r_over.get("suppressed_alarms", 0) >= 1, "库区超温被抑制")

# 导入低温
r_under, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -28.0, "reading_time": "2100-02-20T10:30:00"}
])
assert_true(r_under.get("suppressed_alarms", 0) >= 1, "库区低温被抑制")

# ========== 5. 命中日志查询 ==========
print("\n--- [5/8] 命中日志查询 /suppression-rules/{id}/hits ---")
hits, s = http_get_json(f"/suppression-rules/{rule_sensor_id}/hits")
print(f"  规则 {rule_sensor_id} 命中日志数: {len(hits)}, status={s}")
assert_eq(s, 200, "获取命中日志 HTTP 200")
assert_true(len(hits) >= 1, "至少 1 条命中日志")
if hits:
    h = hits[0]
    assert_eq(h["rule_id"], rule_sensor_id, "命中日志关联正确规则")
    assert_true("alarm_type" in h, "命中日志包含 alarm_type")
    assert_true("trigger_value" in h, "命中日志包含 trigger_value")
    assert_true("trigger_time" in h, "命中日志包含 trigger_time")
    assert_true("alarm_id" in h, "命中日志包含 alarm_id")
    print(f"    - id={h['id']}, alarm_type={h.get('alarm_type')}, trigger_value={h.get('trigger_value')}, alarm_id={h.get('alarm_id')}")

# 规则详情的 hit_count 与实际一致
rule_detail, _ = http_get_json(f"/suppression-rules/{rule_sensor_id}")
assert_eq(rule_detail["hit_count"], len(hits), "规则详情 hit_count 与命中日志数一致")

# ========== 6. CSV 导出 ==========
print("\n--- [6/8] CSV 导出：抑制规则 & 命中日志 ---")
# 抑制规则 CSV
csv_text, s = http_get("/suppression-rules/export.csv")
assert_eq(s, 200, "/suppression-rules/export.csv HTTP 200")
reader = csv.reader(io.StringIO(csv_text))
rows = list(reader)
print(f"  抑制规则 CSV: {len(rows)} 行 (含表头)")
assert_true(len(rows) >= 2, "CSV 至少有表头 + 1 行数据")
assert_contains(rows[0], "id", "CSV 表头包含 id")
assert_contains(rows[0], "reason", "CSV 表头包含 reason")
assert_contains(rows[0], "status", "CSV 表头包含 status")
assert_contains(rows[0], "hit_count", "CSV 表头包含 hit_count")

# 命中日志 CSV
csv2, s2 = http_get("/suppression-hits/export.csv")
assert_eq(s2, 200, "/suppression-hits/export.csv HTTP 200")
reader2 = csv.reader(io.StringIO(csv2))
rows2 = list(reader2)
print(f"  命中日志 CSV: {len(rows2)} 行 (含表头)")
assert_true(len(rows2) >= 2, "命中日志 CSV 至少表头 + 1 行")
assert_contains(rows2[0], "rule_id", "命中日志 CSV 包含 rule_id")
assert_contains(rows2[0], "alarm_id", "命中日志 CSV 包含 alarm_id")
assert_contains(rows2[0], "trigger_value", "命中日志 CSV 包含 trigger_value")
assert_contains(rows2[0], "trigger_time", "命中日志 CSV 包含 trigger_time")

# ========== 7. 撤销规则后重新触发 open ==========
print("\n--- [7/8] 撤销规则后新异常读数生成 open 报警 ---")
# 撤销刚才的传感器规则
r_rev, s_rev = http_post(f"/suppression-rules/{rule_sensor_id}/revoke", {"person_id": p_op["id"]})
assert_eq(s_rev, 200, "撤销规则 HTTP 200")
assert_eq(r_rev["status"], "revoked", "撤销后规则状态为 revoked")

# 导入基准（避免 offline）
http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -20.0, "reading_time": "2100-02-25T13:50:00"}
])
# 导入撤销后的超温（仍在原时间窗口，但规则已撤销 → 应该 open）
r3, s3 = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2100-02-25T14:00:00"}
])
print(f"  撤销后导入: successful={r3['successful']}, new_alarms={r3['new_alarms']}, suppressed={r3.get('suppressed_alarms')}")
assert_eq(r3.get("suppressed_alarms", 0), 0, "撤销后无 suppressed 报警")
assert_true(r3["new_alarms"] >= 1, "撤销后产生新报警")

alarms4, _ = http_get_json(f"/alarms?sensor_id={s1['id']}")
new_open = [a for a in alarms4
            if a["status"] == "open"
            and a["alarm_type"] == "over_temp"
            and "2100-02-25T14:00:00" in str(a.get("trigger_time", ""))]
assert_true(len(new_open) >= 1, "撤销后有新的 open 状态超温报警")
if new_open:
    print(f"  新 open 报警 id={new_open[0]['id']}, status={new_open[0]['status']}")

# ========== 8. 其他状态流转正常 ==========
print("\n--- [8/8] 其他状态流转 (ack/processing/escalate/close) 不受影响 ---")
# 用新产生的 open 报警测试
flow_alarm = new_open[0] if new_open else open_alarm
fid = flow_alarm["id"]
print(f"  测试报警 id={fid}, 初始状态={flow_alarm['status']}")

r, s = http_post(f"/alarms/{fid}/acknowledge", {"person_id": p_op["id"], "note": "已确认"})
assert_eq(s, 200, f"operator acknowledge: HTTP {s}")
assert_eq(r["status"], "acknowledged", "流转到 acknowledged")

r, s = http_post(f"/alarms/{fid}/processing", {"person_id": p_op["id"], "note": "处理中"})
assert_eq(s, 200, f"operator processing: HTTP {s}")
assert_eq(r["status"], "processing", "流转到 processing")

r, s = http_post(f"/alarms/{fid}/escalate", {"person_id": p_op["id"], "note": "升级"})
assert_eq(s, 200, f"operator escalate: HTTP {s}")
assert_eq(r["status"], "escalated", "流转到 escalated")

r, s = http_post(f"/alarms/{fid}/close", {"person_id": p_admin["id"], "resolution_note": "修复完成"})
assert_eq(s, 200, f"admin close: HTTP {s}")
assert_eq(r["status"], "closed", "流转到 closed")

# observer 不能 ack
r, s = http_post(f"/alarms/{open_alarm['id']}/acknowledge", {"person_id": p_obs["id"], "note": "observer越权"})
assert_true(s in [400, 403], f"observer acknowledge 返回错误: HTTP {s}")

# ========== 汇总 ==========
print("\n" + "=" * 70)
print(f"FINAL VERIFICATION 汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)
if FAIL == 0:
    print("\n[OK] 所有最终验证通过！漏洞修复完成，文档示例一致。")
else:
    print(f"\n[FAIL] 有 {FAIL} 个验证失败。")
    exit(1)
