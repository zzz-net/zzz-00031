# 冷库温控报警确认 API 服务

本地运行的冷库温度监控报警管理系统，支持传感器阈值配置、温度读数导入、超温/离线报警识别、报警状态流转及数据导出。

## 技术栈

- **后端框架**: FastAPI
- **数据库**: SQLite (文件存储: `cold_storage.db`)
- **ORM**: SQLAlchemy

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化样例数据

```bash
python init_data.py
```

### 3. 启动服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后访问:
- API 文档: http://localhost:8000/docs
- 根路径: http://localhost:8000

## 核心概念

### 角色权限

| 角色 | 权限 |
|------|------|
| `admin` | 所有操作，包括关闭报警、管理抑制规则、管理巡检模板、生成巡检工单 |
| `operator` | 确认、处理中、升级、关闭报警、管理抑制规则、领取/填写/完成巡检工单 |
| `observer` | 仅查看，不能操作报警、不能创建/撤销抑制规则、不能管理巡检模板和工单 |

### 报警状态

| 状态 | 说明 |
|------|------|
| `open` | 新产生的报警，未确认 |
| `acknowledged` | 值班人员已确认 |
| `processing` | 处理中 |
| `escalated` | 已升级到上级 |
| `suppressed` | 已抑制（临时屏蔽） |
| `closed` | 已关闭（需处理说明） |

### 报警类型

| 类型 | 说明 |
|------|------|
| `over_temp` | 超高温报警（温度 > 上限） |
| `under_temp` | 超低温报警（温度 < 下限） |
| `offline` | 离线报警（两次读数间隔超过传感器 `offline_timeout_minutes`） |

### 关键规则

1. **乱序保护**: 同一传感器的乱序读数（reading_time 早于已入库读数的最新时间）在写入前被拒绝，不入库，计入 failed 和 errors 列表
2. **去重窗口**: 在去重窗口内，连续高温/低温只更新同一个报警
3. **权限控制**: 观察者(observer)不能确认、关闭或升级报警，也不能管理抑制规则
4. **关闭说明**: 关闭报警必须提供处理说明，缺少时返回 HTTP 400
5. **离线检测**: 当一条读数的 reading_time 距该传感器上一条读数超过 `offline_timeout_minutes`（默认30分钟）时，自动产生一条 `offline` 类型报警，触发时间为上次读数时间 + 超时阈值
6. **抑制规则**: 只能通过 `/suppression-rules` 创建规则化抑制，禁止直接把报警改成 suppressed。抑制期间读数正常入库，报警状态为 suppressed，关联规则ID并生成命中日志。

## API 示例 (curl)

以下示例假设服务运行在 `http://localhost:8000`。

---

### 一、配置管理

#### 1. 查看库区列表

```bash
curl -X GET http://localhost:8000/zones
```

#### 2. 新增库区

```bash
curl -X POST http://localhost:8000/zones \
  -H "Content-Type: application/json" \
  -d '{"name": "测试库区D", "description": "测试用冷库区域"}'
```

#### 3. 查看人员列表

```bash
curl -X GET http://localhost:8000/persons
```

#### 4. 新增值班人员

```bash
curl -X POST http://localhost:8000/persons \
  -H "Content-Type: application/json" \
  -d '{"name": "赵运营", "role": "operator", "phone": "13900000001"}'
```

#### 5. 查看传感器列表

```bash
curl -X GET http://localhost:8000/sensors
```

#### 6. 新增传感器

```bash
curl -X POST http://localhost:8000/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "code": "TEMP-005",
    "name": "D区新传感器",
    "zone_id": 1,
    "is_active": true,
    "offline_timeout_minutes": 30
  }'
```

#### 7. 配置阈值版本

```bash
curl -X POST http://localhost:8000/thresholds \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "upper_limit": -15.0,
    "lower_limit": -25.0,
    "dedup_window_minutes": 60,
    "effective_from": "2026-06-01T00:00:00"
  }'
```

#### 8. 查看传感器阈值历史

```bash
curl -X GET http://localhost:8000/sensors/1/thresholds
```

---

### 二、导入温度读数

#### 方式1: JSON 数组直接导入

```bash
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[
    {"sensor_code": "TEMP-001", "temperature": -18.5, "reading_time": "2026-06-12T08:00:00"},
    {"sensor_code": "TEMP-001", "temperature": -14.0, "reading_time": "2026-06-12T08:30:00"},
    {"sensor_code": "TEMP-001", "temperature": -12.5, "reading_time": "2026-06-12T09:00:00"}
  ]'
```

#### 方式2: JSON 文件导入

```bash
curl -X POST http://localhost:8000/readings/import-json \
  -F "file=@examples/readings_sample.json"
```

#### 方式3: CSV 文件导入

```bash
curl -X POST http://localhost:8000/readings/import-csv \
  -F "file=@examples/readings_sample.csv"
```

#### 查看读数列表

```bash
curl -X GET "http://localhost:8000/readings?sensor_id=1&limit=10"
```

---

### 三、报警管理

#### 1. 查看所有报警

```bash
curl -X GET http://localhost:8000/alarms
```

#### 2. 按状态筛选报警

```bash
curl -X GET "http://localhost:8000/alarms?status=open"
```

#### 3. 查看报警详情

```bash
curl -X GET http://localhost:8000/alarms/1
```

---

### 四、报警状态流转

#### 1. 确认报警 (值班确认)

```bash
curl -X POST http://localhost:8000/alarms/1/acknowledge \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "note": "李值班已收到报警，正在赶往现场"}'
```

#### 2. 标记处理中

```bash
curl -X POST http://localhost:8000/alarms/1/processing \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "note": "正在检查制冷设备"}'
```

#### 3. 升级报警

```bash
curl -X POST http://localhost:8000/alarms/1/escalate \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "note": "设备故障严重，需联系维修"}'
```

#### 4. 关闭报警（需处理说明）

```bash
curl -X POST http://localhost:8000/alarms/1/close \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1, "resolution_note": "制冷设备已修复，温度恢复正常范围"}'
```

---

### 五、失败路径验证

#### 1. 观察者不能关闭报警

```bash
curl -X POST http://localhost:8000/alarms/1/close \
  -H "Content-Type: application/json" \
  -d '{"person_id": 3, "resolution_note": "我想关闭报警"}'
```

预期结果: 返回 400 错误，提示 "Permission denied: only admin or operator can close alarms"

#### 2. 关闭时缺少处理说明

```bash
curl -X POST http://localhost:8000/alarms/1/close \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果: 返回 400 错误，提示 "Resolution note is required to close an alarm"

#### 3. 乱序读数被拒绝（不入库）

先导入一组正常读数:
```bash
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -18.0, "reading_time": "2026-06-12T10:00:00"}]'
```

再导入更早时间的乱序读数:
```bash
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -19.0, "reading_time": "2026-06-12T09:30:00"}]'
```

预期结果: 返回 successful=0, failed=1, errors 列表包含 "out-of-order rejected"。乱序读数不会被写入数据库，也不会影响报警状态。批量导入时, rejected/failed 的计数与 errors 列表长度完全一致。

#### 4. 去重窗口内连续高温只更新一个报警

导入去重窗口内的多个超温读数:
```bash
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[
    {"sensor_code": "TEMP-003", "temperature": 7.0, "reading_time": "2026-06-12T11:00:00"},
    {"sensor_code": "TEMP-003", "temperature": 7.5, "reading_time": "2026-06-12T11:10:00"},
    {"sensor_code": "TEMP-003", "temperature": 8.0, "reading_time": "2026-06-12T11:20:00"}
  ]'
