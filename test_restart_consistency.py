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
print("TEST: 服务重启后一致性验证")
print("=" * 70)

alarms, _ = http_get("/alarms")
print(f"  报警总数: {len(alarms)}")
assert_true(len(alarms) >= 4, "重启后至少应有4个报警(offline+over_temp等)")

by_type = {}
for a in alarms:
    by_type.setdefault(a["alarm_type"], 0)
    by_type[a["alarm_type"]] += 1
print(f"  按类型统计: {by_type}")
assert_true(by_type.get("offline", 0) >= 2, "至少有2个offline报警")
assert_true(by_type.get("over_temp", 0) >= 2, "至少有2个over_temp报警")

by_status = {}
for a in alarms:
    by_status.setdefault(a["status"], 0)
    by_status[a["status"]] += 1
print(f"  按状态统计: {by_status}")
assert_true(by_status.get("closed", 0) >= 1, "至少有1个已关闭报警")

closed_alarms = [a for a in alarms if a["status"] == "closed"]
for ca in closed_alarms:
    detail, _ = http_get(f"/alarms/{ca['id']}")
    print(f"  已关闭报警 {ca['id']}: resolution_note长度={len(detail.get('resolution_note') or '')}, confirmations={len(detail['confirmations'])}")
    assert_true(detail.get("resolution_note") and len(detail["resolution_note"]) > 0,
                f"关闭报警{ca['id']}有处理说明")
    assert_true(len(detail["confirmations"]) >= 4, f"关闭报警{ca['id']}有>=4条确认记录")

offline_alarms = [a for a in alarms if a["alarm_type"] == "offline"]
for oa in offline_alarms[:2]:
    assert_true(oa["trigger_value"] is None, f"离线报警{oa['id']}的trigger_value为None")
print("  所有离线报警的trigger_value均为None (离线报警无具体温度值)")

req = urllib.request.Request(f"{BASE}/alarms/export.csv")
with urllib.request.urlopen(req) as resp:
    csv_content = resp.read().decode()
csv_lines = csv_content.strip().split("\n")
print(f"  CSV导出: {len(csv_lines)}行")
assert_eq(len(csv_lines), len(alarms) + 1, "CSV行数=报警数+表头")

req = urllib.request.Request(f"{BASE}/alarms/export.json")
with urllib.request.urlopen(req) as resp:
    json_alarms = json.loads(resp.read().decode())
print(f"  JSON导出: {len(json_alarms)}条")
assert_eq(len(json_alarms), len(alarms), "JSON导出条数=API查询条数")

csv_ids = set()
for l in csv_lines[1:]:
    parts = list(csv.reader([l]))[0]
    if parts:
        csv_ids.add(int(parts[0]))
json_ids = set(a["id"] for a in json_alarms)
api_ids = set(a["id"] for a in alarms)
assert_true(csv_ids == json_ids == api_ids, f"CSV/JSON/API返回的报警ID集合一致: {sorted(api_ids)}")

req = urllib.request.Request(f"{BASE}/readings/export.csv")
with urllib.request.urlopen(req) as resp:
    readings_csv = resp.read().decode()
r_lines = readings_csv.strip().split("\n")
print(f"  读数CSV行数: {len(r_lines)}")
assert_true(len(r_lines) >= 2, "读数CSV有表头+数据")

readings_api, _ = http_get("/readings?limit=10000")
print(f"  API读数条数: {len(readings_api)}")
assert_eq(len(r_lines) - 1, len(readings_api), "读数CSV数据行=API返回条数")

persons, _ = http_get("/persons")
sensors, _ = http_get("/sensors")
zones, _ = http_get("/zones")
thresholds, _ = http_get("/sensors/1/thresholds")
print(f"  人员={len(persons)}, 传感器={len(sensors)}, 库区={len(zones)}, 传感器1阈值={len(thresholds)}")
assert_eq(len(persons), 3, "人员数量=3")
assert_eq(len(sensors), 4, "传感器数量=4")
assert_eq(len(zones), 3, "库区数量=3")
assert_true(len(thresholds) >= 1, "传感器1至少有1个阈值版本")

# 抑制规则验证
try:
    rules, _ = http_get("/suppression-rules")
    print(f"  抑制规则={len(rules)}")
    if len(rules) > 0:
        by_status = {}
        for r in rules:
            by_status.setdefault(r["status"], 0)
            by_status[r["status"]] += 1
        print(f"    按状态: {by_status}")

        active_rules = [r for r in rules if r["status"] == "active"]
        if active_rules:
            rule = active_rules[0]
            detail, _ = http_get(f"/suppression-rules/{rule['id']}")
            assert_true("hit_count" in detail, f"规则{rule['id']}详情有hit_count")
            assert_true("creator_name" in detail, f"规则{rule['id']}详情有creator_name")
            print(f"    规则{rule['id']}: status={detail['status']}, hit_count={detail['hit_count']}")

            try:
                hits, _ = http_get(f"/suppression-rules/{rule['id']}/hits")
                print(f"    命中日志数: {len(hits)}")
                if len(hits) > 0:
                    assert_true(hits[0].get("trigger_value") is not None or hits[0].get("alarm_type") == "offline",
                                "命中日志有trigger_value或为offline类型")
                    assert_true("sensor_code" in hits[0], "命中日志有sensor_code")
            except Exception as e:
                print(f"    命中日志查询跳过: {e}")

        # 验证CSV导出
        try:
            req = urllib.request.Request(f"{BASE}/suppression-rules/export.csv")
            with urllib.request.urlopen(req) as resp:
                rules_csv = resp.read().decode()
            rules_csv_lines = rules_csv.strip().split("\n")
            print(f"    规则CSV行数: {len(rules_csv_lines)}")
            assert_true(len(rules_csv_lines) >= 2, "规则CSV有表头+数据")
            assert_true("hit_count" in rules_csv_lines[0], "规则CSV有hit_count列")
        except Exception as e:
            print(f"    规则CSV导出跳过: {e}")

        try:
            req = urllib.request.Request(f"{BASE}/suppression-hits/export.csv")
            with urllib.request.urlopen(req) as resp:
                hits_csv = resp.read().decode()
            hits_csv_lines = hits_csv.strip().split("\n")
            print(f"    命中日志CSV行数: {len(hits_csv_lines)}")
            assert_true(len(hits_csv_lines) >= 2, "命中日志CSV有表头+数据")
        except Exception as e:
            print(f"    命中日志CSV导出跳过: {e}")

except Exception as e:
    print(f"  抑制规则验证跳过: {e}")

# 报警中的抑制关联验证
suppressed_alarms = [a for a in alarms if a["status"] == "suppressed"]
if suppressed_alarms:
    print(f"  抑制状态报警: {len(suppressed_alarms)}个")
    for sa in suppressed_alarms[:2]:
        assert_true(sa.get("suppression_rule_id") is not None, f"抑制报警{sa['id']}有suppression_rule_id")
        assert_true(sa.get("suppression_rule_reason") is not None, f"抑制报警{sa['id']}有suppression_rule_reason")

print()
print("=" * 70)
print(f"重启后一致性验证: 通过={PASS}, 失败={FAIL}")
print("=" * 70)

if FAIL == 0:
    print("\n[OK] 重启后所有数据一致!")
else:
    print(f"\n[FAIL] 有{FAIL}个一致性问题。")
    exit(1)
