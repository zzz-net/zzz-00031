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

### 八、报警抑制规则

值班人员可给指定传感器或库区设置临时抑制窗口。窗口内读数仍正常入库，但符合抑制条件的报警不会变成 `open`，而是标记为 `suppressed`，同时生成命中日志（suppression_hits）记录触发值、时间和命中规则。

#### 抑制规则属性

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sensor_id` | int | 否 | 按传感器抑制（与 zone_id 二选一或同时） |
| `zone_id` | int | 否 | 按库区抑制（与 sensor_id 二选一或同时） |
| `alarm_type` | str | 否 | 按报警类型抑制：`over_temp` / `under_temp` / `offline`，留空表示全部 |
| `start_time` | datetime | 是 | 抑制窗口开始时间 |
| `end_time` | datetime | 是 | 抑制窗口结束时间，必须晚于 start_time |
| `reason` | str | 是 | 抑制原因，如"设备检修"、"库区维护" |
| `created_by` | int | 是 | 创建人 ID（必须是 admin 或 operator） |

#### 约束条件

- **禁止时间重叠**：相同范围（传感器/库区/类型有交集）的 active 规则不能时间重叠
- **禁止结束早于开始**：`end_time` 必须严格大于 `start_time`
- **权限约束**：只有 admin 和 operator 可以创建/撤销抑制规则，observer 只能查看
- **审计追踪**：每条 suppressed 报警都有对应 suppression_rule_id 和命中日志
- **到期自动恢复**：窗口结束后新异常读数正常生成 open 报警
- **撤销恢复**：撤销规则后新异常读数正常生成 open 报警

#### 1. 创建抑制规则（按传感器 + 类型）

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

#### 2. 创建抑制规则（按库区，全部类型）

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

#### 3. 查看抑制规则列表

```bash
# 全部规则
curl -X GET http://localhost:8000/suppression-rules

# 按状态筛选
curl -X GET "http://localhost:8000/suppression-rules?status=active"

# 按传感器筛选
curl -X GET "http://localhost:8000/suppression-rules?sensor_id=1"
```

#### 4. 查看抑制规则详情

```bash
curl -X GET http://localhost:8000/suppression-rules/1
```

预期结果：包含规则信息、创建人姓名、命中次数（hit_count）等。

#### 5. 撤销抑制规则

```bash
curl -X POST http://localhost:8000/suppression-rules/1/revoke \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1}'
```

预期结果：返回 200，规则状态变为 revoked。撤销后新异常读数会正常生成 open 报警。

#### 6. 查看抑制命中日志

```bash
curl -X GET http://localhost:8000/suppression-rules/1/hits
```

预期结果：每条命中包含 rule_id、alarm_id、sensor_code、alarm_type、trigger_value、trigger_time。

#### 7. 导出抑制规则 CSV

```bash
curl -X GET "http://localhost:8000/suppression-rules/export.csv" -o suppression_rules.csv
```

#### 8. 导出抑制命中日志 CSV

```bash
curl -X GET "http://localhost:8000/suppression-hits/export.csv" -o suppression_hits.csv
```

#### 9. 失败场景：时间重叠冲突

```bash
# 先创建一条 active 规则
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-06-17T00:00:00",
    "end_time": "2026-06-17T23:59:59",
    "reason": "测试冲突1",
    "created_by": 1
  }'

# 再创建一条时间重叠的同范围规则
curl -X POST http://localhost:8000/suppression-rules \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": 1,
    "start_time": "2026-06-17T12:00:00",
    "end_time": "2026-06-18T12:00:00",
    "reason": "测试冲突2",
    "created_by": 1
  }'
```

预期结果：第二条返回 409 Conflict，提示与现有规则冲突。

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
# 先跑一轮 test_suppression_comprehensive.py，然后重启 uvicorn
python test_restart_consistency.py
```

验证内容:
- 重启后所有报警（offline/over_temp/under_temp）数量、类型、状态一致
- 已关闭报警的 `resolution_note` 和 `confirmations` 记录完整
- 离线报警 `trigger_value` 为 `None`
- 报警 CSV/JSON 导出行数、ID 集合与 API 查询一致
- 温度读数 CSV/API 条数一致
- 配置数据（人员/传感器/库区/阈值版本）完整保留
- **抑制规则**：规则列表、状态、命中日志、CSV 导出跨重启一致
- **suppressed 状态报警**：suppression_rule_id 和 suppression_rule_reason 完整保留

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
| `alarms` | 报警记录（含 suppression_rule_id 关联抑制规则） |
| `alarm_confirmations` | 报警状态变更记录 |
| `suppression_rules` | 抑制规则（支持按传感器/库区/类型 + 时间窗口） |
| `suppression_hits` | 抑制命中日志（记录触发值、时间、关联报警和规则） |

服务重启后，所有数据保留，查询和导出结果一致。

## 项目结构

```
.
├── main.py                    # 主应用入口，API 路由
├── models.py                  # SQLAlchemy 数据模型（含 SuppressionRule / SuppressionHit）
├── schemas.py                 # Pydantic 请求/响应模式
├── crud.py                    # 基础 CRUD 操作（含抑制规则 CRUD）
├── alarm_service.py           # 报警核心业务逻辑（含抑制命中处理）
├── database.py                # 数据库连接配置
├── init_data.py               # 样例数据初始化脚本
├── test_alarm_fixes.py        # 复现与回归测试脚本
├── test_suppression_comprehensive.py  # 抑制规则综合测试
├── test_restart_consistency.py# 重启后一致性测试
├── requirements.txt           # Python 依赖
├── examples/                  # 样例数据
│   ├── readings_sample.json
│   └── readings_sample.csv
└── README.md
```