```

预期结果: 去重窗口内只产生 1 个报警，后续读数只更新最新温度值

---

### 六、数据导出

#### 1. 导出报警为 CSV

```bash
curl -X GET "http://localhost:8000/alarms/export.csv" -o alarms.csv
```

#### 2. 导出报警为 JSON

```bash
curl -X GET "http://localhost:8000/alarms/export.json" -o alarms.json
```

#### 3. 按状态筛选导出

```bash
curl -X GET "http://localhost:8000/alarms/export.csv?status=closed" -o closed_alarms.csv
```

#### 4. 导出温度读数为 CSV

```bash
curl -X GET "http://localhost:8000/readings/export.csv" -o readings.csv
```

---

### 七、离线报警触发示例

传感器配置了 `offline_timeout_minutes`（默认 30 分钟）后，若一条读数距上次读数超时，将自动生成 `offline` 报警。

```bash
# 第一次导入：建立基准读数
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-002", "temperature": -22.0, "reading_time": "2026-06-12T08:00:00"}]'

# 2 小时后再导入一条正常温度读数（间隔已远超 30 分钟阈值）
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-002", "temperature": -22.5, "reading_time": "2026-06-12T10:00:00"}]'
```

预期结果：第二次导入应产生 1 个新报警（类型 `offline`，触发时间 = 上次读数时间 08:00 + 30min = 08:30），尽管读数值本身在正常范围内。

---

### 八、报警静音计划（抑制规则）

值班人员可给指定传感器或库区设置**临时静音窗口**（也叫抑制规则）。窗口内读数仍正常入库，但符合静音条件的报警不会变成 `open` 进入待处理列表，而是标记为 `suppressed`，同时生成命中日志（suppression_hits）记录触发值、时间和关联的静音计划，全程可追溯。

#### 静音计划属性

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sensor_id` | int | 否 | 按传感器静音（与 zone_id 二选一或同时） |
| `zone_id` | int | 否 | 按库区静音（与 sensor_id 二选一或同时） |
| `alarm_type` | str | 否 | 按报警类型静音：`over_temp` / `under_temp` / `offline`，留空表示全部 |
| `start_time` | datetime | 是 | 静音窗口开始时间 |
| `end_time` | datetime | 是 | 静音窗口结束时间，必须晚于 start_time |
| `reason` | str | 是 | 静音原因，如"设备检修"、"库区维护" |
| `created_by` | int | 是 | 创建人 ID（必须是 admin 或 operator） |

#### 约束条件

- **禁止时间重叠**：相同范围（传感器/库区/类型有交集）的 active 规则不能时间重叠
- **禁止结束早于开始**：`end_time` 必须严格大于 `start_time`
- **至少一个范围**：`sensor_id` 和 `zone_id` 不能同时为空
- **权限约束**：只有 admin 和 operator 可以创建/撤销静音计划，observer 只能查看
- **审计追踪**：每条 suppressed 报警都有对应 suppression_rule_id 和命中日志
- **到期自动恢复**：窗口结束后新异常读数正常生成 open 报警
- **撤销恢复**：撤销规则后新异常读数正常生成 open 报警
- **统一命中逻辑**：JSON 导入、CSV 导入、直接提交读数走同一套命中逻辑

#### 1. 创建静音计划（按传感器 + 类型）

```bash
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "alarm_type": "over_temp",
    "start_time": "2026-06-15T00:00:00",
    "end_time": "2026-06-15T23:59:59",
    "reason": "传感器检修",
    "created_by": 1
  }'
```

预期结果：返回 200，包含规则详情（status=active）。

#### 2. 创建静音计划（按库区，全部类型）

```bash
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "start_time": "2026-06-16T00:00:00",
    "end_time": "2026-06-16T23:59:59",
    "reason": "库区整体维护",
    "created_by": 2
  }'
```

#### 3. 查看静音计划列表

```bash
# 全部规则
curl -X GET http://localhost:8000/suppression-rules

# 按状态筛选
curl -X GET "http://localhost:8000/suppression-rules?status=active"

# 按传感器筛选
curl -X GET "http://localhost:8000/suppression-rules?sensor_id=1"
```

#### 4. 查看静音计划详情

```bash
curl -X GET http://localhost:8000/suppression-rules/1
```

预期结果：包含规则信息、创建人姓名、命中次数（hit_count）等。

#### 5. 撤销静音计划

```bash
curl -X POST http://localhost:8000/suppression-rules/1/revoke \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：返回 200，规则状态变为 revoked。撤销后新异常读数会正常生成 open 报警。

#### 6. 查看静音命中日志

```bash
curl -X GET http://localhost:8000/suppression-rules/1/hits
```

预期结果：每条命中包含 rule_id、alarm_id、sensor_code、alarm_type、trigger_value、trigger_time。

#### 7. 导出静音计划 CSV

```bash
curl -X GET "http://localhost:8000/suppression-rules/export.csv" -o suppression_rules.csv
```

#### 8. 导出静音命中日志 CSV

```bash
curl -X GET "http://localhost:8000/suppression-hits/export.csv" -o suppression_hits.csv
```

#### 9. 失败场景

##### 场景 1：observer 不能创建静音计划（403）

```bash
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-06-18T00:00:00",
    "end_time": "2026-06-18T23:59:59",
    "reason": "observer尝试创建",
    "created_by": 3
  }'
```

预期结果：返回 403，提示 "Permission denied: only admin or operator can create suppression rules"

##### 场景 2：observer 不能撤销静音计划（403）

```bash
curl -X POST http://localhost:8000/suppression-rules/1/revoke \
  -H "Content-Type: application/json" \
  -d '{"person_id": 3}'
```

预期结果：返回 403，提示 "Permission denied: only admin or operator can revoke suppression rules"

##### 场景 3：结束时间早于开始时间（400）

```bash
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-06-19T12:00:00",
    "end_time": "2026-06-19T10:00:00",
    "reason": "时间错误",
    "created_by": 1
  }'
```

预期结果：返回 400，提示 "End time must be after start time"

##### 场景 4：缺少 sensor_id 和 zone_id（400）

```bash
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2026-06-20T00:00:00",
    "end_time": "2026-06-20T23:59:59",
    "reason": "缺少范围",
    "created_by": 1
  }'
```

预期结果：返回 400，提示 "Either sensor_id or zone_id must be provided"

##### 场景 5：时间重叠冲突（409）

```bash
# 先创建一条 active 规则
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-06-21T00:00:00",
    "end_time": "2026-06-21T23:59:59",
    "reason": "测试冲突1",
    "created_by": 1
  }'

# 再创建一条时间重叠的同范围规则
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-06-21T12:00:00",
    "end_time": "2026-06-22T12:00:00",
    "reason": "测试冲突2",
    "created_by": 1
  }'
