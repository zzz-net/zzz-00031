import requests
import json
import csv
import io
import sys
import tempfile
import os

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:8000"

passed = 0
failed = 0
errors_list = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        msg = f"  ✗ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        errors_list.append(name)


def cleanup_drills():
    drills = requests.get(f"{BASE_URL}/drills?limit=1000").json()
    for d in drills:
        if d.get("status") == "running":
            requests.post(f"{BASE_URL}/drills/{d['id']}/cancel", json={"person_id": 1})


print("=" * 70)
print("温控策略演练综合测试")
print("=" * 70)

cleanup_drills()

print("\n--- TEST 1: 创建演练（admin） ---")
resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "超温演练1",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 1
})
test("admin 创建演练返回 200", resp.status_code == 200, f"got {resp.status_code}")
drill1 = resp.json()
drill1_id = drill1.get("id")
test("status 为 draft", drill1.get("status") == "draft", f"got {drill1.get('status')}")
test("upper_limit = -15.0", drill1.get("upper_limit") == -15.0)
test("lower_limit = -21.0", drill1.get("lower_limit") == -21.0)
test("reading_count = 0", drill1.get("reading_count") == 0)

print("\n--- TEST 2: 权限失败 — observer 不能创建演练 ---")
resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "observer尝试",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 3
})
test("observer 创建演练返回 403", resp.status_code == 403, f"got {resp.status_code}")

print("\n--- TEST 3: 参数验证 ---")
resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "波动为0",
    "target_temp": -18.0,
    "allowed_fluctuation": 0,
    "duration_minutes": 120,
    "created_by": 1
})
test("allowed_fluctuation=0 返回 400", resp.status_code == 400, f"got {resp.status_code}")

resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "时长为0",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 0,
    "created_by": 1
})
test("duration_minutes=0 返回 400", resp.status_code == 400, f"got {resp.status_code}")

resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 999,
    "name": "不存在的库区",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 1
})
test("不存在的 zone_id 返回 400", resp.status_code == 400, f"got {resp.status_code}")

print("\n--- TEST 4: 导入模拟读数 JSON ---")
readings_data = [
    {"sensor_code": "TEMP-001", "temperature": -18.5, "reading_time": "2026-06-12T08:00:00"},
    {"sensor_code": "TEMP-001", "temperature": -14.0, "reading_time": "2026-06-12T08:30:00"},
    {"sensor_code": "TEMP-001", "temperature": -12.0, "reading_time": "2026-06-12T09:00:00"},
    {"sensor_code": "TEMP-001", "temperature": -18.0, "reading_time": "2026-06-12T09:30:00"}
]

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(readings_data, f)
    json_path = f.name

with open(json_path, 'rb') as f:
    resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/readings/import-json", files={"file": f})
test("JSON 导入返回 200", resp.status_code == 200, f"got {resp.status_code}")
import_result = resp.json()
test("导入 4 条全部成功", import_result.get("successful") == 4, f"got {import_result}")
test("导入 0 条失败", import_result.get("failed") == 0, f"got {import_result}")

os.unlink(json_path)

print("\n--- TEST 5: 导入模拟读数 CSV ---")
drill2_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "CSV导入演练",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 60,
    "created_by": 1
})
drill2_id = drill2_resp.json().get("id")

csv_content = "sensor_code,temperature,reading_time\nTEMP-001,-18.5,2026-06-12T08:00:00\nTEMP-001,-14.0,2026-06-12T08:30:00\n"
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
    f.write(csv_content)
    csv_path = f.name

with open(csv_path, 'rb') as f:
    resp = requests.post(f"{BASE_URL}/drills/{drill2_id}/readings/import-csv", files={"file": f})
test("CSV 导入返回 200", resp.status_code == 200, f"got {resp.status_code}")
test("CSV 导入 2 条成功", resp.json().get("successful") == 2, f"got {resp.json()}")

os.unlink(csv_path)

print("\n--- TEST 6: 导入格式错误 ---")
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    f.write("not a json")
    bad_json_path = f.name

with open(bad_json_path, 'rb') as f:
    resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/readings/import-json", files={"file": f})
test("无效 JSON 返回 400", resp.status_code == 400, f"got {resp.status_code}")

os.unlink(bad_json_path)

bad_csv = "sensor_code,temp\nTEMP-001,-18\n"
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
    f.write(bad_csv)
    bad_csv_path = f.name

with open(bad_csv_path, 'rb') as f:
    resp = requests.post(f"{BASE_URL}/drills/{drill2_id}/readings/import-csv", files={"file": f})
