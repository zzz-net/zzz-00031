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
| `admin` | 所有操作，包括关闭报警 |
| `operator` | 确认、处理中、升级、关闭报警 |
| `observer` | 仅查看，不能操作报警 |

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
| `over_temp` | 超高温报警 |
| `under_temp` | 超低温报警 |
| `offline` | 离线报警 |

### 关键规则

1. **乱序保护**: 同一传感器乱序读数不会改写活跃报警
2. **去重窗口**: 在去重窗口内，连续高温/低温只更新同一个报警
3. **权限控制**: 观察者(observer)不能关闭或确认报警
4. **关闭说明**: 关闭报警必须提供处理说明

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

#### 4. 抑制报警（临时屏蔽）

```bash
curl -X POST http://localhost:8000/alarms/1/suppress \
  -H "Content-Type: application/json" \
  -d '{"person_id": 1, "note": "已知设备检修，临时屏蔽1小时", "suppress_minutes": 60}'
```

#### 5. 关闭报警（需处理说明）

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

#### 3. 乱序读数不产生新报警

先导入一组读数产生报警:
```bash
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -10.0, "reading_time": "2026-06-12T10:00:00"}]'
```

再导入更早时间的乱序读数:
```bash
curl -X POST http://localhost:8000/readings/import \
  -H "Content-Type: application/json" \
  -d '[{"sensor_code": "TEMP-001", "temperature": -9.0, "reading_time": "2026-06-12T09:30:00"}]'
```

预期结果: 乱序读数不会产生新报警，也不会改变现有报警的触发时间

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

## 数据存储

所有数据存储在 SQLite 数据库文件 `cold_storage.db` 中，包含以下表:

| 表名 | 说明 |
|------|------|
| `zones` | 库区信息 |
| `persons` | 人员/负责人信息 |
| `sensors` | 传感器信息 |
| `threshold_versions` | 阈值版本（版本化管理） |
| `temperature_readings` | 温度读数 |
| `alarms` | 报警记录 |
| `alarm_confirmations` | 报警状态变更记录 |

服务重启后，所有数据保留，查询和导出结果一致。

## 项目结构

```
.
├── main.py              # 主应用入口，API 路由
├── models.py            # SQLAlchemy 数据模型
├── schemas.py           # Pydantic 请求/响应模式
├── crud.py              # 基础 CRUD 操作
├── alarm_service.py     # 报警核心业务逻辑
├── database.py          # 数据库连接配置
├── init_data.py         # 样例数据初始化脚本
├── requirements.txt     # Python 依赖
├── examples/            # 样例数据
│   ├── readings_sample.json
│   └── readings_sample.csv
└── README.md
```