```

预期结果：第二条返回 409 Conflict，提示与现有规则冲突。

##### 场景 6：旧手工抑制端点已移除（404）

```bash
curl -X POST http://localhost:8000/alarms/1/suppress \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1, "note": "尝试旧抑制", "suppress_minutes": 60}'
```

预期结果：返回 404（或 405/400），旧端点已被移除，只能通过静音计划实现抑制。

#### 10. 完整流程示例：传感器检修静音

```bash
# 步骤1: operator 创建按传感器的静音计划（24小时窗口）
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-07-01T00:00:00",
    "end_time": "2026-07-01T23:59:59",
    "reason": "TEMP-001传感器年度校准检修",
    "created_by": 2
  }'

# 步骤2: 导入超温读数（在静音窗口内）
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2026-07-01T10:00:00"}]'

# 预期: successful=1, suppressed_alarms=1，读数正常入库，报警被静音

# 步骤3: 查看被静音的报警
curl -X GET "http://localhost:8000/alarms?status=suppressed"

# 步骤4: 查看静音命中日志
curl -X GET http://localhost:8000/suppression-rules/1/hits

# 步骤5: 提前完成检修，撤销静音计划
curl -X POST http://localhost:8000/suppression-rules/1/revoke \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2}'

# 步骤6: 撤销后再导入超温读数，应产生正常 open 报警
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -9.0, "reading_time": "2026-07-01T14:00:00"}]'

# 预期: new_alarms>=1, suppressed_alarms=0，新报警为 open 状态
```

---

## 自动化测试

项目包含 5 个 Python 测试脚本，用于回归验证所有用户可见行为。

### 1. 复现与回归测试（修复项验证）

```bash
python test_alarm_fixes.py
```

覆盖内容:
- **TEST 1**: 离线报警链路 — 导入超时后的正常读数应产生 `offline` 报警
- **TEST 2**: 乱序读数拒绝 — 写入前校验, `successful`/`failed`/`errors` 对得上, 乱序数据不入库
- **TEST 3**: 关闭报警缺 `resolution_note` 返回 **400**（与 README 一致，非 422）；观察者无权限操作
- **TEST 4**: 完整报警生命周期（确认→处理→升级→关闭）+ 去重窗口 + 处理说明/确认记录留存
- **TEST 5**: 报警 CSV/JSON 导出，ID 集合与 API 查询完全一致

### 2. 报警抑制规则综合测试

```bash
python test_suppression_comprehensive.py
```

覆盖内容:
- 权限验证（observer 不能创建/撤销抑制规则）
- 时间验证（结束早于开始、时间重叠冲突）
- 按传感器/库区/报警类型抑制
- 撤销抑制后恢复触发
- 抑制到期后恢复触发
- 抑制命中日志审计
- 导入统计一致（JSON/CSV/直接导入都有 suppressed_alarms）
- CSV 导出（规则、命中日志、报警）

### 3. 重启后一致性验证

```bash
# 先运行一轮综合测试产生数据
python test_suppression_comprehensive.py

# 重启服务（停止后再启动）
# 方式1：如果用 --reload 模式，修改任意 .py 文件保存即可自动重启
# 方式2：手动停止 uvicorn 后重新启动
uvicorn main:app --host 0.0.0.0 --port 8000

# 等待服务启动后运行一致性验证
python test_restart_consistency.py
```

验证内容:
- 重启后所有报警（offline/over_temp/under_temp）数量、类型、状态一致
- 已关闭报警的 `resolution_note` 和 `confirmations` 记录完整
- 离线报警 `trigger_value` 为 `None`
- 报警 CSV/JSON 导出行数、ID 集合与 API 查询一致
- 温度读数 CSV/API 条数一致
- 配置数据（人员/传感器/库区/阈值版本）完整保留
- **静音计划（抑制规则）**：规则列表、状态、命中日志、CSV 导出跨重启一致
- **suppressed 状态报警**：suppression_rule_id 和 suppression_rule_reason 完整保留
- 静音命中记录可追溯：每条 suppressed 报警都能在命中日志中找到对应记录
- **交接班巡检清单**：清单数据、检查项快照（阈值/读数/报警数）、检查结果、处理人信息完整保留
- 快照不变性：重启后传感器快照阈值、最近读数、未处理报警数与创建时一致
- 导出一致性：CSV/JSON 导出的报警数量和检查项状态与 API 查询一致
- **冷库巡检工单**：模板状态（draft/active/disabled）、巡检点配置、工单状态（pending/claimed/completed）、检查项填写数据（温度、照片、备注、异常处理）、关联报警（含 alarm_snapshot 快照）、操作日志完整保留
- 巡检逾期计算：重启后非 completed 工单的 is_overdue 标记仍按 deadline 与当前时间正确计算
- 巡检导出一致性：重启后工单 CSV/JSON 导出的 ID 集合与列表 API 完全一致，单条工单明细导出与详情 API 字段一致

### 4. 冷库巡检工单综合测试

```bash
python test_inspection.py
```

覆盖内容（337 项用例，全部通过）：
- **权限验证**：admin/operator/observer 三角色权限矩阵全覆盖（模板管理、工单生成/领取/填写/完成、报警关联等）
- **模板状态流转**：draft → active → disabled → active（停用后可重新启用）
- **模板不可变性**：active 和 disabled 模板字段、巡检点均不可修改（增删改全部拦截）
- **工单生成冲突**：同一库区同一日期同一班次重复生成返回 409 Conflict
- **工单生命周期**：pending → claimed → completed，全部检查项完成才能提交
- **检查项填写**：温度复核、照片 URL 列表（photo_urls）、备注、异常处理动作、处理人、状态（normal/abnormal）
- **逾期自动标记**：非 completed 工单超过 deadline 自动标记 is_overdue=true（运行时计算）
- **报警关联**：关联已有报警并保存 alarm_snapshot JSON 快照，解除关联，快照不受后续报警状态变化影响
- **操作日志审计**：生成、领取、检查项更新、完成、报警关联/解除全部生成可追溯日志
- **多条件筛选**：按库区、状态、负责人（claimed_by）、班次、日期范围、是否逾期筛选
- **导出一致性**：工单列表 CSV/JSON 导出与列表 API ID 集合完全一致；单条工单明细导出与详情 API（items/associated_alarms/logs）字段完全一致

### 5. 冷库巡检工单跨重启一致性验证

```bash
# 先运行综合测试产生数据
python test_inspection.py

# 重启服务（停止后再启动）
uvicorn main:app --host 0.0.0.0 --port 8000

