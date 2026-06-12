import requests
import json
import sys

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


print("=" * 70)
print("温控策略演练 — 重启后一致性验证")
print("=" * 70)

print("\n--- 验证演练数据跨重启持久化 ---")

resp = requests.get(f"{BASE_URL}/drills?limit=1000")
test("获取演练列表返回 200", resp.status_code == 200, f"got {resp.status_code}")
drills = resp.json()
test("演练列表非空", len(drills) > 0, "no drills found - run test_drill.py first")

completed_drills = [d for d in drills if d.get("status") == "completed"]
running_drills = [d for d in drills if d.get("status") == "running"]
cancelled_drills = [d for d in drills if d.get("status") == "cancelled"]

test(f"已完成演练数量 >= 1", len(completed_drills) >= 1, f"got {len(completed_drills)}")
test(f"已取消演练数量 >= 1", len(cancelled_drills) >= 1, f"got {len(cancelled_drills)}")

if completed_drills:
    drill_id = completed_drills[0]["id"]

    resp = requests.get(f"{BASE_URL}/drills/{drill_id}")
    test("获取已完成演练详情返回 200", resp.status_code == 200)
    detail = resp.json()

    test("status 为 completed", detail.get("status") == "completed")
    test("judgments 非空", len(detail.get("judgments", [])) > 0)
    test("alarm_changes 非空", len(detail.get("alarm_changes", [])) > 0)
    test("operation_logs 非空", len(detail.get("operation_logs", [])) > 0)
    test("config_snapshot 不为空", detail.get("config_snapshot") is not None)
    test("started_at 不为空", detail.get("started_at") is not None)
    test("completed_at 不为空", detail.get("completed_at") is not None)

    first_judgment = detail["judgments"][0] if detail["judgments"] else {}
    test("judgment 包含 sensor_code", "sensor_code" in first_judgment)
    test("judgment 包含 action", "action" in first_judgment)
    test("judgment 包含 temperature", "temperature" in first_judgment)

    first_change = detail["alarm_changes"][0] if detail["alarm_changes"] else {}
    test("alarm_change 包含 change_type", "change_type" in first_change)
    test("alarm_change 包含 sensor_code", "sensor_code" in first_change)

    first_log = detail["operation_logs"][0] if detail["operation_logs"] else {}
    test("operation_log 包含 action", "action" in first_log)
    test("operation_log 包含 operator_name", "operator_name" in first_log)

    resp = requests.get(f"{BASE_URL}/drills/{drill_id}/export.json")
    test("导出 JSON 返回 200", resp.status_code == 200)
    export_data = resp.json()

    export_j_ids = set(j["id"] for j in export_data.get("judgments", []))
    api_j_ids = set(j["id"] for j in detail.get("judgments", []))
    test("导出与 API judgment IDs 一致", export_j_ids == api_j_ids)

    export_ac_ids = set(ac["id"] for ac in export_data.get("alarm_changes", []))
    api_ac_ids = set(ac["id"] for ac in detail.get("alarm_changes", []))
    test("导出与 API alarm_change IDs 一致", export_ac_ids == api_ac_ids)

if cancelled_drills:
    drill_id = cancelled_drills[0]["id"]
    resp = requests.get(f"{BASE_URL}/drills/{drill_id}")
    test("获取已取消演练详情返回 200", resp.status_code == 200)
    detail = resp.json()
    test("已取消演练 status 为 cancelled", detail.get("status") == "cancelled")
    test("cancelled_at 不为空", detail.get("cancelled_at") is not None)

print("\n--- 验证演练不影响真实报警 ---")
alarms_resp = requests.get(f"{BASE_URL}/alarms?limit=1000")
test("获取真实报警返回 200", alarms_resp.status_code == 200)

readings_resp = requests.get(f"{BASE_URL}/readings?limit=1000")
test("获取真实读数返回 200", readings_resp.status_code == 200)

print("\n" + "=" * 70)
print(f"重启验证完成: {passed} 通过, {failed} 失败")
print("=" * 70)

if errors_list:
    print("\n失败项:")
    for e in errors_list:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)
