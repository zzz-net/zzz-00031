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
| `admin` | 所有操作，包括关闭报警、管理抑制规则 |
| `operator` | 确认、处理中、升级、关闭报警、管理抑制规则 |
| `observer` | 仅查看，不能操作报警、不能创建/撤销抑制规则 |

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

项目包含 3 个 Python 测试脚本，用于回归验证所有用户可见行为。

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

## 项目结构

```
.
├── main.py                    # 主应用入口，API 路由
├── models.py                  # SQLAlchemy 数据模型（含静音计划 SuppressionRule / SuppressionHit）
├── schemas.py                 # Pydantic 请求/响应模式
├── crud.py                    # 基础 CRUD 操作（含静音计划 CRUD）
├── alarm_service.py           # 报警核心业务逻辑（含静音命中处理）
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
├── requirements.txt           # Python 依赖
├── examples/                  # 样例数据
│   ├── readings_sample.json
│   └── readings_sample.csv
└── README.md
```
