# Vlog Editing Helper 深度代码审查报告

## Executive Summary

总体评价：**8.3 / 10**

优点：
- 模块划分清晰（ai/tasks/ui）
- Provider 抽象较合理
- 测试覆盖较好
- 使用 dataclass 管理配置
- 代码风格整体统一

主要技术债：
1. UI 层承担过多职责
2. Config 模块过度集中
3. Provider 生命周期管理不足
4. 文件系统与业务逻辑耦合较深
5. 缺少统一领域模型层

---

# P0（优先处理）

## 1. ui/server.py 已成为“上帝对象”

文件：
`vlog_tool/ui/server.py`

规模：约 547 行

### 现象

同时承担：

- HTTP Server
- Route Dispatch
- Project Discovery
- Config Cache
- Run State
- Thread 管理
- 文件访问

### 风险

- 修改一个功能容易影响其他功能
- 单元测试困难
- 后续功能扩展成本上升

### 推荐方案

拆分：

```text
ui/
├── server.py
├── router.py
├── state.py
├── project_service.py
└── config_cache.py
```

---

## 2. Provider Cache 无生命周期管理

文件：

`vlog_tool/ai/factory.py`

发现：

```python
_provider_cache = {}
```

### 风险

长期运行时：

- Session 泄漏
- HTTP Client 长驻
- 内存持续增长

### 推荐方案

引入：

```python
ProviderManager
```

统一负责：

- 创建
- 复用
- 销毁
- 热更新

---

# P1（建议近期处理）

## 3. config.py 职责过重

文件：

`vlog_tool/config.py`

规模：约 405 行

### 当前职责

- Schema
- Defaults
- Validation
- Load
- Merge
- Env Override

### 推荐方案

```text
config/
├── schema.py
├── loader.py
├── validator.py
└── defaults.py
```

收益：

- 降低耦合
- 提高可测试性

---

## 4. UI 中存在业务逻辑

发现类似：

- Project Resolve
- Project Discovery
- Registry 查询

直接放在 UI Handler 中。

### 推荐方案

迁移至：

```python
ProjectService
```

UI 仅负责：

```text
Request
 -> Service
 -> Response
```

---

## 5. 文件系统承担数据库职责

当前大量 Task 直接依赖：

```python
Path.read_text()
Path.write_text()
```

### 问题

业务逻辑与目录结构强绑定。

### 推荐方案

增加 Repository 抽象：

```python
ProjectRepository
```

统一访问：

```python
load_script()
save_script()
load_analysis()
```

---

## 6. Config Cache 不是严格 LRU

发现逻辑类似：

```python
oldest_key = next(iter(cache))
```

### 问题

这是“最早插入”，不是“最久未使用”。

### 推荐方案

```python
functools.lru_cache
```

或

```python
OrderedDict
```

---

# P2（中长期优化）

## 7. Prompt 缺少版本管理

建议：

```text
prompts/
├── v1/
├── v2/
└── v3/
```

同时记录：

- 创建时间
- 使用模型
- A/B 测试结果

---

## 8. Token Cost Tracking 缺失

建议记录：

```json
{
  "provider":"gemini",
  "model":"gemini-2.5-flash",
  "input_tokens":1000,
  "output_tokens":300
}
```

用于：

- 成本分析
- Prompt 优化
- 预算控制

---

## 9. 缺少领域模型

当前较多 dict/json 直接流转。

建议：

```python
@dataclass
class VideoAnalysis

@dataclass
class Segment

@dataclass
class VoiceoverScript
```

收益：

- 类型安全
- IDE 友好
- 降低 Bug

---

## 10. 缺少事件总线

当前：

```python
tracker.update()
```

未来建议：

```python
event_bus.publish()
```

支持：

- UI 订阅
- 日志订阅
- WebSocket 推送

---

# 性能优化建议

## 文件扫描缓存

避免频繁：

```python
rglob()
```

建立：

```python
VideoIndex
```

缓存：

- path
- duration
- resolution
- stem

---

## IO 并发化

适用于：

- metadata 收集
- JSON 读取
- 文件扫描

可采用：

```python
ThreadPoolExecutor
```

---

# 推荐重构路线

## Phase 1

- 拆分 server.py
- ProviderManager
- Config 模块拆分

## Phase 2

- Repository Layer
- Domain Model
- Cost Tracking

## Phase 3

- Event Bus
- Workflow Engine
- 插件化 Provider

---

# 最终结论

项目已经达到“可长期维护”的水平，但当前最大的风险是：

1. UI 层持续膨胀
2. 配置系统中心化
3. 文件系统耦合
4. Provider 生命周期管理不足

如果未来继续增加 AI 工作流能力，建议优先推进 Repository Layer 与 Service Layer 重构。