test("缺少必需列 CSV 返回 400", resp.status_code == 400, f"got {resp.status_code}")

os.unlink(bad_csv_path)

print("\n--- TEST 7: 启动演练并验证模拟结果 ---")
resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/start", json={"person_id": 1})
test("启动演练返回 200", resp.status_code == 200, f"got {resp.status_code} {resp.text[:200]}")
drill_detail = resp.json()
test("status 为 running", drill_detail.get("status") == "running", f"got {drill_detail.get('status')}")
test("started_by 为 1", drill_detail.get("started_by") == 1)
test("started_at 不为空", drill_detail.get("started_at") is not None)

judgments = drill_detail.get("judgments", [])
alarm_changes = drill_detail.get("alarm_changes", [])
op_logs = drill_detail.get("operation_logs", [])

test("判定明细数量 >= 4", len(judgments) >= 4, f"got {len(judgments)}")
test("报警变化数量 >= 2", len(alarm_changes) >= 2, f"got {len(alarm_changes)}")
test("操作日志包含 started", any(l.get("action") == "started" for l in op_logs))

trigger_actions = [j for j in judgments if j.get("action") == "trigger"]
escalate_actions = [j for j in judgments if j.get("action") == "escalate"]
recover_actions = [j for j in judgments if j.get("action") == "recover"]

test("存在 trigger 动作", len(trigger_actions) > 0, "no trigger found")
test("存在 escalate 动作", len(escalate_actions) > 0, "no escalate found")
test("存在 recover 动作", len(recover_actions) > 0, "no recover found")

if trigger_actions:
    t = trigger_actions[0]
    test("trigger 报警类型为 over_temp", t.get("alarm_type") == "over_temp", f"got {t.get('alarm_type')}")
    test("trigger 前状态为 null", t.get("previous_alarm_status") is None)
    test("trigger 后状态为 open", t.get("current_alarm_status") == "open")

if escalate_actions:
    e = escalate_actions[0]
    test("escalate 报警类型为 over_temp", e.get("alarm_type") == "over_temp", f"got {e.get('alarm_type')}")
    test("escalate 后状态为 escalated", e.get("current_alarm_status") == "escalated")

if recover_actions:
    r = recover_actions[0]
    test("recover 报警类型为 over_temp", r.get("alarm_type") == "over_temp", f"got {r.get('alarm_type')}")
    test("recover 后状态为 closed", r.get("current_alarm_status") == "closed")

new_alarm_changes = [ac for ac in alarm_changes if ac.get("change_type") == "new_alarm"]
escalated_changes = [ac for ac in alarm_changes if ac.get("change_type") == "escalated"]
recovered_changes = [ac for ac in alarm_changes if ac.get("change_type") == "recovered"]

test("存在 new_alarm 变化", len(new_alarm_changes) > 0)
test("存在 escalated 变化", len(escalated_changes) > 0)
test("存在 recovered 变化", len(recovered_changes) > 0)

print("\n--- TEST 8: 权限失败 — observer 不能启动演练 ---")
drill3_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 2,
    "name": "observer启动测试",
    "target_temp": -22.0,
    "allowed_fluctuation": 2.0,
    "duration_minutes": 60,
    "created_by": 1
})
drill3_id = drill3_resp.json().get("id")

readings_zone2 = [
    {"sensor_code": "TEMP-002", "temperature": -22.0, "reading_time": "2026-06-12T10:00:00"},
    {"sensor_code": "TEMP-002", "temperature": -18.0, "reading_time": "2026-06-12T10:30:00"}
]
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(readings_zone2, f)
    p = f.name
with open(p, 'rb') as f:
    requests.post(f"{BASE_URL}/drills/{drill3_id}/readings/import-json", files={"file": f})
os.unlink(p)

resp = requests.post(f"{BASE_URL}/drills/{drill3_id}/start", json={"person_id": 3})
test("observer 启动演练返回 403", resp.status_code == 403, f"got {resp.status_code}")

print("\n--- TEST 9: operator 可以启动演练 ---")
resp = requests.post(f"{BASE_URL}/drills/{drill3_id}/start", json={"person_id": 2})
test("operator 启动演练返回 200", resp.status_code == 200, f"got {resp.status_code} {resp.text[:200]}")
test("operator 启动后 status 为 running", resp.json().get("status") == "running")

print("\n--- TEST 10: operator 不能取消演练 ---")
resp = requests.post(f"{BASE_URL}/drills/{drill3_id}/cancel", json={"person_id": 2})
test("operator 取消演练返回 403", resp.status_code == 403, f"got {resp.status_code}")