# 等待服务启动后运行一致性验证
python test_inspection_restart.py
```

覆盖内容（128 项用例，全部通过）：
- 模板数据持久化：列表数量、状态、巡检点配置跨重启一致
- 工单状态持久化：pending/claimed/completed 状态、领取人、完成时间、deadline 完整保留
- 检查项数据持久化：温度值、photo_urls 列表、备注、异常处理、状态、处理人信息完整保留
- 操作日志持久化：所有日志条目（action、operator、detail、timestamp）完整保留
- 关联报警持久化：关联记录、alarm_snapshot JSON 快照（含报警详情、确认、处理日志）完整保留
- 逾期计算正确性：重启后 is_overdue 按 deadline 与当前时间重新计算
- 导出一致性：重启后工单 CSV/JSON/list/detail 导出与 API 数据完全一致
- 权限约束持久化：重启后权限控制仍然生效（observer 仍不能创建/操作）

---

## 数据存储

所有数据存储在 SQLite 数据库文件 `cold_storage.db` 中，包含以下表：

| 表名 | 说明 |
|------|------|
| `zones` | 库区信息 |
| `persons` | 人员/负责人信息 |
| `sensors` | 传感器信息 |
| `threshold_versions` | 阈值版本（版本化管理） |
| `temperature_readings` | 温度读数 |
| `alarms` | 报警记录（含 suppression_rule_id 关联静音计划） |
| `alarm_confirmations` | 报警状态变更记录 |
| `suppression_rules` | 静音计划（支持按传感器/库区/类型 + 时间窗口） |
| `suppression_hits` | 静音命中日志（记录触发值、时间、关联报警和计划） |
| `shift_checklists` | 交接班巡检清单（按库区+班次生成） |
| `shift_checklist_sensor_items` | 传感器检查项（快照阈值、读数、报警） |
| `shift_checklist_manual_items` | 现场手动检查项（制冷机组、库门密封等） |
| `drills` | 温控策略演练配置与状态 |
| `drill_readings` | 演练模拟读数 |
| `drill_judgments` | 演练逐条判定明细 |
| `drill_alarm_changes` | 演练报警变化记录 |
| `drill_operation_logs` | 演练操作日志 |
| `inspection_templates` | 巡检工单模板（按库区+班次配置，含 draft/active/disabled 状态） |
| `inspection_checkpoints` | 模板巡检点（名称、描述、是否需照片/温度、排序） |
| `inspection_work_orders` | 巡检工单（从模板生成，含截止时间、状态、领取人、完成时间） |
| `inspection_work_order_items` | 工单检查项（巡检点快照副本，含温度、照片URL、备注、异常处理、状态） |
| `inspection_work_order_alarms` | 工单关联报警（含关联时报警快照 JSON） |
| `inspection_work_order_logs` | 工单操作日志（生成、领取、填写、完成、关联/解除报警等） |

服务重启后，所有数据保留，查询和导出结果一致。

---

## 九、交接班巡检清单

值班人员可按库区生成班次巡检清单，自动快照每个传感器的当前阈值、最近读数和未处理报警数量，并生成5项固定现场确认检查项。清单创建后可逐项追加检查结果、异常备注和处理人；提交后不可再改；同一库区同一班次（日期+班次类型）不能重复创建。

### 班次类型

| 类型 | 说明 |
|------|------|
| `morning` | 早班 |
| `afternoon` | 中班 |
| `night` | 晚班 |

### 清单状态

| 状态 | 说明 |
|------|------|
| `draft` | 草稿，可追加检查结果、可提交、可撤回 |
| `submitted` | 已提交，不可修改 |
| `revoked` | 已撤回，不可修改，但可重建同班次清单 |

### 检查项状态

| 状态 | 说明 |
|------|------|
| `pending` | 待检查 |
| `normal` | 正常 |
| `abnormal` | 异常（需填写异常备注，可指定处理人） |

### 自动生成的手动检查项

创建清单时自动生成以下5项现场确认检查项：

1. 制冷机组运行状态 — 检查机组是否正常运行，有无异常噪音或振动
2. 库门密封检查 — 检查库门密封条是否完好，关闭是否严密
3. 传感器外观及固定 — 检查传感器外观是否完好，安装是否牢固
4. 库区卫生情况 — 检查库区地面、货架是否清洁，有无杂物堆积
5. 应急设备检查 — 检查应急灯、报警按钮、消防设备是否正常可用

### 约束条件

- **禁止重复班次**：同一库区同一日期同一班次类型不能重复创建（revoked 的不参与冲突检测）
- **权限约束**：只有 admin 和 operator 可以创建/提交/撤回/更新检查项，observer 只能查看
- **已提交不可修改**：提交后的清单不能再修改检查项、再提交或撤回
- **已撤回不可修改**：撤回后的清单不能再修改检查项
- **快照不可变**：创建时快照的阈值、读数、报警数据不受后续导入或阈值变更影响

#### 1. 创建交接班巡检清单

```bash
curl -X POST http://localhost:8000/shift-checklists \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "shift_date": "2026-06-12",
    "shift_type": "morning",
    "created_by": 1,
    "general_remark": "早班巡检"
  }'
```

预期结果：返回 200，包含清单详情（status=draft），sensor_items 含该库区所有传感器的快照数据，manual_items 含5项现场检查项。

#### 2. 查看清单列表

```bash
# 全部清单
curl -X GET http://localhost:8000/shift-checklists

# 按库区筛选
curl -X GET "http://localhost:8000/shift-checklists?zone_id=1"

# 按状态筛选
curl -X GET "http://localhost:8000/shift-checklists?status=draft"

# 按班次类型筛选
curl -X GET "http://localhost:8000/shift-checklists?shift_type=morning"

# 按日期范围筛选
curl -X GET "http://localhost:8000/shift-checklists?shift_date_from=2026-06-01&shift_date_to=2026-06-30"

# 按创建人筛选
curl -X GET "http://localhost:8000/shift-checklists?created_by=1"
```

#### 3. 查看清单详情

```bash
curl -X GET http://localhost:8000/shift-checklists/1
```

预期结果：包含清单信息、创建人姓名/角色、传感器检查项（含 sensor_code、快照阈值、最近读数、未处理报警数）、手动检查项。

#### 4. 更新传感器检查项

```bash
# 标记为正常
curl -X PUT http://localhost:8000/shift-checklists/1/sensor-items/1 \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "check_status": "normal"}'

# 标记为异常（带备注和处理人）
curl -X PUT http://localhost:8000/shift-checklists/1/sensor-items/1 \
  -H "Content-Type: application/json" \
  -d '{
    "person_id": 2,
    "check_status": "abnormal",
    "abnormal_remark": "温度偏离正常范围",
    "handler_id": 1
  }'
```

#### 5. 更新手动检查项

```bash
curl -X PUT http://localhost:8000/shift-checklists/1/manual-items/1 \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "check_status": "normal"}'
```

#### 6. 提交清单

```bash
curl -X POST http://localhost:8000/shift-checklists/1/submit \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1, "general_remark": "早班巡检完毕，一切正常"}'
```

预期结果：返回 200，状态变为 submitted。提交后不可再修改。

#### 7. 撤回未提交清单

```bash
curl -X POST http://localhost:8000/shift-checklists/1/revoke \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：返回 200，状态变为 revoked。撤回后可重建同班次清单。

#### 8. 导出清单 CSV

```bash
curl -X GET "http://localhost:8000/shift-checklists/export.csv" -o shift_checklists.csv
```

#### 9. 导出清单 JSON

```bash
curl -X GET "http://localhost:8000/shift-checklists/export.json" -o shift_checklists.json
```

#### 10. 失败场景验证

##### 场景 1：observer 不能创建清单（403）

```bash
curl -X POST http://localhost:8000/shift-checklists \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "shift_date": "2026-06-20",
    "shift_type": "morning",
    "created_by": 3
  }'
```

预期结果：返回 403，提示 "Permission denied: only admin or operator can create shift checklists"

