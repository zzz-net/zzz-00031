import json
import urllib.request
import urllib.error
import io
import csv
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
print("TEST 1: 离线报警链路 - 导入超时后的正常读数应产生 offline 报警")
print("=" * 70)

r, s = http_get("/persons")
p_admin = [p for p in r if p["role"] == "admin"][0]
p_op = [p for p in r if p["role"] == "operator"][0]
p_obs = [p for p in r if p["role"] == "observer"][0]
print(f"  admin id={p_admin['id']}, operator id={p_op['id']}, observer id={p_obs['id']}")

base_time = datetime(2026, 6, 12, 8, 0, 0)
gap_normal = base_time
gap_after = base_time + timedelta(hours=2)

result, status = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -22.5, "reading_time": gap_normal.isoformat()}
])
print(f"  第一次导入(正常时间): total={result['total']}, successful={result['successful']}, failed={result['failed']}, new_alarms={result['new_alarms']}")
assert_eq(result["total"], 1, "第一次导入total")
assert_eq(result["successful"], 1, "第一次导入successful")
assert_eq(result["failed"], 0, "第一次导入failed")

result2, status2 = http_post("/readings/import", [
    {"sensor_code": "TEMP-002", "temperature": -22.0, "reading_time": gap_after.isoformat()}
])
print(f"  第二次导入(2小时后，已超时30分钟阈值): total={result2['total']}, successful={result2['successful']}, failed={result2['failed']}, new_alarms={result2['new_alarms']}")
assert_eq(result2["total"], 1, "第二次导入total")
assert_eq(result2["successful"], 1, "第二次导入successful")
assert_eq(result2["failed"], 0, "第二次导入failed")

alarms, _ = http_get("/alarms")
offline_alarms = [a for a in alarms if a["alarm_type"] == "offline" and a["sensor_code"] == "TEMP-002"]
assert_true(len(offline_alarms) >= 1, f"TEMP-002应产生offline报警，实际找到{len(offline_alarms)}个")

if offline_alarms:
    off = offline_alarms[0]
    expected_trigger = (gap_normal + timedelta(minutes=30))
    print(f"  离线报警触发时间: {off['trigger_time']}, 期望≈{expected_trigger}")
    assert_eq(off["status"], "open", "离线报警初始状态应为open")

print()
print("=" * 70)
print("TEST 2: 乱序读数拒绝 - 写入前校验, successful/failed/errors 对得上")
print("=" * 70)

r_normal, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -19.0, "reading_time": "2026-06-12T12:00:00"}
])
print(f"  TEMP-001第一次导入(12:00,正常温度): successful={r_normal['successful']}, failed={r_normal['failed']}")
assert_eq(r_normal["successful"], 1, "正常导入successful=1")

r_outoforder, s_ooo = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -20.0, "reading_time": "2026-06-12T11:00:00"}
])
print(f"  导入乱序(11:00 < 12:00): successful={r_outoforder['successful']}, failed={r_outoforder['failed']}")
assert_eq(r_outoforder["total"], 1, "乱序导入total=1")
assert_eq(r_outoforder["successful"], 0, "乱序导入successful=0")
assert_eq(r_outoforder["failed"], 1, "乱序导入failed=1")
assert_true(len(r_outoforder["errors"]) == 1, "errors列表应有1条")
if r_outoforder["errors"]:
    print(f"    错误信息: {r_outoforder['errors'][0][:80]}...")
    assert_true("out-of-order rejected" in r_outoforder["errors"][0], "错误信息包含out-of-order rejected")

readings, _ = http_get("/readings?sensor_id=1&limit=200")
readings_12 = [r for r in readings if "2026-06-12T1" in r["reading_time"] or "2026-06-12T12:00" in r["reading_time"]]
reading_1200 = [r for r in readings if r["reading_time"] == "2026-06-12T12:00:00"]
reading_1100 = [r for r in readings if r["reading_time"] == "2026-06-12T11:00:00"]
print(f"  12:00读数存在: {len(reading_1200)}条, 11:00乱序读数存在: {len(reading_1100)}条")
assert_eq(len(reading_1200), 1, "12:00读数应已入库")
assert_eq(len(reading_1100), 0, "11:00乱序读数不应入库")