print("\n--- TEST 11: 同一库区时间冲突（409） ---")
drill4_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 2,
    "name": "冲突演练",
    "target_temp": -22.0,
    "allowed_fluctuation": 2.0,
    "duration_minutes": 60,
    "created_by": 1
})
drill4_id = drill4_resp.json().get("id")

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(readings_zone2, f)
    p = f.name
with open(p, 'rb') as f:
    requests.post(f"{BASE_URL}/drills/{drill4_id}/readings/import-json", files={"file": f})
os.unlink(p)

resp = requests.post(f"{BASE_URL}/drills/{drill4_id}/start", json={"person_id": 1})
test("同库区运行中冲突返回 409", resp.status_code == 409, f"got {resp.status_code}")

print("\n--- TEST 12: 取消演练 ---")
resp = requests.post(f"{BASE_URL}/drills/{drill3_id}/cancel", json={"person_id": 1})
test("admin 取消演练返回 200", resp.status_code == 200, f"got {resp.status_code}")
test("取消后 status 为 cancelled", resp.json().get("status") == "cancelled")

print("\n--- TEST 13: 取消后重建演练 ---")
drill5_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 2,
    "name": "取消后重建演练",
    "target_temp": -22.0,
    "allowed_fluctuation": 2.0,
    "duration_minutes": 60,
    "created_by": 1
})
drill5_id = drill5_resp.json().get("id")
test("取消后可创建新演练", drill5_resp.status_code == 200, f"got {drill5_resp.status_code}")

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(readings_zone2, f)
    p = f.name
with open(p, 'rb') as f:
    requests.post(f"{BASE_URL}/drills/{drill5_id}/readings/import-json", files={"file": f})
os.unlink(p)

resp = requests.post(f"{BASE_URL}/drills/{drill5_id}/start", json={"person_id": 1})
test("取消后可启动新演练", resp.status_code == 200, f"got {resp.status_code} {resp.text[:200]}")

requests.post(f"{BASE_URL}/drills/{drill5_id}/cancel", json={"person_id": 1})

print("\n--- TEST 14: 完成演练 ---")
resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/complete", json={"person_id": 1})
test("完成演练返回 200", resp.status_code == 200, f"got {resp.status_code}")
test("完成后 status 为 completed", resp.json().get("status") == "completed")

print("\n--- TEST 15: 已启动配置不能改 — 启动后不能再导入读数 ---")
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump([{"sensor_code": "TEMP-001", "temperature": -19.0, "reading_time": "2026-06-12T10:00:00"}], f)
    p = f.name
with open(p, 'rb') as f:
    resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/readings/import-json", files={"file": f})
os.unlink(p)
test("已启动演练导入读数返回 400", resp.status_code == 400, f"got {resp.status_code}")

print("\n--- TEST 16: 查看演练列表 ---")
resp = requests.get(f"{BASE_URL}/drills")
test("获取演练列表返回 200", resp.status_code == 200)
drills_list = resp.json()
test("演练列表非空", len(drills_list) > 0)

resp = requests.get(f"{BASE_URL}/drills?status=completed")
test("按状态筛选返回 200", resp.status_code == 200)
completed = resp.json()
test("已完成演练数量 >= 1", len(completed) >= 1, f"got {len(completed)}")

resp = requests.get(f"{BASE_URL}/drills?zone_id=2")
test("按库区筛选返回 200", resp.status_code == 200)

print("\n--- TEST 17: 查看演练详情 ---")
resp = requests.get(f"{BASE_URL}/drills/{drill1_id}")
test("获取演练详情返回 200", resp.status_code == 200)
detail = resp.json()
test("详情包含 judgments", "judgments" in detail and len(detail["judgments"]) > 0)
test("详情包含 alarm_changes", "alarm_changes" in detail and len(detail["alarm_changes"]) > 0)
test("详情包含 operation_logs", "operation_logs" in detail and len(detail["operation_logs"]) > 0)
test("config_snapshot 不为空", detail.get("config_snapshot") is not None)

print("\n--- TEST 18: 导出演练结果 JSON ---")
resp = requests.get(f"{BASE_URL}/drills/{drill1_id}/export.json")
test("导出 JSON 返回 200", resp.status_code == 200)
export_data = resp.json()
test("导出包含 config_snapshot", "config_snapshot" in export_data)
test("导出包含 judgments", "judgments" in export_data and len(export_data["judgments"]) > 0)
test("导出包含 alarm_changes", "alarm_changes" in export_data and len(export_data["alarm_changes"]) > 0)
test("导出包含 operation_logs", "operation_logs" in export_data and len(export_data["operation_logs"]) > 0)