##### 场景 2：重复班次冲突（409）

```bash
# 先创建一条
curl -X POST http://localhost:8000/shift-checklists \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "shift_date": "2026-06-21", "shift_type": "morning", "created_by": 1}'

# 再创建同库区同班次
curl -X POST http://localhost:8000/shift-checklists \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "shift_date": "2026-06-21", "shift_type": "morning", "created_by": 1}'
```

预期结果：第二条返回 409 Conflict，提示 "Duplicate shift checklist"。

##### 场景 3：撤回后重建同班次

```bash
# 撤回上面的清单（假设 ID=1）
curl -X POST http://localhost:8000/shift-checklists/1/revoke \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 重建同班次清单，应成功
curl -X POST http://localhost:8000/shift-checklists \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "shift_date": "2026-06-21", "shift_type": "morning", "created_by": 1}'
```

预期结果：撤回成功（status=revoked），重建成功（status=draft）。

##### 场景 4：导入读数后清单快照不被旧数据改写

```bash
# 步骤1: 创建清单（记录快照）
curl -X POST http://localhost:8000/shift-checklists \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "shift_date": "2026-06-22", "shift_type": "morning", "created_by": 1}'

# 步骤2: 查看清单详情，记录 snapshot_threshold_upper 等快照值
curl -X GET http://localhost:8000/shift-checklists/1

# 步骤3: 导入新的温度读数（会触发新报警或改变最新读数）
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2026-06-22T10:00:00"}]'

# 步骤4: 修改阈值
curl -X POST http://localhost:8000/thresholds \
  -H "Content-Type: application/json" \
  -d '{"sensor_id": 1, "upper_limit": -10.0, "lower_limit": -30.0, "dedup_window_minutes": 60, "effective_from": "2026-06-22T00:00:00"}'

# 步骤5: 再次查看清单详情，验证快照值未变
curl -X GET http://localhost:8000/shift-checklists/1
```

预期结果：清单中 sensor_items 的 snapshot_threshold_upper/lower、snapshot_latest_reading_value、snapshot_open_alarm_count 等快照值与步骤2完全相同，不受步骤3、4的影响。

---

## 十、温控策略演练

主管可针对库区配置演练策略（目标温度、允许波动、持续时长），导入模拟读数后发起演练，系统按时间顺序计算每个传感器是否会触发报警、升级或恢复。演练结果完全落库，与真实报警系统隔离，服务重启后状态和明细仍可查。

### 演练状态

| 状态 | 说明 |
|------|------|
| `draft` | 草稿，可导入读数、可启动、可取消 |
| `running` | 已启动，模拟结果已计算，可完成或取消 |
| `completed` | 已完成，不可修改 |
| `cancelled` | 已取消，不可修改 |

### 判定动作

| 动作 | 说明 |
|------|------|
| `trigger` | 新报警触发 |
| `update` | 报警持续，温度更新 |
| `escalate` | 报警升级（偏差继续增大） |
| `recover` | 报警恢复（温度回归正常） |
| `none` | 温度正常，无报警变化 |

### 报警变化类型

| 类型 | 说明 |
|------|------|
| `new_alarm` | 新报警产生 |
| `status_update` | 报警状态更新（持续但未升级） |
| `escalated` | 报警升级 |
| `recovered` | 报警恢复关闭 |

### 权限矩阵

| 操作 | admin | operator | observer |
|------|-------|----------|----------|
| 创建演练 | ✅ | ❌ | ❌ |
| 导入模拟读数 | ✅ | ❌ | ❌ |
| 启动演练 | ✅ | ✅ | ❌ |
| 取消演练 | ✅ | ❌ | ❌ |
| 完成演练 | ✅ | ❌ | ❌ |
| 查看演练 | ✅ | ✅ | ✅ |
| 导出演练 | ✅ | ❌ | ❌ |

### 约束条件

- **同一库区不能同时运行**：同一库区不能有两场 status=running 的演练
- **已启动配置不可改**：演练一旦启动，配置和读数不可变更
- **读数仅限草稿**：模拟读数只能在 draft 状态导入
- **传感器归属校验**：导入的 sensor_code 必须属于演练配置的库区
- **演练与真实隔离**：演练不产生真实的温度读数和报警记录

### 阈值计算

- 上限 = 目标温度 + 允许波动（`upper_limit = target_temp + allowed_fluctuation`）
- 下限 = 目标温度 - 允许波动（`lower_limit = target_temp - allowed_fluctuation`）
- 升级判定：若偏差超过历史最大偏差，报警升级（如超温时温度继续升高、低温时温度继续降低）

#### 1. 创建演练

```bash
curl -X POST http://localhost:8000/drills \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "name": "冷冻库区A超温演练",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 1
  }'
```

预期结果：返回 200，status=draft，upper_limit=-15.0，lower_limit=-21.0。

#### 2. 导入模拟读数（JSON 文件）

```bash
curl -X POST http://localhost:8000/drills/1/readings/import-json \
  -F "file=@examples/drill_readings_sample.json"
```

JSON 格式示例（`examples/drill_readings_sample.json`）：

```json
[
  {"sensor_code": "TEMP-001", "temperature": -18.5, "reading_time": "2026-06-12T08:00:00"},
  {"sensor_code": "TEMP-001", "temperature": -14.0, "reading_time": "2026-06-12T08:30:00"},
  {"sensor_code": "TEMP-001", "temperature": -12.0, "reading_time": "2026-06-12T09:00:00"},
  {"sensor_code": "TEMP-001", "temperature": -18.0, "reading_time": "2026-06-12T09:30:00"}
]
```

#### 3. 导入模拟读数（CSV 文件）

```bash
curl -X POST http://localhost:8000/drills/1/readings/import-csv \
  -F "file=@examples/drill_readings_sample.csv"
```

CSV 格式示例（`examples/drill_readings_sample.csv`）：

```csv
sensor_code,temperature,reading_time
TEMP-001,-18.5,2026-06-12T08:00:00
TEMP-001,-14.0,2026-06-12T08:30:00
TEMP-001,-12.0,2026-06-12T09:00:00
TEMP-001,-18.0,2026-06-12T09:30:00
```

#### 4. 启动演练

```bash
curl -X POST http://localhost:8000/drills/1/start \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：返回 200，status=running，包含 judgments（逐条判定）和 alarm_changes（报警变化）。
- -14.0 → trigger（over_temp，超上限 -15.0）
- -12.0 → escalate（偏差继续增大）
- -18.0 → recover（温度回归正常范围）

#### 5. 完成演练

```bash
curl -X POST http://localhost:8000/drills/1/complete \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：返回 200，status=completed。

#### 6. 取消演练

```bash
# 取消草稿
curl -X POST http://localhost:8000/drills/1/cancel \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 取消运行中的演练
curl -X POST http://localhost:8000/drills/2/cancel \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：返回 200，status=cancelled。取消后可新建同库区的新演练。

#### 7. 查看演练列表

```bash
# 全部演练
curl -X GET http://localhost:8000/drills

# 按库区筛选
curl -X GET "http://localhost:8000/drills?zone_id=1"