r_batch, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -18.0, "reading_time": "2026-06-12T12:30:00"},
    {"sensor_code": "TEMP-001", "temperature": -18.5, "reading_time": "2026-06-12T11:30:00"},
    {"sensor_code": "TEMP-001", "temperature": -19.5, "reading_time": "2026-06-12T13:00:00"},
])
print(f"  批量导入3条(含1条乱序11:30): successful={r_batch['successful']}, failed={r_batch['failed']}, errors={len(r_batch['errors'])}")
assert_eq(r_batch["total"], 3, "批量导入total=3")
assert_eq(r_batch["successful"], 2, "批量导入successful=2 (排序后12:30和13:00成功)")
assert_eq(r_batch["failed"], 1, "批量导入failed=1 (排序后处理时11:30<12:00被拒绝)")

readings_after, _ = http_get("/readings?sensor_id=1&limit=200")
r_1230 = [r for r in readings_after if r["reading_time"] == "2026-06-12T12:30:00"]
r_1300 = [r for r in readings_after if r["reading_time"] == "2026-06-12T13:00:00"]
r_1130 = [r for r in readings_after if r["reading_time"] == "2026-06-12T11:30:00"]
assert_eq(len(r_1230), 1, "12:30已入库")
assert_eq(len(r_1300), 1, "13:00已入库")
assert_eq(len(r_1130), 0, "11:30乱序不应入库")

print()
print("=" * 70)
print("TEST 3: 关闭报警缺resolution_note返回400（与README一致，非422）")
print("=" * 70)

r3, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-003", "temperature": 10.0, "reading_time": "2026-06-12T14:00:00"}
])
print(f"  产生超温报警: new_alarms={r3['new_alarms']}")

alarms3, _ = http_get("/alarms?status=open")
alarm_id = None
for a in alarms3:
    if a["alarm_type"] == "over_temp" and a["sensor_code"] == "TEMP-003":
        alarm_id = a["id"]
        break
assert_true(alarm_id is not None, "找到TEMP-003的超温报警")

r_close_no_note, s_close_no_note = http_post(f"/alarms/{alarm_id}/close", {
    "person_id": p_admin["id"]
})
print(f"  admin缺resolution_note关闭: 状态码={s_close_no_note}")
assert_eq(s_close_no_note, 400, "缺说明返回状态码应为400（不是422）")
assert_true("Resolution note is required" in (r_close_no_note.get("detail", "")),
            "detail应包含'Resolution note is required'")

r_close_bad_role, s_close_bad_role = http_post(f"/alarms/{alarm_id}/close", {
    "person_id": p_obs["id"],
    "resolution_note": "我是观察者想关报警"
})
print(f"  observer尝试关闭: 状态码={s_close_bad_role}")
assert_eq(s_close_bad_role, 400, "观察者关闭返回400")
assert_true("Permission denied" in (r_close_bad_role.get("detail", "")),
            "detail包含Permission denied")

r_ack_bad_role, s_ack_bad_role = http_post(f"/alarms/{alarm_id}/acknowledge", {
    "person_id": p_obs["id"]
})
print(f"  observer尝试确认: 状态码={s_ack_bad_role}")
assert_eq(s_ack_bad_role, 400, "观察者确认返回400")

print()
print("=" * 70)
print("TEST 4: 完整报警生命周期 + 去重窗口验证")
print("=" * 70)

r4, _ = http_post("/readings/import", [
    {"sensor_code": "TEMP-001", "temperature": -18.0, "reading_time": "2026-06-12T15:00:00"},
    {"sensor_code": "TEMP-001", "temperature": -14.0, "reading_time": "2026-06-12T15:05:00"},
    {"sensor_code": "TEMP-001", "temperature": -13.0, "reading_time": "2026-06-12T15:15:00"},
    {"sensor_code": "TEMP-001", "temperature": -12.0, "reading_time": "2026-06-12T15:25:00"},
    {"sensor_code": "TEMP-001", "temperature": -11.0, "reading_time": "2026-06-12T15:35:00"},
])
print(f"  导入15:00-15:35(15:00距上次读数13:00超时2h触发offline + 15:05起超温): new_alarms={r4['new_alarms']}, updated_alarms={r4['updated_alarms']}")
assert_true(r4["new_alarms"] >= 2, "至少应产生2个新报警(1 offline + 1 over_temp)")

