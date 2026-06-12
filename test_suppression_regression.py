import json
import urllib.request
import urllib.error

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
        try:
            return json.loads(e.read().decode()), e.code
        except Exception:
            return {"detail": str(e)}, e.code


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


print("=" * 70)
print("TEST: 抑制规则回归测试（封闭旧手工抑制漏洞）")
print("=" * 70)

# 获取基础数据
persons, _ = http_get("/persons")
sensors, _ = http_get("/sensors")
p_admin = [p for p in persons if p["role"] == "admin"][0]
p_op = [p for p in persons if p["role"] == "operator"][0]
p_obs = [p for p in persons if p["role"] == "observer"][0]
s1 = [s for s in sensors if s["code"] == "TEMP-001"][0]
s2 = [s for s in sensors if s["code"] == "TEMP-002"][0]
s3 = [s for s in sensors if s["code"] == "TEMP-003"][0]
print(f"  admin id={p_admin['id']}, operator id={p_op['id']}, observer id={p_obs['id']}")
print(f"  TEMP-001 id={s1['id']}, TEMP-002 id={s2['id']}, TEMP-003 id={s3['id']}")

# 先清理 TEMP-002 上遗留的 open 报警，避免去重逻辑干扰（TEST 3/4 要用 TEMP-002）
all_alarms, _ = http_get("/alarms")
for a in all_alarms:
    if a["status"] == "open" and a.get("sensor_id") == s2["id"]:
        print(f"  清理 TEMP-002 遗留 open 报警 id={a['id']}...")
        http_post(f"/alarms/{a['id']}/close", {"person_id": p_admin["id"], "resolution_note": "回归测试前置清理"})

# ========== TEST 1: 旧 /alarms/{id}/suppress 端点已移除 ==========
print()
print("TEST 1: 旧手工抑制端点 /alarms/{id}/suppress 已移除")
print("-" * 70)

# 先导入一个基准读数（避免 offline），再导入超温读数产生 open 报警（用 TEMP-003）
http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 2.0, "reading_time": "2099-05-20T09:50:00"}
])
r, s = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 10.0, "reading_time": "2099-05-20T10:00:00"}
])
alarms, _ = http_get("/alarms")
open_alarms = [a for a in alarms if a["status"] == "open"]
assert_true(len(open_alarms) >= 1, "有 open 状态报警用于测试")
test_alarm_id = open_alarms[0]["id"]
print(f"  测试报警 id={test_alarm_id}")

# 尝试调用旧端点（应该返回 404，因为已删除）
r, s = http_post(f"/alarms/{test_alarm_id}/suppress", {
    "person_id": p_admin["id"],
    "note": "尝试旧抑制",
    "suppress_minutes": 60
})
print(f"  调用旧 /alarms/{test_alarm_id}/suppress: status={s}")
assert_true(s in [404, 405, 400], f"旧端点返回错误状态码（404/405/400）: {s}")

# 验证报警状态没有被改变
alarms, _ = http_get("/alarms")
check_alarm = [a for a in alarms if a["id"] == test_alarm_id][0]
assert_eq(check_alarm["status"], "open", "旧端点调用后报警仍为 open（未被抑制）")
assert_true(check_alarm.get("suppression_rule_id") is None, "旧端点调用后 suppression_rule_id 仍为空")

# ========== TEST 2: observer 不能创建抑制规则 ==========
print()
print("TEST 2: observer 不能创建抑制规则")
print("-" * 70)

r, s = http_post("/suppression-rules", {
    "sensor_id": s1["id"],
    "start_time": "2099-06-21T00:00:00",
    "end_time": "2099-06-21T23:59:59",
    "reason": "observer尝试创建",
    "created_by": p_obs["id"]
})
print(f"  observer 创建规则: status={s}")
assert_eq(s, 403, "observer 创建抑制规则应返回 403")

# ========== TEST 3: 规则命中生成 suppressed 报警 + 命中日志 ==========
print()
print("TEST 3: 规则命中生成 suppressed 报警和命中日志")
print("-" * 70)

# 用 TEMP-002（冷冻区B，阈值-30~-20℃）
# 先在抑制窗口内导入一个正常读数作为基准（距离超温读数10分钟，避免offline）
http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -25.0, "reading_time": "2099-12-01T09:50:00"}
])

# operator 创建抑制规则（针对 TEMP-002）
r, s = http_post("/suppression-rules", {
    "sensor_id": s2["id"],
    "start_time": "2099-12-01T00:00:00",
    "end_time": "2099-12-01T23:59:59",
    "reason": "回归测试：传感器检修",
    "created_by": p_op["id"]
})
print(f"  operator 创建规则: status={s}, id={r.get('id')}")
assert_eq(s, 200, "operator 创建抑制规则应成功")
rule_id = r["id"]

# 导入抑制窗口内的超温读数（TEMP-002阈值-30~-20℃，-15℃超温）
r_import, s_import = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -15.0, "reading_time": "2099-12-01T10:00:00"}
])
print(f"  导入超温读数: successful={r_import['successful']}, new_alarms={r_import['new_alarms']}, suppressed={r_import.get('suppressed_alarms')}")
assert_eq(r_import["successful"], 1, "读数成功导入")
assert_true(r_import.get("suppressed_alarms", 0) >= 1, "至少有 1 个报警被抑制")