# 按状态筛选
curl -X GET "http://localhost:8000/drills?status=running"
```

#### 8. 查看演练详情

```bash
curl -X GET http://localhost:8000/drills/1
```

预期结果：包含演练配置、判定明细（judgments）、报警变化（alarm_changes）、操作日志（operation_logs）。

#### 9. 导出演练结果 JSON

```bash
curl -X GET http://localhost:8000/drills/1/export.json -o drill_1_export.json
```

预期结果：JSON 文件包含 config_snapshot（配置快照）、judgments（逐条判定）、alarm_changes（报警变化）、operation_logs（操作日志）。

#### 10. 导出演练列表 CSV

```bash
curl -X GET "http://localhost:8000/drills/export.csv" -o drills.csv
```

#### 11. 失败场景验证

##### 场景 1：observer 不能创建演练（403）

```bash
curl -X POST http://localhost:8000/drills \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "name": "observer尝试创建",
    "target_temp": -18.0,
    "allowed_fluctuation": 3.0,
    "duration_minutes": 120,
    "created_by": 3
  }'
```

预期结果：返回 403，提示 "Permission denied: only admin can create drills"

##### 场景 2：observer 不能启动演练（403）

```bash
curl -X POST http://localhost:8000/drills/1/start \
  -H "Content-Type: application/json" \
  -d '{"person_id": 3}'
```

预期结果：返回 403，提示 "Permission denied: only admin or operator can start drills"

##### 场景 3：operator 不能取消演练（403）

```bash
curl -X POST http://localhost:8000/drills/1/cancel \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2}'
```

预期结果：返回 403，提示 "Permission denied: only admin can cancel drills"

##### 场景 4：同一库区时间冲突（409）

```bash
# 创建并启动演练1（zone_id=1）
curl -X POST http://localhost:8000/drills \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "name": "演练1", "target_temp": -18.0, "allowed_fluctuation": 3.0, "duration_minutes": 120, "created_by": 1}'

# 导入读数并启动
curl -X POST http://localhost:8000/drills/1/readings/import-json \
  -F "file=@examples/drill_readings_sample.json"
curl -X POST http://localhost:8000/drills/1/start \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 创建演练2（同库区）并尝试启动
curl -X POST http://localhost:8000/drills \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "name": "演练2", "target_temp": -20.0, "allowed_fluctuation": 2.0, "duration_minutes": 60, "created_by": 1}'

curl -X POST http://localhost:8000/drills/2/start \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：演练2启动返回 409 Conflict，提示 "Conflict: zone 1 already has a running drill"。

##### 场景 5：取消后重建演练

```bash
# 取消演练1
curl -X POST http://localhost:8000/drills/1/cancel \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 重新创建并启动同库区演练，应成功
curl -X POST http://localhost:8000/drills \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "name": "取消后重建演练", "target_temp": -18.0, "allowed_fluctuation": 3.0, "duration_minutes": 120, "created_by": 1}'
```

预期结果：取消成功（status=cancelled），重建成功（status=draft），可正常启动。

##### 场景 6：导入格式错误

```bash
# JSON 格式错误
echo 'not a json' > /tmp/bad.json
curl -X POST http://localhost:8000/drills/1/readings/import-json \
  -F "file=@/tmp/bad.json"
```

预期结果：返回 400，提示 "Invalid JSON"。

```bash
# CSV 缺少必需列
echo "sensor_code,temp" > /tmp/bad.csv
echo "TEMP-001,-18" >> /tmp/bad.csv
curl -X POST http://localhost:8000/drills/1/readings/import-csv \
  -F "file=@/tmp/bad.csv"
```

预期结果：返回 400，提示 "CSV must have columns: sensor_code, temperature, reading_time"。

##### 场景 7：重启后继续查看演练

```bash
# 步骤1: 创建并完成一个演练
curl -X POST http://localhost:8000/drills \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "name": "重启验证演练", "target_temp": -18.0, "allowed_fluctuation": 3.0, "duration_minutes": 120, "created_by": 1}'

# 步骤2: 导入读数并启动
curl -X POST http://localhost:8000/drills/1/readings/import-json \
  -F "file=@examples/drill_readings_sample.json"
curl -X POST http://localhost:8000/drills/1/start \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 步骤3: 记录演练详情
curl -X GET http://localhost:8000/drills/1

# 步骤4: 重启服务
# 停止 uvicorn 后重新启动
uvicorn main:app --host 0.0.0.0 --port 8000

# 步骤5: 再次查看演练详情，验证数据完整
curl -X GET http://localhost:8000/drills/1
```

预期结果：重启后演练状态、判定明细、报警变化、操作日志与重启前完全一致。

##### 场景 8：导出内容与 API 结果一致

```bash
# 获取演练详情
curl -X GET http://localhost:8000/drills/1

# 导出演练结果
curl -X GET http://localhost:8000/drills/1/export.json -o drill_1_export.json

# 对比：导出 JSON 中的 judgments、alarm_changes、operation_logs 与 API 返回的完全一致
```

预期结果：导出 JSON 的 config_snapshot、judgments、alarm_changes、operation_logs 与 API `/drills/1` 返回的对应字段完全一致。

---

## 十一、冷库巡检工单

主管可按库区、班次、巡检点和截止时间创建巡检工单模板，再按日期生成当天工单；operator 可领取工单、逐项填写温度复核、上传照片（URL 占位）、填写备注、异常处理动作和完成时间；observer 只能查看。工单支持按库区、状态、负责人筛选，过截止时间自动标记 overdue，可关联已有报警（含报警快照与处理日志）。模板启用/停用后历史字段不可修改，同一库区同一班次重复生成报冲突（409）。

### 模板状态

| 状态 | 说明 |
|------|------|
| `draft` | 草稿，可修改模板字段、增删改巡检点 |
| `active` | 已启用，不可修改字段和巡检点，可生成工单 |
| `disabled` | 已停用，不可修改字段和巡检点，不可生成工单，但可重新启用 |

### 工单状态

| 状态 | 说明 |
|------|------|
| `pending` | 待领取，可被 operator 领取 |
| `claimed` | 已领取，可填写检查项、完成工单 |
| `completed` | 已完成，不可修改 |

### 班次类型

| 类型 | 起始时间 | 说明 |
|------|----------|------|
| `morning` | 08:00 | 早班 |
| `afternoon` | 16:00 | 中班 |
| `night` | 00:00 | 晚班 |

工单截止时间 = 班次起始时间 + 模板 deadline_hours。

### 巡检权限矩阵

| 操作 | admin | operator | observer |
|------|-------|----------|----------|
| 创建模板 | ✅ | ❌ | ❌ |
| 修改草稿模板 | ✅ | ❌ | ❌ |
| 启用/停用模板 | ✅ | ❌ | ❌ |
| 增删改巡检点（仅 draft） | ✅ | ❌ | ❌ |
| 生成工单 | ✅ | ❌ | ❌ |
| 领取工单 | ❌ | ✅ | ❌ |
| 填写检查项 | ❌ | ✅（仅自己领取的） | ❌ |
| 完成工单 | ❌ | ✅（仅自己领取的） | ❌ |
| 关联/解除报警 | ✅ | ✅ | ❌ |
| 查看模板/工单 | ✅ | ✅ | ✅ |
| 导出工单 | ✅ | ✅ | ✅ |

