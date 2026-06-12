"""
交接班巡检清单跨服务重启一致性验证
在运行 test_shift_checklist.py 后，重启服务，再运行此脚本验证数据持久化。
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
print("交接班巡检清单跨服务重启一致性验证")
print("=" * 70)

print("\n--- 1. 验证清单数据完整保留 ---")
checklists, _ = http_get_json("/shift-checklists")
assert_true(len(checklists) >= 3, f"清单数量 >= 3 (实际{len(checklists)})")

for c in checklists:
    detail, _ = http_get_json(f"/shift-checklists/{c['id']}")
    assert_true(detail is not None, f"清单{c['id']}详情可获取")
    assert_true("sensor_items" in detail, f"清单{c['id']}包含 sensor_items")
    assert_true("manual_items" in detail, f"清单{c['id']}包含 manual_items")
    assert_true(len(detail["sensor_items"]) >= 1, f"清单{c['id']}至少有1个传感器检查项")
    assert_true(len(detail["manual_items"]) >= 5, f"清单{c['id']}至少有5个手动检查项")

print("\n--- 2. 验证已提交清单状态持久化 ---")
submitted = [c for c in checklists if c["status"] == "submitted"]
assert_true(len(submitted) >= 1, f"至少有1个已提交清单 (实际{len(submitted)})")
for c in submitted:
    assert_true(c["submitted_by"] is not None, f"清单{c['id']} submitted_by 不为空")
    assert_true(c["submitter_name"] is not None, f"清单{c['id']} submitter_name 不为空")

print("\n--- 3. 验证已撤回清单状态持久化 ---")
revoked = [c for c in checklists if c["status"] == "revoked"]
if revoked:
    for c in revoked:
        assert_true(c["revoked_by"] is not None, f"清单{c['id']} revoked_by 不为空")
        assert_true(c["revoker_name"] is not None, f"清单{c['id']} revoker_name 不为空")

print("\n--- 4. 验证检查项快照数据不被后续操作改写 ---")
for c in checklists:
    detail, _ = http_get_json(f"/shift-checklists/{c['id']}")
    for si in detail.get("sensor_items", []):
        assert_true(si["snapshot_threshold_upper"] is not None,
                    f"清单{c['id']} 传感器{si.get('sensor_code', '?')} 阈值上限快照保留")
        assert_true(si["snapshot_threshold_lower"] is not None,
                    f"清单{c['id']} 传感器{si.get('sensor_code', '?')} 阈值下限快照保留")

print("\n--- 5. 验证检查结果和处理人信息持久化 ---")
for c in checklists:
    detail, _ = http_get_json(f"/shift-checklists/{c['id']}")
    for si in detail.get("sensor_items", []):
        if si["check_status"] != "pending":
            assert_true(si["checked_by"] is not None,
                        f"清单{c['id']} 传感器{si.get('sensor_code', '?')} checked_by 保留")
            assert_true(si["checked_at"] is not None,
                        f"清单{c['id']} 传感器{si.get('sensor_code', '?')} checked_at 保留")
    for mi in detail.get("manual_items", []):
        if mi["check_status"] != "pending":
            assert_true(mi["checked_by"] is not None,
                        f"清单{c['id']} 检查项'{mi['item_name']}' checked_by 保留")
            assert_true(mi["checked_at"] is not None,
                        f"清单{c['id']} 检查项'{mi['item_name']}' checked_at 保留")
        if mi["abnormal_remark"]:
            assert_true(mi["handler_id"] is not None,
                        f"清单{c['id']} 检查项'{mi['item_name']}' 有异常备注时处理人保留")

print("\n--- 6. 验证报警快照内部一致性 ---")
for c in checklists:
    detail, _ = http_get_json(f"/shift-checklists/{c['id']}")
    for si in detail.get("sensor_items", []):
        if si["snapshot_open_alarm_ids"]:
            alarm_ids = json.loads(si["snapshot_open_alarm_ids"])
            assert_eq(si["snapshot_open_alarm_count"], len(alarm_ids),
                      f"清单{c['id']} 传感器{si.get('sensor_code', '?')} 报警数与ID列表一致")
        else:
            assert_eq(si["snapshot_open_alarm_count"], 0,
                      f"清单{c['id']} 传感器{si.get('sensor_code', '?')} 无报警时count=0")

print("\n--- 7. 验证 CSV/JSON 导出跨重启一致 ---")
csv_text, s_csv = http_get("/shift-checklists/export.csv")
assert_eq(s_csv, 200, "CSV 导出成功")
csv_reader = csv.reader(io.StringIO(csv_text))
csv_rows = list(csv_reader)
assert_eq(len(csv_rows) - 1, len(checklists), "CSV 数据行数 = API 返回清单数")

json_text, s_json = http_get("/shift-checklists/export.json")
assert_eq(s_json, 200, "JSON 导出成功")
json_data = json.loads(json_text)
assert_eq(len(json_data), len(checklists), "JSON 数据条数 = API 返回清单数")

print("\n--- 8. 验证筛选功能跨重启正常 ---")
r_zone, _ = http_get_json(f"/shift-checklists?zone_id={checklists[0]['zone_id']}")
assert_true(len(r_zone) >= 1, "按库区筛选正常")

r_status, _ = http_get_json("/shift-checklists?status=submitted")
assert_true(len(r_status) >= 1, "按状态筛选正常")

print()
print("=" * 70)
print(f"跨重启一致性验证汇总: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 交接班巡检清单跨重启一致性验证全部通过！")
else:
    print(f"\n[FAIL] 有 {FAIL} 个测试失败。")
    exit(1)
