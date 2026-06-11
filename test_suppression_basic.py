import urllib.request
import urllib.error
import json

BASE = 'http://localhost:8000'

def http_get(path):
    req = urllib.request.Request(f'{BASE}{path}')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode()), resp.status

def http_post(path, data):
    req = urllib.request.Request(
        f'{BASE}{path}',
        data=json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code

PASS = 0
FAIL = 0

def assert_eq(actual, expected, msg):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f'  [PASS] {msg}: {actual}')
    else:
        FAIL += 1
        print(f'  [FAIL] {msg}: 期望 {expected}, 实际 {actual}')

def assert_true(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  [PASS] {msg}')
    else:
        FAIL += 1
        print(f'  [FAIL] {msg}')

print('=' * 70)
print('TEST 1: Observer 不能创建抑制规则')
print('=' * 70)
result, status = http_post('/suppression-rules', {
    'sensor_id': 1,
    'start_time': '2026-06-12T00:00:00',
    'end_time': '2026-06-12T23:59:59',
    'reason': '设备检修',
    'created_by': 3
})
print(f'  Status: {status}, Detail: {result.get("detail", "")}')
assert_eq(status, 403, 'observer 创建应返回 403')

print()
print('=' * 70)
print('TEST 2: Operator 可以创建抑制规则')
print('=' * 70)
result, status = http_post('/suppression-rules', {
    'sensor_id': 1,
    'alarm_type': 'over_temp',
    'start_time': '2026-06-12T00:00:00',
    'end_time': '2026-06-12T23:59:59',
    'reason': '设备检修',
    'created_by': 2
})
print(f'  Status: {status}, Rule ID: {result.get("id", "N/A")}')
assert_eq(status, 200, 'operator 创建应成功')
rule_id_1 = result['id']
assert_eq(result['status'], 'active', '规则状态为 active')
assert_eq(result['sensor_id'], 1, 'sensor_id 正确')
assert_eq(result['alarm_type'], 'over_temp', 'alarm_type 正确')

print()
print('=' * 70)
print('TEST 3: 结束时间早于开始时间应报错')
print('=' * 70)
result, status = http_post('/suppression-rules', {
    'sensor_id': 2,
    'start_time': '2026-06-13T00:00:00',
    'end_time': '2026-06-12T00:00:00',
    'reason': '时间错误',
    'created_by': 2
})
print(f'  Status: {status}, Detail: {result.get("detail", "")}')
assert_eq(status, 400, '结束早于开始应返回 400')

print()
print('=' * 70)
print('TEST 4: 时间重叠冲突检测')
print('=' * 70)
result, status = http_post('/suppression-rules', {
    'sensor_id': 1,
    'alarm_type': 'over_temp',
    'start_time': '2026-06-12T12:00:00',
    'end_time': '2026-06-13T12:00:00',
    'reason': '冲突测试',
    'created_by': 2
})
print(f'  Status: {status}, Detail: {result.get("detail", "")}')
assert_eq(status, 409, '时间重叠应返回 409')

print()
print('=' * 70)
print('TEST 5: 导入超温读数应被抑制')
print('=' * 70)
result, status = http_post('/readings/import', [
    {'sensor_code': 'TEMP-001', 'temperature': -10.0, 'reading_time': '2026-06-12T10:00:00'}
])
print(f'  Status: {status}')
print(f'  Total: {result["total"]}, Successful: {result["successful"]}, Failed: {result["failed"]}')
print(f'  New alarms: {result["new_alarms"]}, Suppressed alarms: {result["suppressed_alarms"]}')
assert_eq(result['successful'], 1, '读数成功导入')
assert_eq(result['new_alarms'], 1, '产生 1 个新报警')
assert_eq(result['suppressed_alarms'], 1, '1 个报警被抑制')

print()
print('=' * 70)
print('TEST 6: 报警状态应为 suppressed 且关联规则')
print('=' * 70)
alarms, _ = http_get('/alarms?status=suppressed')
print(f'  Found {len(alarms)} suppressed alarms')
assert_true(len(alarms) >= 1, '至少有 1 个 suppressed 报警')
if alarms:
    alarm = alarms[0]
    print(f'  Alarm #{alarm["id"]}: type={alarm["alarm_type"]}, status={alarm["status"]}')
    print(f'  suppression_rule_id={alarm.get("suppression_rule_id")}')
    print(f'  suppression_rule_reason={alarm.get("suppression_rule_reason")}')
    assert_eq(alarm['status'], 'suppressed', '报警状态为 suppressed')
    assert_eq(alarm['suppression_rule_id'], rule_id_1, '关联正确的抑制规则')
    assert_eq(alarm['suppression_rule_reason'], '设备检修', '抑制原因正确')

print()
print('=' * 70)
print('TEST 7: 抑制命中日志存在')
print('=' * 70)
hits, status = http_get(f'/suppression-rules/{rule_id_1}/hits')
print(f'  Status: {status}, Hit count: {len(hits)}')
assert_eq(status, 200, '获取命中日志成功')
assert_true(len(hits) >= 1, '至少有 1 条命中记录')
if hits:
    hit = hits[0]
    print(f'  Hit #{hit["id"]}: alarm_id={hit["alarm_id"]}, alarm_type={hit["alarm_type"]}')
    assert_eq(hit['rule_id'], rule_id_1, '命中记录关联正确的规则')
    assert_eq(hit['alarm_type'], 'over_temp', '命中记录类型正确')

print()
print('=' * 70)
print('TEST 8: 撤销抑制规则后恢复报警触发')
print('=' * 70)
# 先撤销规则
result, status = http_post(f'/suppression-rules/{rule_id_1}/revoke', {'person_id': 2})
print(f'  Revoke status: {status}')
assert_eq(status, 200, '撤销成功')
assert_eq(result['status'], 'revoked', '规则状态为 revoked')

# 再导入一个更晚时间的超温读数（去重窗口外）
result2, status2 = http_post('/readings/import', [
    {'sensor_code': 'TEMP-001', 'temperature': -9.0, 'reading_time': '2026-06-13T10:00:00'}
])
print(f'  Import status: {status2}')
print(f'  New alarms: {result2["new_alarms"]}, Suppressed: {result2["suppressed_alarms"]}')
assert_eq(result2['successful'], 1, '读数导入成功')
assert_true(result2['new_alarms'] >= 1, '撤销后应产生新的 open 报警')

# 检查新报警状态
alarms2, _ = http_get('/alarms?status=open')
over_temp_alarms = [a for a in alarms2 if a['alarm_type'] == 'over_temp' and a['sensor_code'] == 'TEMP-001']
print(f'  TEMP-001 的 open 超温报警: {len(over_temp_alarms)} 个')
assert_true(len(over_temp_alarms) >= 1, '撤销后有 open 状态的超温报警')

print()
print('=' * 70)
print(f'测试汇总: 通过={PASS}, 失败={FAIL}')
print('=' * 70)

if FAIL == 0:
    print('\n[OK] 所有基础测试通过!')
else:
    print(f'\n[FAIL] 有{FAIL}个测试失败。')
    exit(1)
