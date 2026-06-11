import urllib.request
import json

BASE_URL = "http://localhost:8000"

def http_get(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode()), resp.status

print("=" * 70)
print("跨重启一致性验证")
print("=" * 70)

rules, s = http_get('/suppression-rules')
print(f"\n抑制规则总数: {len(rules)}")
active_rules = [r for r in rules if r['status'] == 'active']
revoked_rules = [r for r in rules if r['status'] == 'revoked']
print(f"  active: {len(active_rules)}, revoked: {len(revoked_rules)}")

rule5 = None
for r in rules:
    if r['id'] == 5:
        rule5 = r
        break

if rule5:
    print(f"\n规则5详情:")
    print(f"  id: {rule5['id']}")
    print(f"  status: {rule5['status']}")
    print(f"  reason: {rule5['reason']}")
    print(f"  hit_count: {rule5['hit_count']}")

hits, s = http_get('/suppression-rules/5/hits')
print(f"\n规则5的命中日志数: {len(hits)}")
if hits:
    print(f"  第一条: id={hits[0]['id']}, alarm_type={hits[0]['alarm_type']}, trigger_value={hits[0]['trigger_value']}")

alarms, s = http_get('/alarms?status=suppressed')
print(f"\nsuppressed状态报警数: {len(alarms)}")
if alarms:
    print(f"  第一条: id={alarms[0]['id']}, type={alarms[0]['alarm_type']}, rule_id={alarms[0].get('suppression_rule_id')}")

print("\n" + "=" * 70)
print("验证完成 - 请在重启服务后再次运行此脚本")
print("=" * 70)
