# noVNC 键盘映射补丁（ZStack zsv-novnc）

修复 ZStack Web 控制台中 **`@`、`#`、`$` 等 Shift 组合键无法输入**，以及输入法激活时部分按键完全无响应的问题。

- 适用对象：ZStack 5.x 管理节点上的 `zstack-ui` 前端包
- 目标文件：`/usr/local/zstack/zstack-ui/zstack-ui/zsv-novnc/2369.<hash>.js`
- 内嵌组件：`novnc:5.0.0`（noVNC 官方 `Keyboard` 实现）
- 现场验证版本：ZStack-ZSvirt 1.0.0.93（release h84r），`2369.b57e7bebec.js`

---

## 1. 根因

### 缺陷 A：Shift 字符未发送修饰键

`_handleKeyDown()` 把按键换算成 keysym 后，**只发送目标 keysym，从不发送 Shift 修饰键**。

| 场景 | 后果 |
|---|---|
| VNC 图形会话（X11/Windows） | 通常无碍，服务端按 keysym 处理 |
| Linux **文本控制台**（`login:` 提示符） | qemu 需按**扫描码**还原按键，缺少修饰键 → `@`/`#` 等被丢弃 |

### 缺陷 B：输入法激活时按键被丢弃

当 IME 生效时 `event.key` 返回多字符（如 `"Process"`），命中：

```js
if (1 !== e.length) return null;
```

该按键被直接放弃，表现为「某些键完全没反应」。

---

## 2. 补丁内容（两处，最小改动）

### 补丁 1 — keysym 回退推导（修缺陷 B）

```js
// 修改前
if(1!==e.length)return null;let i=e.charCodeAt();return i?t1.lookup(i):null
```

```js
// 修改后：key 非单字符时，改用 event.code + event.shiftKey 按 US 布局推导
if(1!==e.length){let n=(function(q){let m={Digit1:"1!", ... ,Space:"  "};
  let s=m[q.code];if(!s)return null;
  return q.shiftKey?s.charAt(1):s.charAt(0)})(t);
  return n?t1.lookup(n.charCodeAt()):null}let i=e.charCodeAt();return i?t1.lookup(i):null
```

覆盖键位：`Digit0-9`、`Minus`、`Equal`、`BracketLeft/Right`、`Backslash`、`Semicolon`、
`Quote`、`Backquote`、`Comma`、`Period`、`Slash`、`Space`。

### 补丁 2 — 显式补发 Shift 修饰键（修缺陷 A）

```js
// 修改前
this._sendKeyEvent(i,e,!0)
```

```js
// 修改后：Shift 类字符发送完整序列
(t && t.shiftKey && i && i<256 &&
 "!@#$%^&*()_+{}|:<>?~".indexOf(String.fromCharCode(i)) > -1 &&
 "ShiftLeft" !== e && "ShiftRight" !== e)
  ? ( Shift_L↓ , keysym↓ , keysym↑ , Shift_L↑ )
  : this._sendKeyEvent(i,e,!0)
```

字符集：`! @ # $ % ^ & * ( ) _ + { } | : < > ? ~`

**字母大小写路径未改动**，避免扩大影响面。

---

## 3. 使用方法

在**管理节点**上以 root 执行：

```bash
# 1) 先看状态（不修改任何文件）
python3 apply_novnc_keyboard_patch.py --check

# 2) 打补丁（自动备份 + node 语法校验，幂等）
python3 apply_novnc_keyboard_patch.py --apply

# 3) 回滚（指定备份文件）
python3 apply_novnc_keyboard_patch.py --revert \
    /usr/local/zstack/zstack-ui/zstack-ui/zsv-novnc/2369.js.bak-YYYYmmdd-HHMMSS \
    --target /usr/local/zstack/zstack-ui/zstack-ui/zsv-novnc/2369.<hash>.js
```

脚本行为：

| 特性 | 说明 |
|---|---|
| 幂等 | 已打过则跳过；处于「部分打补丁」状态时拒绝修改 |
| 安全 | 目标串必须唯一命中，否则报错退出，不写入 |
| 备份 | 默认在同目录生成 `2369.js.bak-<时间戳>` |
| 校验 | 自动执行 `node --check`，语法失败会明确报告 |

### HA 环境要求

管理节点为 HA 时，**两台都必须打补丁**（逐台执行、逐台校验），否则主备切换后前端会退回未修复版本：

```bash
# 示例：先 .169，校验通过后再 .167
for mn in 55.32.170.169 55.32.170.167; do
  scp apply_novnc_keyboard_patch.py root@$mn:/tmp/
  ssh root@$mn "python3 /tmp/apply_novnc_keyboard_patch.py --apply"
done
```

### 浏览器侧

目标文件名带内容哈希且**未变更**，浏览器会继续使用缓存，**必须强制刷新**：

- `F12` → Network 勾选 `Disable cache` → 刷新；或
- 直接使用无痕窗口

---

## 4. 验证

### 4.1 补丁逻辑行为测试（Node，15 项）

```bash
node tests/test_keysym_fallback.js     # 10 项：Shift 字符映射 + 正常路径不回归
node tests/test_shift_burst.js         # 5  项：修饰键序列 + 不递归/不扩面
```

实测结果（本仓库提交时）：

```
Shift+2→@(0x40)  Shift+3→#(0x23)  Shift+4→$(0x24)  Shift+/→?(0x3f)
Shift+;→:(0x3a)  Shift+'→"(0x22)  无Shift的2→2(0x32)
单字符路径 @ # a 均保持原行为                                   PASS
Shift+2 事件序列: Shift↓ → @↓ → @↑ → Shift↑                    PASS
Shift+A / 无Shift数字 / Shift 键自身：保持原行为，不递归         PASS
合计 PASS=15 FAIL=0
```

### 4.2 现场实施记录

| 项目 | 结果 |
|---|---|
| 节点 | 55.32.170.169、55.32.170.167（逐台实施） |
| 备份 | 各节点 `/root/novnc-patch-<时间戳>/` |
| md5（两节点一致） | `bc5f4959e085e8e467a62eb04c10808c` |
| 文件大小 | 156824 → 157519 字节 |
| `node --check` | 本地与两台节点均通过 |
| HTTPS 下发 | 两节点均 `200`，157519 字节，含补丁标记 |
| 页面回归 | `/`、`/api/ping`、`/graphql` 均 200 |
| 副本排查 | 全 UI 目录仅 1 份 Keyboard 实现，无被下发的备份副本 |

> 浏览器交互验收（实际敲 `@`/`#` 登录）由使用方完成；服务端与补丁逻辑已验证到位。

---

## 5. 已知边界

1. 字符推导按 **US 布局**。客户机内若为非 US 布局，Shift 字符仍按 US 映射发送。
2. 未处理 `AltGr`（右 Alt）组合，欧文特殊字符需另行适配。
3. 上游升级 `zsv-novnc` 会覆盖本补丁，升级后需重新执行 `--check` 并重打。
4. 补丁修改的是**前端压缩产物**，并非源码。若上游发布对应源码修复，应以源码方式替代本补丁。

---

## 6. 目录结构

```
zstack/novnc-keyboard-patch/
├── README.md                          # 本文件
├── apply_novnc_keyboard_patch.py      # 幂等补丁脚本（apply / check / revert）
├── snippets/
│   ├── p1_before.txt  p1_after.txt    # 补丁 1 改动前后原文（供评审）
│   └── p2_before.txt  p2_after.txt    # 补丁 2 改动前后原文
└── tests/
    ├── test_keysym_fallback.js        # 补丁 1 行为测试
    └── test_shift_burst.js            # 补丁 2 行为测试
```