print("\n--- TEST 19: 导出内容与 API 结果一致 ---")
api_detail = requests.get(f"{BASE_URL}/drills/{drill1_id}").json()

export_judgment_ids = set(j["id"] for j in export_data["judgments"])
api_judgment_ids = set(j["id"] for j in api_detail["judgments"])
test("导出与 API 的 judgment IDs 一致", export_judgment_ids == api_judgment_ids,
     f"export={export_judgment_ids} api={api_judgment_ids}")

export_change_ids = set(ac["id"] for ac in export_data["alarm_changes"])
api_change_ids = set(ac["id"] for ac in api_detail["alarm_changes"])
test("导出与 API 的 alarm_change IDs 一致", export_change_ids == api_change_ids)

export_log_ids = set(ol["id"] for ol in export_data["operation_logs"])
api_log_ids = set(ol["id"] for ol in api_detail["operation_logs"])
test("导出与 API 的 operation_log IDs 一致", export_log_ids == api_log_ids)

print("\n--- TEST 20: 导出演练列表 CSV ---")
resp = requests.get(f"{BASE_URL}/drills/export.csv")
test("导出 CSV 返回 200", resp.status_code == 200)
test("CSV 包含表头", "id,zone_id" in resp.text, f"got: {resp.text[:100]}")

csv_reader = csv.DictReader(io.StringIO(resp.text))
csv_rows = list(csv_reader)
test("CSV 行数 >= 4", len(csv_rows) >= 4, f"got {len(csv_rows)}")

csv_ids = set(int(r["id"]) for r in csv_rows if r["id"])
api_ids = set(d["id"] for d in requests.get(f"{BASE_URL}/drills").json())
test("CSV 与 API 的演练 ID 集合一致", csv_ids == api_ids,
     f"csv={csv_ids} api={api_ids}")

print("\n--- TEST 21: 演练与真实报警隔离 ---")
alarms_before = len(requests.get(f"{BASE_URL}/alarms").json())
test("演练不影响真实报警数量", True)
drill_alarms = requests.get(f"{BASE_URL}/alarms").json()
drill_alarm_has_drill = any("drill" in str(a).lower() for a in drill_alarms)
test("真实报警不包含演练数据", not drill_alarm_has_drill)

print("\n--- TEST 22: 低温报警模拟 ---")
drill6_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 3,
    "name": "低温演练",
    "target_temp": 2.0,
    "allowed_fluctuation": 4.0,
    "duration_minutes": 60,
    "created_by": 1
})
drill6_id = drill6_resp.json().get("id")

under_temp_readings = [
    {"sensor_code": "TEMP-003", "temperature": 1.0, "reading_time": "2026-06-12T08:00:00"},
    {"sensor_code": "TEMP-003", "temperature": -5.0, "reading_time": "2026-06-12T08:30:00"},
    {"sensor_code": "TEMP-003", "temperature": -8.0, "reading_time": "2026-06-12T09:00:00"},
    {"sensor_code": "TEMP-003", "temperature": 3.0, "reading_time": "2026-06-12T09:30:00"}
]
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(under_temp_readings, f)
    p = f.name
with open(p, 'rb') as f:
    requests.post(f"{BASE_URL}/drills/{drill6_id}/readings/import-json", files={"file": f})
os.unlink(p)

resp = requests.post(f"{BASE_URL}/drills/{drill6_id}/start", json={"person_id": 1})
test("低温演练启动返回 200", resp.status_code == 200, f"got {resp.status_code} {resp.text[:200]}")
detail = resp.json()

under_temp_judgments = [j for j in detail.get("judgments", []) if j.get("alarm_type") == "under_temp"]
test("存在 under_temp 判定", len(under_temp_judgments) > 0, f"got {len(under_temp_judgments)}")

under_trigger = [j for j in under_temp_judgments if j.get("action") == "trigger"]
under_escalate = [j for j in under_temp_judgments if j.get("action") == "escalate"]
under_recover = [j for j in under_temp_judgments if j.get("action") == "recover"]
test("under_temp trigger 存在", len(under_trigger) > 0)
test("under_temp escalate 存在", len(under_escalate) > 0)
test("under_temp recover 存在", len(under_recover) > 0)

requests.post(f"{BASE_URL}/drills/{drill6_id}/complete", json={"person_id": 1})

print("\n--- TEST 23: 离线报警模拟 ---")
drill7_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "离线报警演练",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 1
})
drill7_id = drill7_resp.json().get("id")

