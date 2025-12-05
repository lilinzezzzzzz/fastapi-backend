
### 1\. 核心最佳实践 (Must-Dos)

#### ✅ 必须正确处理可变默认值 (Mutable Defaults)

这是最常见也是最危险的错误。永远不要直接使用 `list` 或 `dict` 作为默认值。

  * **错误的做法：** `tags: list = []` (所有实例共享同一个列表)
  * **正确的做法：** 使用 `field(default_factory=...)`

<!-- end list -->

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class User:
    name: str
    # ✅ 每个实例都会获得一个新的空列表
    tags: List[str] = field(default_factory=list) 
```

#### ✅ 默认开启 `slots=True` (Python 3.10+)

除非你有非常具体的理由（如需要动态添加属性），否则应尽可能使用 `slots=True`。

  * **好处：** 内存占用更低，访问属性速度更快。
  * **用法：** `@dataclass(slots=True)`

#### ✅ 优先考虑不可变性 `frozen=True`

如果你的数据对象不需要修改（例如配置项、DTO），将其设为不可变。

  * **好处：** 线程安全，可哈希（可以用作字典的 key），代码意图更清晰。
  * **用法：** `@dataclass(frozen=True)`

#### ✅ 强制使用关键字参数 `kw_only=True` (Python 3.10+)

当字段较多（超过3个）时，强制调用者使用关键字参数可以极大地提高可读性，并防止重构时的参数顺序错误。

```python
@dataclass(kw_only=True)
class Config:
    host: str
    port: int
    debug: bool = False

# ✅ 必须这样调用：Config(host="localhost", port=8080)
# ❌ Config("localhost", 8080) 会报错
```

-----

### 2\. `__post_init__` 的正确用法

`__post_init__` 是 `dataclass` 唯一允许你插入逻辑的地方，但要克制使用。

  * **适合场景：**
      * 计算派生字段（例如：根据 `firstName` 和 `lastName` 生成 `fullName`）。
      * 轻量级验证（例如：检查 `age > 0`）。
  * **不适合场景：**
      * 复杂的业务逻辑。
      * 耗时的操作（数据库查询、API 调用）。
      * **深度验证**（如果需要复杂验证，请直接使用 Pydantic）。

<!-- end list -->

```python
@dataclass
class Rectangle:
    width: float
    height: float
    area: float = field(init=False) # 告诉 dataclass 这个字段不需要在 __init__ 中传参

    def __post_init__(self):
        self.area = self.width * self.height
```

-----

### 3\. 何时选择 Dataclass vs 其他工具

不要把 `dataclass` 当作万能锤子。根据场景选择正确的工具：

| 场景 | 推荐工具 | 原因 |
| :--- | :--- | :--- |
| **内部数据传递** | **Dataclass** | 标准库原生支持，性能好，开销小。 |
| **外部数据验证 (API/JSON)** | **Pydantic** | Dataclass **不做**运行时类型检查。Pydantic 提供强大的解析和验证功能。 |
| **简单的字典结构** | **TypedDict** | 如果你只需要给字典加类型提示，并不需要类的方法，用 `TypedDict` 更轻量。 |
| **只读且极简** | **NamedTuple** | 比 Dataclass 更轻量，但不支持继承，且不支持默认值工厂。 |

-----

### 4\. 常见的“反模式” (Anti-Patterns)

  * ❌ **反模式 1：把它当做普通的 Class**
    如果你的类包含大量的方法和复杂的 `__init__` 逻辑，普通的 `class` 可能是更好的选择。Dataclass 的初衷是作为"数据的容器"。
  * ❌ **反模式 2：忽略 `repr=False` 对敏感字段的处理**
    如果字段包含密码或密钥，记得在 `field()` 中设置 `repr=False`，防止打印日志时泄露。
    ```python
    password: str = field(repr=False)
    ```
  * ❌ **反模式 3：继承噩梦**
    Dataclass 的继承机制（尤其是涉及默认值字段的顺序时）非常脆弱。尽量通过 **组合 (Composition)** 而非继承来复用字段。

-----

### 5\. 终极示例代码

这是一个结合了上述最佳实践的完整示例：

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass(frozen=True, slots=True, kw_only=True)
class UserProfile:
    """
    一个不可变、高性能、强制关键字参数的用户资料类。
    """
    id: int
    username: str
    email: str
    # 敏感信息不包含在 repr 输出中
    api_key: str = field(repr=False)
    
    # 可变默认值必须使用 default_factory
    roles: List[str] = field(default_factory=list)
    
    # 派生字段，不需要初始化传参
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        # 轻量级验证
        if "@" not in self.email:
            raise ValueError("Invalid email format")

# 使用示例
try:
    user = UserProfile(
        id=1, 
        username="gemini_user", 
        email="user@example.com", 
        api_key="secret_123"
    )
    print(user) 
    # 输出: UserProfile(id=1, username='gemini_user', email='user@example.com', roles=[], created_at=...)
    # 注意 api_key 未显示
except ValueError as e:
    print(f"Error: {e}")
```

### 总结

对于大多数现代 Python 项目（3.10+），默认起手式应该是：
`@dataclass(slots=True, frozen=True, kw_only=True)`
只有当你确实需要可变性或兼容旧版本时，再移除这些参数。