### 约束条件

- **模板不可变**：模板一旦启用（active）或停用（disabled），模板字段和巡检点均不可修改；停用后可重新启用为 active
- **禁止重复生成**：同一库区（zone_id）+ 同一日期（work_date）+ 同一班次（shift_type）只能有一条工单，重复生成返回 409 Conflict
- **截止时间逾期**：非 completed 工单，若当前时间 > deadline，则 is_overdue=true（运行时计算）
- **全部检查完成才能提交**：完成工单前所有检查项必须已检查（check_status != pending）
- **数据持久化**：所有模板、工单、检查项、关联报警、操作日志均存入 SQLite，服务重启后完整保留

### 1. 创建巡检模板（含巡检点）

```bash
curl -X POST http://localhost:8000/inspection-templates \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "shift_type": "morning",
    "name": "冷冻库区A早班巡检",
    "description": "每日早班巡检流程",
    "deadline_hours": 4.0,
    "created_by": 1,
    "checkpoints": [
      {"name": "1号冷风机运行状态", "description": "检查风机是否运转正常", "sort_order": 1, "require_photo": true, "require_temperature": false},
      {"name": "2号冷风机运行状态", "description": "检查风机是否运转正常", "sort_order": 2, "require_photo": true, "require_temperature": false},
      {"name": "库区温度复核", "description": "实测并记录库区温度", "sort_order": 3, "require_photo": false, "require_temperature": true},
      {"name": "库门密封性检查", "description": "检查密封条是否完好", "sort_order": 4, "require_photo": true, "require_temperature": false}
    ]
  }'
```

预期结果：返回 200，status=draft，含 checkpoints 列表。

### 2. 为草稿模板新增巡检点

```bash
curl -X POST http://localhost:8000/inspection-templates/1/checkpoints \
  -H "Content-Type: application/json" \
  -d '{"name": "应急照明检查", "description": "检查应急灯是否正常", "sort_order": 5, "require_photo": true, "require_temperature": false}'
```

### 3. 修改草稿巡检点

```bash
curl -X PUT http://localhost:8000/inspection-templates/1/checkpoints/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "1号冷风机运行状态-更新", "require_photo": true}'
```

### 4. 删除草稿巡检点

```bash
curl -X DELETE http://localhost:8000/inspection-templates/1/checkpoints/5
```

### 5. 启用模板

```bash
curl -X POST http://localhost:8000/inspection-templates/1/activate \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：status=active。启用后模板字段和巡检点不可再修改。

### 6. 停用模板

```bash
curl -X POST http://localhost:8000/inspection-templates/1/disable \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：status=disabled。停用后不可生成工单，但可重新 activate。

### 7. 查看模板列表

```bash
# 全部模板
curl -X GET http://localhost:8000/inspection-templates

# 按库区筛选
curl -X GET "http://localhost:8000/inspection-templates?zone_id=1"

# 按状态筛选
curl -X GET "http://localhost:8000/inspection-templates?status=active"

# 按班次筛选
curl -X GET "http://localhost:8000/inspection-templates?shift_type=morning"
```

### 8. 查看模板详情

```bash
curl -X GET http://localhost:8000/inspection-templates/1
```

预期结果：包含模板信息和完整 checkpoints 列表。

### 9. 修改草稿模板字段

```bash
curl -X PUT http://localhost:8000/inspection-templates/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "冷冻库区A早班巡检-修订", "deadline_hours": 5.0}'
```

仅 draft 状态可修改，active/disabled 返回错误。

### 10. 从模板生成当日巡检工单

```bash
curl -X POST http://localhost:8000/inspection-work-orders/generate \
  -H "Content-Type: application/json" \
  -d '{"template_id": 1, "work_date": "2026-07-15", "created_by": 1}'
```

预期结果：返回 200，status=pending，items 为模板巡检点的副本（快照），deadline = 班次起始时间 + deadline_hours。

### 11. 领取工单

```bash
curl -X POST http://localhost:8000/inspection-work-orders/1/claim \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2}'
```

预期结果：status=claimed，claimed_by=2，claimed_at 记录领取时间。

### 12. 填写巡检检查项

```bash
curl -X PUT http://localhost:8000/inspection-work-orders/1/items/1 \
  -H "Content-Type: application/json" \
  -d '{
    "person_id": 2,
    "check_status": "normal",
    "photo_urls": ["http://example.com/photo1.jpg", "http://example.com/photo2.jpg"],
    "remark": "设备运行正常，无异常噪音",
    "exception_action": null,
    "handler_id": null
  }'
```

填写温度复核（需温度的检查项）：

```bash
curl -X PUT http://localhost:8000/inspection-work-orders/1/items/3 \
  -H "Content-Type: application/json" \
  -d '{
    "person_id": 2,
    "check_status": "abnormal",
    "temperature_value": -14.5,
    "remark": "温度偏高，超出阈值",
    "exception_action": "已联系维修人员检查制冷机组",
    "handler_id": 1
  }'
```

### 13. 完成工单

```bash
curl -X POST http://localhost:8000/inspection-work-orders/1/complete \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "general_remark": "本次巡检完成，发现1项温度异常，已安排处理"}'
```

预期结果：status=completed。所有检查项必须已检查（不能有 pending），否则返回 400。

### 14. 查看工单列表

```bash
# 全部工单
curl -X GET http://localhost:8000/inspection-work-orders

# 按库区筛选
curl -X GET "http://localhost:8000/inspection-work-orders?zone_id=1"

# 按状态筛选
curl -X GET "http://localhost:8000/inspection-work-orders?status=pending"

# 按负责人（领取人）筛选
curl -X GET "http://localhost:8000/inspection-work-orders?claimed_by=2"

# 按班次筛选
curl -X GET "http://localhost:8000/inspection-work-orders?shift_type=morning"

# 按日期范围筛选
curl -X GET "http://localhost:8000/inspection-work-orders?work_date_from=2026-07-01&work_date_to=2026-07-31"

# 按是否逾期筛选
curl -X GET "http://localhost:8000/inspection-work-orders?is_overdue=true"
```

### 15. 查看工单详情

```bash
curl -X GET http://localhost:8000/inspection-work-orders/1
```

预期结果：包含工单信息、items（所有检查项及填写结果）、associated_alarms（关联报警含快照）、logs（操作日志）。

### 16. 关联已有报警

```bash
curl -X POST http://localhost:8000/inspection-work-orders/1/alarms \
  -H "Content-Type: application/json" \
  -d '{"associated_by": 2, "alarm_id": 1}'
```

预期结果：返回关联记录，alarm_snapshot 为关联时报警状态的 JSON 快照（含报警详情、确认记录、处理日志），后续报警状态变化不影响快照。

### 17. 解除报警关联

```bash
curl -X DELETE http://localhost:8000/inspection-work-orders/1/alarms/1
```

### 18. 导出工单列表 CSV

```bash
curl -X GET "http://localhost:8000/inspection-work-orders/export.csv" -o inspection_work_orders.csv
```

### 19. 导出工单列表 JSON

```bash
curl -X GET "http://localhost:8000/inspection-work-orders/export.json" -o inspection_work_orders.json
```