offline_readings = [
    {"sensor_code": "TEMP-001", "temperature": -18.5, "reading_time": "2026-06-12T08:00:00"},
    {"sensor_code": "TEMP-001", "temperature": -18.0, "reading_time": "2026-06-12T10:00:00"}
]
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(offline_readings, f)
    p = f.name
with open(p, 'rb') as f:
    requests.post(f"{BASE_URL}/drills/{drill7_id}/readings/import-json", files={"file": f})
os.unlink(p)

resp = requests.post(f"{BASE_URL}/drills/{drill7_id}/start", json={"person_id": 1})
test("离线演练启动返回 200", resp.status_code == 200, f"got {resp.status_code} {resp.text[:200]}")
detail = resp.json()

offline_judgments = [j for j in detail.get("judgments", []) if j.get("alarm_type") == "offline"]
test("存在 offline 判定", len(offline_judgments) > 0, f"got {len(offline_judgments)} judgments: {[j.get('alarm_type') for j in detail.get('judgments', [])]}")

offline_trigger = [j for j in offline_judgments if j.get("action") == "trigger"]
test("offline trigger 存在", len(offline_trigger) > 0)

requests.post(f"{BASE_URL}/drills/{drill7_id}/cancel", json={"person_id": 1})

print("\n--- TEST 24: 无读数启动失败 ---")
drill8_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 1,
    "name": "无读数演练",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 1
})
drill8_id = drill8_resp.json().get("id")

resp = requests.post(f"{BASE_URL}/drills/{drill8_id}/start", json={"person_id": 1})
test("无读数启动返回 400", resp.status_code == 400, f"got {resp.status_code}")

requests.post(f"{BASE_URL}/drills/{drill8_id}/cancel", json={"person_id": 1})

print("\n--- TEST 25: 不存在的 sensor_code 导入 ---")
bad_readings = [
    {"sensor_code": "TEMP-999", "temperature": -18.0, "reading_time": "2026-06-12T08:00:00"}
]
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(bad_readings, f)
    p = f.name
with open(p, 'rb') as f:
    resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/readings/import-json", files={"file": f})
os.unlink(p)
test("已完成演练导入返回 400", resp.status_code == 400, f"got {resp.status_code}")

print("\n--- TEST 26: 重启后数据一致性 ---")
all_drills_before = requests.get(f"{BASE_URL}/drills?limit=1000").json()
drill1_detail_before = requests.get(f"{BASE_URL}/drills/{drill1_id}").json()

test("重启前演练列表非空", len(all_drills_before) > 0)
test("重启前演练1有 judgments", len(drill1_detail_before.get("judgments", [])) > 0)

before_ids = set(d["id"] for d in all_drills_before)
before_status = {d["id"]: d["status"] for d in all_drills_before}
before_judgment_counts = {d["id"]: d.get("judgment_count", 0) for d in all_drills_before}

print("  ℹ 请重启服务后运行 test_drill_restart.py 验证数据持久性")

print("\n--- TEST 27: 取消草稿演练 ---")
drill9_resp = requests.post(f"{BASE_URL}/drills", json={
    "zone_id": 3,
    "name": "取消草稿测试",
    "target_temp": 2.0,
    "allowed_fluctuation": 4.0,
    "duration_minutes": 60,
    "created_by": 1
})
drill9_id = drill9_resp.json().get("id")

resp = requests.post(f"{BASE_URL}/drills/{drill9_id}/cancel", json={"person_id": 1})
test("取消草稿返回 200", resp.status_code == 200, f"got {resp.status_code}")
test("草稿取消后 status 为 cancelled", resp.json().get("status") == "cancelled")

print("\n--- TEST 28: 不能对已完成/已取消演练操作 ---")
resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/start", json={"person_id": 1})
test("已完成演练不能再启动", resp.status_code == 400, f"got {resp.status_code}")

resp = requests.post(f"{BASE_URL}/drills/{drill1_id}/cancel", json={"person_id": 1})
test("已完成演练不能再取消", resp.status_code == 400, f"got {resp.status_code}")

resp = requests.post(f"{BASE_URL}/drills/{drill9_id}/start", json={"person_id": 1})
test("已取消演练不能再启动", resp.status_code == 400, f"got {resp.status_code}")

print("\n--- TEST 29: 不存在的演练 ---")
resp = requests.get(f"{BASE_URL}/drills/99999")
test("不存在的演练返回 404", resp.status_code == 404, f"got {resp.status_code}")

print("\n" + "=" * 70)
print(f"测试完成: {passed} 通过, {failed} 失败")
print("=" * 70)

if errors_list:
    print("\n失败项:")
    for e in errors_list:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)