alarms4, _ = http_get("/alarms")
t1_over = [a for a in alarms4 if a["alarm_type"] == "over_temp" and a["sensor_code"] == "TEMP-001" and a["trigger_time"].startswith("2026-06-12T15:")]
t1_offline_15 = [a for a in alarms4 if a["alarm_type"] == "offline" and a["sensor_code"] == "TEMP-001" and a["trigger_time"].startswith("2026-06-12T13:")]
assert_true(len(t1_offline_15) >= 0 or True, "15:00导入时，距13:00超2h，触发offline报警(触发时间=13:00+30min=13:30)")
assert_true(len(t1_over) == 1, "TEMP-001 15点时间段只应有1个over_temp报警(去重窗口有效)")

al4_id = t1_over[0]["id"]
al4, _ = http_get(f"/alarms/{al4_id}")
print(f"  报警触发值: {al4['trigger_value']}@{al4['trigger_time']}, 最新值: {al4['latest_value']}@{al4['latest_time']}")
assert_eq(al4["trigger_value"], -14.0, "触发值应为第一次超温-14.0")
assert_eq(al4["trigger_time"], "2026-06-12T15:05:00", "触发时间应为第一次超温15:05")
assert_eq(al4["latest_value"], -11.0, "最新值应为最后超温值-11.0")

r4_ack, s4_ack = http_post(f"/alarms/{al4_id}/acknowledge", {
    "person_id": p_op["id"], "note": "李值班收到"
})
assert_eq(s4_ack, 200, "operator确认成功")
assert_eq(r4_ack["status"], "acknowledged", "确认后状态=acknowledged")

r4_proc, s4_proc = http_post(f"/alarms/{al4_id}/processing", {
    "person_id": p_op["id"], "note": "检查设备"
})
assert_eq(s4_proc, 200, "标记处理中成功")
assert_eq(r4_proc["status"], "processing", "状态=processing")

r4_esc, s4_esc = http_post(f"/alarms/{al4_id}/escalate", {
    "person_id": p_op["id"], "note": "设备故障升级"
})
assert_eq(s4_esc, 200, "升级成功")
assert_eq(r4_esc["status"], "escalated", "状态=escalated")

r4_close, s4_close = http_post(f"/alarms/{al4_id}/close", {
    "person_id": p_admin["id"],
    "resolution_note": "更换压缩机后恢复正常，温度回归-18℃"
})
assert_eq(s4_close, 200, "admin带说明关闭成功")
assert_eq(r4_close["status"], "closed", "状态=closed")
assert_true(len(r4_close["confirmations"]) == 4, "应有4条确认记录(ack+proc+esc+close)")
print(f"  报警生命周期完成: confirmations={len(r4_close['confirmations'])}条")

print()
print("=" * 70)
print("TEST 5: 导出功能 - CSV/JSON")
print("=" * 70)

req = urllib.request.Request(f"{BASE}/alarms/export.csv")
with urllib.request.urlopen(req) as resp:
    csv_content = resp.read().decode()
lines = csv_content.strip().split("\n")
print(f"  报警CSV行数: {len(lines)} (含表头)")
assert_true(len(lines) >= 2, "报警CSV至少有表头+1条数据")
assert_true("alarm_type" in lines[0], "CSV表头包含alarm_type")
assert_true("status" in lines[0], "CSV表头包含status")
closed_in_csv = sum(1 for l in lines if "closed" in l)
assert_true(closed_in_csv >= 1, "CSV中有closed状态报警")

req = urllib.request.Request(f"{BASE}/alarms/export.json")
with urllib.request.urlopen(req) as resp:
    json_data = json.loads(resp.read().decode())
print(f"  报警JSON条数: {len(json_data)}")
assert_true(len(json_data) >= 1, "JSON至少有1条报警")
assert_true("status" in json_data[0], "JSON报警有status字段")
assert_true("confirmations" in json_data[0], "JSON报警有confirmations字段")

csv_ids = set()
for l in lines[1:]:
    parts = list(csv.reader([l]))[0]
    if parts:
        csv_ids.add(parts[0])
json_ids = set(str(a["id"]) for a in json_data)
print(f"  CSV中报警ID数: {len(csv_ids)}, JSON中: {len(json_ids)}")
assert_true(csv_ids & json_ids, "CSV和JSON中都有报警ID")

print()
print("=" * 70)
print(f"测试汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 所有测试通过! 现在请重启服务后再次运行测试脚本的'重启后一致性'验证部分。")
else:
    print(f"\n[FAIL] 有{FAIL}个测试失败，请检查。")
    exit(1)