# 验证报警状态
alarms, _ = http_get(f"/alarms?sensor_id={s2['id']}")
suppressed_on_day = [
    a for a in alarms
    if a["alarm_type"] == "over_temp"
    and a["status"] == "suppressed"
    and a["suppression_rule_id"] == rule_id
    and "2099-12-01" in str(a.get("trigger_time", ""))
]
print(f"  12月1日被规则{rule_id}抑制的over_temp报警: {len(suppressed_on_day)}个")
assert_true(len(suppressed_on_day) >= 1, "有被规则抑制的over_temp报警")
if suppressed_on_day:
    alarm = suppressed_on_day[0]
    assert_eq(alarm["status"], "suppressed", "报警状态为 suppressed")
    assert_eq(alarm["suppression_rule_id"], rule_id, "关联正确的抑制规则 ID")
    assert_eq(alarm["suppression_rule_reason"], "回归测试：传感器检修", "抑制原因正确")

# 验证命中日志
hits, s_hits = http_get(f"/suppression-rules/{rule_id}/hits")
print(f"  命中日志数: {len(hits)}, status={s_hits}")
assert_eq(s_hits, 200, "获取命中日志成功")
assert_true(len(hits) >= 1, "至少有 1 条命中日志")
if hits:
    hit = hits[0]
    assert_eq(hit["rule_id"], rule_id, "命中日志关联正确的规则")
    assert_eq(hit["alarm_type"], "over_temp", "命中类型正确")
    assert_true(hit.get("trigger_value") is not None, "命中日志有 trigger_value")
    assert_true(hit.get("sensor_code") is not None, "命中日志有 sensor_code")
    assert_true(hit.get("alarm_id") is not None, "命中日志有 alarm_id")

# 验证规则详情 hit_count
rule_detail, _ = http_get(f"/suppression-rules/{rule_id}")
assert_eq(rule_detail["hit_count"], len(hits), "规则详情 hit_count 与实际命中日志数一致")

# ========== TEST 4: 撤销规则后重新触发 open 报警 ==========
print()
print("TEST 4: 撤销抑制规则后新异常读数生成 open 报警")
print("-" * 70)

# 撤销规则
r_rev, s_rev = http_post(f"/suppression-rules/{rule_id}/revoke", {"person_id": p_op["id"]})
print(f"  撤销规则: status={s_rev}, new_status={r_rev.get('status')}")
assert_eq(s_rev, 200, "撤销规则成功")
assert_eq(r_rev["status"], "revoked", "规则状态变为 revoked")

# 先建立一个基准读数（距离撤销后的新异常读数10分钟，避免offline）
http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -25.0, "reading_time": "2099-12-01T13:50:00"}
])

# 导入新的超温读数（在原来的时间窗口内，但规则已撤销）
r_import2, s_import2 = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -15.0, "reading_time": "2099-12-01T14:00:00"}
])
print(f"  撤销后导入: successful={r_import2['successful']}, new_alarms={r_import2['new_alarms']}, suppressed={r_import2.get('suppressed_alarms')}")
assert_eq(r_import2.get("suppressed_alarms", 0), 0, "撤销后没有被抑制的报警")
assert_true(r_import2["new_alarms"] >= 1, "撤销后产生新的报警")

# 验证有新的 open 状态报警
alarms2, _ = http_get(f"/alarms?sensor_id={s2['id']}")
open_after_revoke = [
    a for a in alarms2
    if a["alarm_type"] == "over_temp"
    and a["status"] == "open"
    and "2099-12-01T14:00:00" in str(a.get("trigger_time", ""))
]
print(f"  撤销后新产生的 open 报警: {len(open_after_revoke)}个")
assert_true(len(open_after_revoke) >= 1, "撤销后有 open 状态的超温报警")

# ========== TEST 5: 其他状态流转（ack/processing/escalate/close）不受影响 ==========
print()
print("TEST 5: 其他报警状态流转（ack/processing/escalate/close）不受影响")
print("-" * 70)

# 用新产生的 open 报警来测试完整流转
test_alarm_for_flow = open_after_revoke[0] if open_after_revoke else open_alarms[0]
flow_id = test_alarm_for_flow["id"]
print(f"  测试流转报警 id={flow_id}, 当前状态={test_alarm_for_flow['status']}")

# acknowledge
r, s = http_post(f"/alarms/{flow_id}/acknowledge", {"person_id": p_op["id"], "note": "已确认"})
assert_eq(s, 200, f"operator 可以 acknowledge: status={s}")
if s == 200:
    assert_eq(r["status"], "acknowledged", "报警变为 acknowledged")

# processing
r, s = http_post(f"/alarms/{flow_id}/processing", {"person_id": p_op["id"], "note": "处理中"})
assert_eq(s, 200, f"operator 可以 processing: status={s}")
if s == 200:
    assert_eq(r["status"], "processing", "报警变为 processing")

# escalate
r, s = http_post(f"/alarms/{flow_id}/escalate", {"person_id": p_op["id"], "note": "需升级"})
assert_eq(s, 200, f"operator 可以 escalate: status={s}")
if s == 200:
    assert_eq(r["status"], "escalated", "报警变为 escalated")

# close
r, s = http_post(f"/alarms/{flow_id}/close", {"person_id": p_admin["id"], "resolution_note": "测试完成关闭"})
assert_eq(s, 200, f"admin 可以 close: status={s}")
if s == 200:
    assert_eq(r["status"], "closed", "报警变为 closed")

# observer 不能 acknowledge
r, s = http_post(f"/alarms/{test_alarm_id}/acknowledge", {"person_id": p_obs["id"], "note": "越权确认"})
assert_true(s in [400, 403], f"observer 不能 acknowledge，返回 {s}")

# ========== 汇总 ==========
print()
print("=" * 70)
print(f"抑制规则回归测试: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 所有抑制规则回归测试通过!")
else:
    print(f"\n[FAIL] 有 {FAIL} 个测试失败。")
    exit(1)