预期结果：导出 JSON/CSV 的工单 ID 集合与列表 API `/inspection-work-orders` 完全一致。

### 20. 导出单条工单明细 JSON

```bash
curl -X GET "http://localhost:8000/inspection-work-orders/1/export.json" -o inspection_wo_1.json
```

预期结果：导出内容包含 items、associated_alarms、logs，与详情 API `/inspection-work-orders/1` 返回的对应字段一致。

### 21. 失败场景验证

#### 场景 1：observer 不能创建模板（403）

```bash
curl -X POST http://localhost:8000/inspection-templates \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "shift_type": "morning", "name": "observer尝试", "deadline_hours": 4.0, "created_by": 3}'
```

预期结果：返回 403，提示权限不足。

#### 场景 2：observer 不能领取工单（403）

```bash
curl -X POST http://localhost:8000/inspection-work-orders/1/claim \
  -H "Content-Type: application/json" \
  -d '{"person_id": 3}'
```

预期结果：返回 403。

#### 场景 3：operator 不能创建模板（403）

```bash
curl -X POST http://localhost:8000/inspection-templates \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "shift_type": "morning", "name": "operator尝试", "deadline_hours": 4.0, "created_by": 2}'
```

预期结果：返回 403。

#### 场景 4：active 模板不能修改（400）

```bash
# 先启用模板
curl -X POST http://localhost:8000/inspection-templates/1/activate \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 再尝试修改
curl -X PUT http://localhost:8000/inspection-templates/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "尝试修改active模板"}'
```

预期结果：返回 400，提示模板已启用/停用，不能修改。

#### 场景 5：active 模板不能增删巡检点（400）

```bash
curl -X POST http://localhost:8000/inspection-templates/1/checkpoints \
  -H "Content-Type: application/json" \
  -d '{"name": "尝试新增巡检点"}'
```

预期结果：返回 400。

#### 场景 6：disabled 模板同样不可修改（400）

```bash
# 先停用
curl -X POST http://localhost:8000/inspection-templates/1/disable \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'

# 再尝试修改
curl -X PUT http://localhost:8000/inspection-templates/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "尝试修改disabled模板"}'
```

预期结果：返回 400。

#### 场景 7：重复生成同一库区同一班次工单（409）

```bash
# 第一次生成
curl -X POST http://localhost:8000/inspection-work-orders/generate \
  -H "Content-Type: application/json" \
  -d '{"template_id": 1, "work_date": "2026-07-20", "created_by": 1}'

# 第二次生成（同库区同日期同班次）
curl -X POST http://localhost:8000/inspection-work-orders/generate \
  -H "Content-Type: application/json" \
  -d '{"template_id": 1, "work_date": "2026-07-20", "created_by": 1}'
```

预期结果：第二次返回 409 Conflict，提示"Duplicate work order for zone + date + shift"。

#### 场景 8：未领取不能完成（400）

```bash
curl -X POST http://localhost:8000/inspection-work-orders/1/complete \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2}'
```

预期结果：返回 400，提示工单未领取。

#### 场景 9：有 pending 检查项不能完成（400）

```bash
# 先领取
curl -X POST http://localhost:8000/inspection-work-orders/1/claim \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2}'

# 只填部分检查项（还有 pending）
curl -X PUT http://localhost:8000/inspection-work-orders/1/items/1 \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2, "check_status": "normal"}'

# 尝试完成
curl -X POST http://localhost:8000/inspection-work-orders/1/complete \
  -H "Content-Type: application/json" \
  -d '{"person_id": 2}'
```

预期结果：返回 400，提示还有未完成的检查项。

#### 场景 10：逾期工单自动标记 overdue

生成一个截止时间在过去的工单（或等待截止时间过去），然后查询：

```bash
curl -X GET "http://localhost:8000/inspection-work-orders?is_overdue=true"
```

预期结果：非 completed 且 deadline < 当前时间的工单 is_overdue=true。

#### 场景 11：重启后数据完整保留

```bash
# 步骤1: 创建模板并启用，生成工单、领取、填写、完成、关联报警
# （执行上述 1-17 步骤中的若干操作）

# 步骤2: 记录模板、工单、检查项、报警关联、操作日志数据

# 步骤3: 重启服务
# 停止 uvicorn 后重新启动
uvicorn main:app --host 0.0.0.0 --port 8000

# 步骤4: 查询验证数据完整
curl -X GET http://localhost:8000/inspection-templates/1
curl -X GET http://localhost:8000/inspection-work-orders/1
```

预期结果：重启后模板状态、工单状态、检查项填写数据、关联报警（含 alarm_snapshot）、操作日志与重启前完全一致。

#### 场景 12：导出与列表 API 数据一致

```bash
# 获取列表 API 的工单 ID 集合
curl -X GET "http://localhost:8000/inspection-work-orders"

# 导出 CSV/JSON
curl -X GET "http://localhost:8000/inspection-work-orders/export.csv" -o wo.csv
curl -X GET "http://localhost:8000/inspection-work-orders/export.json" -o wo.json

# 获取工单详情 API
curl -X GET http://localhost:8000/inspection-work-orders/1

# 导出工单明细
curl -X GET "http://localhost:8000/inspection-work-orders/1/export.json" -o wo_1.json
```

预期结果：
- 列表导出（CSV/JSON）的工单 ID 集合与 `/inspection-work-orders` API 完全一致
- 单条工单导出 JSON 的 items、associated_alarms、logs 字段与 `/inspection-work-orders/1` API 对应字段完全一致

---

## 项目结构

```
.
├── main.py                    # 主应用入口，API 路由
├── models.py                  # SQLAlchemy 数据模型（含静音计划、巡检模板/工单等）
├── schemas.py                 # Pydantic 请求/响应模式（含巡检模块 schema）
├── crud.py                    # 基础 CRUD 操作（含静音计划 CRUD）
├── alarm_service.py           # 报警核心业务逻辑（含静音命中处理）
├── drill_service.py           # 温控策略演练核心逻辑（模拟、CRUD、导出）
├── inspection_service.py      # 冷库巡检工单核心逻辑（模板、工单、报警关联、导出）
├── database.py                # 数据库连接配置
├── init_data.py               # 样例数据初始化脚本
├── test_alarm_fixes.py        # 复现与回归测试脚本
├── test_suppression_basic.py  # 静音计划基础测试
├── test_suppression_comprehensive.py  # 静音计划综合测试
├── test_suppression_regression.py     # 静音计划回归测试（旧手工抑制漏洞）
├── test_restart_consistency.py# 重启后一致性测试
├── test_final_verify.py       # 最终验证脚本（README 文档示例验证）
├── test_shift_checklist.py             # 交接班巡检清单全面测试
├── test_shift_checklist_restart.py     # 交接班巡检清单跨重启一致性测试
├── test_drill.py              # 温控策略演练综合测试
├── test_inspection.py         # 冷库巡检工单综合测试（337 项用例）
├── test_inspection_restart.py # 冷库巡检工单跨重启一致性测试（128 项用例）
├── requirements.txt           # Python 依赖
├── examples/                  # 样例数据
│   ├── readings_sample.json
│   ├── readings_sample.csv
│   ├── drill_readings_sample.json
│   └── drill_readings_sample.csv
└── README.md
```
