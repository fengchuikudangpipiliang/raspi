# 树莓派设备侧管理员 API 文档

这份文档描述的是 **树莓派项目本身暴露的设备侧 API**。  
你未来在 Windows 电脑上编写的管理员项目，不需要和树莓派项目放在一起运行，只需要通过 Tailscale 网络访问这些 HTTP 接口即可。

## 1. 使用方式

推荐访问方式：

- Windows 电脑安装 Tailscale
- 树莓派安装 Tailscale
- 两台设备加入同一个 Tailnet
- Windows 管理项目直接请求树莓派的 Tailscale 地址

推荐示例：

- `http://100.x.x.x:5000/api/admin/device/health`
- `http://raspberrypi.your-tailnet.ts.net:5000/api/admin/device/health`

不推荐第一版就走真正公网暴露。  
管理员项目和树莓派都在 Tailscale 里时，直接走 Tailnet 内网更安全。

## 2. 树莓派配置

树莓派项目配置文件是：

- [env.json](/home/luck/face3/env.json)

管理员 API 相关配置项：

```json
{
  "web_host": "0.0.0.0",
  "web_port": 5000,
  "device_id": "face3-pi-01",
  "device_name": "Face3 Raspberry Pi",
  "device_location": "实验室门口",
  "admin_api_token": "face3-admin-change-this-token"
}
```

说明：

- `web_host` 必须是 `0.0.0.0`，这样 Windows 电脑才能通过网络访问
- `device_id` 是设备唯一标识
- `device_name` 是设备展示名称
- `device_location` 是安装位置
- `admin_api_token` 是管理员项目调用 API 时必须携带的鉴权令牌

上线前必须把 `admin_api_token` 改成你自己的随机长字符串。

## 3. 启动方式

在树莓派项目根目录执行：

```bash
cd /home/luck/face3
source .venv/bin/activate
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

如果你后面正式部署，建议去掉 `--reload`。

## 4. 鉴权方式

所有管理员 API 都要求鉴权。

推荐请求头：

```http
Authorization: Bearer 你的admin_api_token
```

也兼容：

```http
X-Admin-Token: 你的admin_api_token
```

推荐统一使用 `Authorization: Bearer ...`。

如果 Token 错误，服务会返回：

```json
{
  "detail": "管理员 API 鉴权失败。"
}
```

HTTP 状态码：

- `401`：Token 错误
- `503`：树莓派没有配置 `admin_api_token`

## 5. 返回格式约定

### 5.1 成功返回

详情接口一般返回：

```json
{
  "ok": true,
  "data": {
    "...": "..."
  }
}
```

列表接口一般返回：

```json
{
  "ok": true,
  "items": [],
  "total": 0
}
```

### 5.2 失败返回

业务错误一般返回：

```json
{
  "detail": "错误说明"
}
```

或者：

```json
{
  "ok": false,
  "message": "错误说明"
}
```

Windows 管理项目应优先按 HTTP 状态码判断是否成功，再读取 JSON 内容。

## 6. 接口总览

当前已经实现的接口分成 5 组：

- 设备信息与健康
- 成员与用户
- 人脸档案
- 考勤记录
- 管理控制

### 6.1 设备信息与健康

- `GET /api/admin/device/info`
- `GET /api/admin/device/health`
- `GET /api/admin/device/metrics`
- `POST /api/admin/device/reload-config`

### 6.2 成员与用户

- `GET /api/admin/roster-members`
- `GET /api/admin/users`
- `GET /api/admin/users/{user_id}`
- `POST /api/admin/users/{user_id}/status`
- `POST /api/admin/users/{user_id}/password/reset`

### 6.3 人脸档案

- `GET /api/admin/face-profiles`
- `GET /api/admin/face-profiles/{face_profile_id}/image`
- `DELETE /api/admin/face-profiles/{face_profile_id}`

### 6.4 考勤记录

- `GET /api/admin/attendance`
- `GET /api/admin/attendance/today-summary`
- `GET /api/admin/attendance/{attendance_id}/snapshot`

## 7. 详细接口说明

### 7.1 获取设备基础信息

`GET /api/admin/device/info`

用途：

- 管理员后台首页展示设备信息
- 标识当前连接的是哪台树莓派

示例请求：

```http
GET /api/admin/device/info HTTP/1.1
Authorization: Bearer your-admin-token
```

示例返回：

```json
{
  "ok": true,
  "data": {
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-20T20:10:00+08:00",
    "server_time": "2026-04-20T20:12:35+08:00"
  }
}
```

### 7.2 获取设备健康状态

`GET /api/admin/device/health`

用途：

- 展示树莓派是否还活着
- 展示数据库是否可用
- 展示摄像头线程是否在运行
- 展示成员名单、人脸目录等基础文件状态

示例返回：

```json
{
  "ok": true,
  "data": {
    "ok": true,
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-20T20:10:00+08:00",
    "server_time": "2026-04-20T20:12:35+08:00",
    "app_uptime_seconds": 155.3,
    "database": {
      "ok": true,
      "sqlite_path": "data/face3.db"
    },
    "camera": {
      "configured": true,
      "running": false,
      "last_frame_at": null,
      "last_opened_at": null,
      "last_error": null,
      "detected_faces": 0
    },
    "files": {
      "roster_exists": true,
      "faces_dir_exists": true,
      "snapshots_dir_exists": true
    },
    "admin_api": {
      "token_configured": true,
      "using_default_token": false
    }
  }
}
```

字段说明：

- `data.ok`：设备侧整体健康是否通过
- `database.ok`：数据库是否可访问
- `camera.running`：本地摄像头线程当前是否正在运行
- `camera.last_frame_at`：最后一次成功拿到摄像头帧的时间
- `admin_api.using_default_token`：是否还在使用默认 Token，生产环境应为 `false`

### 7.3 获取设备性能指标

`GET /api/admin/device/metrics`

用途：

- 后台展示 CPU 负载、内存、磁盘、温度

示例返回：

```json
{
  "ok": true,
  "data": {
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-20T20:10:00+08:00",
    "server_time": "2026-04-20T20:12:35+08:00",
    "system_uptime_seconds": 86400.2,
    "app_uptime_seconds": 155.3,
    "load_average": {
      "one_min": 0.25,
      "five_min": 0.18,
      "fifteen_min": 0.12
    },
    "memory": {
      "total_bytes": 2013265920,
      "available_bytes": 1288490188,
      "used_bytes": 724775732,
      "usage_percent": 36.0
    },
    "disk": {
      "path": "/home/luck/face3/data",
      "total_bytes": 62312374272,
      "available_bytes": 41231237120,
      "used_bytes": 21081137152,
      "usage_percent": 33.83
    },
    "temperature": {
      "cpu_celsius": 51.6
    },
    "process": {
      "pid": 12345
    }
  }
}
```

### 7.4 重新加载配置

`POST /api/admin/device/reload-config`

用途：

- 管理员项目修改树莓派 `env.json` 后，让树莓派重新加载配置

请求体：

- 无

示例返回：

```json
{
  "ok": true,
  "data": {
    "changed": true,
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口"
  }
}
```

### 7.5 获取成员名单

`GET /api/admin/roster-members`

查询参数：

- `search`：按姓名或学号/工号模糊过滤
- `status`：按状态过滤，支持 `active` 或 `disabled`

示例：

```http
GET /api/admin/roster-members?search=张&status=active
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "name": "张三",
      "code": "S2026001",
      "role": "member",
      "status": "active",
      "created_at": "2026-04-20 10:00:00",
      "updated_at": "2026-04-20 10:00:00",
      "registered": true
    }
  ],
  "total": 1
}
```

### 7.6 获取用户列表

`GET /api/admin/users`

查询参数：

- `search`：按姓名或编号模糊过滤
- `status`：按成员状态过滤，支持 `active` 或 `disabled`
- `registered_only`：是否只返回已注册账号，`true` 或 `false`

示例：

```http
GET /api/admin/users?registered_only=true
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 2,
      "roster_member_id": 1,
      "name": "张三",
      "code": "S2026001",
      "role": "member",
      "status": "active",
      "registered": true,
      "password_changed_at": "2026-04-20 10:58:26",
      "last_login_at": "2026-04-20 11:40:12",
      "created_at": "2026-04-20 10:58:26",
      "face_profiles_count": 1,
      "face_profile_ready": true
    }
  ],
  "total": 1
}
```

### 7.7 获取单个用户详情

`GET /api/admin/users/{user_id}`

示例返回：

```json
{
  "ok": true,
  "data": {
    "id": 2,
    "roster_member_id": 1,
    "name": "张三",
    "code": "S2026001",
    "role": "member",
    "status": "active",
    "registered": true,
    "password_changed_at": "2026-04-20 10:58:26",
    "last_login_at": "2026-04-20 11:40:12",
    "created_at": "2026-04-20 10:58:26",
    "face_profiles_count": 1,
    "face_profile_ready": true,
    "face_profiles": [
      {
        "id": 2,
        "user_id": 2,
        "name": "张三",
        "code": "S2026001",
        "image_path": "data/faces/S2026001/20260420115512-1f76d4cc.jpeg",
        "created_at": "2026-04-20 03:55:12",
        "image_url": "/api/admin/face-profiles/2/image"
      }
    ]
  }
}
```

### 7.8 更新用户状态

`POST /api/admin/users/{user_id}/status`

用途：

- 启用或停用某个用户
- 实际上更新的是该用户关联的成员名单状态

请求体：

```json
{
  "status": "disabled"
}
```

允许值：

- `active`
- `disabled`

成功返回：

```json
{
  "ok": true,
  "data": {
    "updated": true,
    "user_id": 2,
    "status": "disabled"
  }
}
```

### 7.9 重置用户登录密码

`POST /api/admin/users/{user_id}/password/reset`

用途：

- 仅针对已经完成首次注册的用户
- 直接重置 `users.password_hash`

请求体：

```json
{
  "new_password": "TempPass2026",
  "confirm_password": "TempPass2026"
}
```

密码规则：

- 至少 8 个字符
- 至少包含 1 个字母和 1 个数字
- 不能直接包含完整学号/工号
- 不能与姓名完全相同

成功返回：

```json
{
  "ok": true,
  "data": {
    "updated": true,
    "user_id": 2
  }
}
```

### 7.10 获取人脸档案列表

`GET /api/admin/face-profiles`

查询参数：

- `limit`：返回条数，默认 100，最大 200
- `user_id`：按用户 ID 过滤
- `code`：按学号/工号精确过滤

示例：

```http
GET /api/admin/face-profiles?code=S2026001
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 2,
      "user_id": 2,
      "name": "张三",
      "code": "S2026001",
      "image_path": "data/faces/S2026001/20260420115512-1f76d4cc.jpeg",
      "created_at": "2026-04-20 03:55:12",
      "image_url": "/api/admin/face-profiles/2/image"
    }
  ],
  "total": 1
}
```

### 7.11 获取人脸图片

`GET /api/admin/face-profiles/{face_profile_id}/image`

用途：

- 管理员后台直接显示用户人脸图片

说明：

- 这个接口直接返回图片文件，不是 JSON
- 仍然需要带管理员 Token

Windows 管理项目可直接把这个 URL 作为 `<img>` 或图片下载地址使用。  
如果使用浏览器组件或前端框架，需要确保请求头里能带上 `Authorization`。

### 7.12 删除人脸档案

`DELETE /api/admin/face-profiles/{face_profile_id}`

用途：

- 删除数据库中的人脸档案记录
- 同时删除磁盘上的照片文件

成功返回：

```json
{
  "ok": true,
  "data": {
    "deleted": true,
    "face_profile_id": 2
  }
}
```

### 7.13 获取考勤记录列表

`GET /api/admin/attendance`

查询参数：

- `limit`：默认 50，最大 300
- `date`：按日期过滤，格式 `YYYY-MM-DD`
- `code`：按编号精确过滤
- `name`：按姓名模糊过滤

示例：

```http
GET /api/admin/attendance?date=2026-04-20&limit=100
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 11,
      "user_id": 2,
      "name": "张三",
      "code": "S2026001",
      "check_type": "check_in",
      "check_time": "2026-04-20 08:01:25",
      "snapshot_path": "data/snapshots/20260420/xxx.jpg",
      "snapshot_url": "/api/admin/attendance/11/snapshot",
      "confidence": 0.91
    }
  ],
  "total": 1
}
```

### 7.14 获取今日考勤汇总

`GET /api/admin/attendance/today-summary`

查询参数：

- `date`：可选，格式 `YYYY-MM-DD`

说明：

- 如果不传 `date`，默认返回树莓派本地当天的汇总

示例返回：

```json
{
  "ok": true,
  "data": {
    "date": "2026-04-20",
    "registered_users": 12,
    "checked_in_users": 9,
    "attendance_records": 9,
    "absent_users": 3
  }
}
```

### 7.15 获取考勤快照

`GET /api/admin/attendance/{attendance_id}/snapshot`

用途：

- 在管理员后台查看某条考勤记录对应的抓拍图

说明：

- 该接口直接返回图片文件，不是 JSON
- 如果该考勤记录没有快照，会返回 `404`

## 8. Windows 管理项目推荐调用方式

推荐把树莓派基地址和 Token 配成环境变量：

```txt
FACE3_PI_BASE_URL=http://raspberrypi.tailnet-name.ts.net:5000
FACE3_PI_ADMIN_TOKEN=your-admin-token
```

请求时统一带：

```http
Authorization: Bearer your-admin-token
```

推荐在 Windows 管理项目里封装一个统一请求层：

- 自动拼接 `base_url`
- 自动附带 Bearer Token
- 自动处理 `401`
- 自动把非 2xx 转成异常

## 9. 建议的 Windows 后台页面对应关系

你后面 Windows 管理项目可以直接按下面映射做：

- 仪表盘
  - `/api/admin/device/health`
  - `/api/admin/device/metrics`
  - `/api/admin/attendance/today-summary`

- 成员管理
  - `/api/admin/roster-members`
  - `/api/admin/users`
  - `/api/admin/users/{user_id}`
  - `/api/admin/users/{user_id}/status`
  - `/api/admin/users/{user_id}/password/reset`

- 人脸档案
  - `/api/admin/face-profiles`
  - `/api/admin/face-profiles/{face_profile_id}/image`
  - `/api/admin/face-profiles/{face_profile_id}`

- 考勤记录
  - `/api/admin/attendance`
  - `/api/admin/attendance/today-summary`
  - `/api/admin/attendance/{attendance_id}/snapshot`

## 10. 当前版本限制

当前设备侧 API 已经够你编写第一版管理员项目，但有几个边界需要明确：

- 暂时没有多树莓派聚合能力
- 暂时没有管理员账号体系，只有 Token 鉴权
- 暂时没有考勤记录人工修改接口
- 暂时没有成员名单在线导入接口
- `face_profile` 和 `attendance` 图片访问仍然依赖管理员请求时附带 Token

## 11. 推荐下一步

等你 Windows 管理项目第一版能跑起来以后，树莓派这边建议继续加：

- 考勤记录人工补录/修正接口
- 成员名单导入接口
- 人脸档案审核与替换接口
- 操作日志接口
- 管理员 Token 轮换机制

## 12. 文档对应源码

本次 API 主要实现位置：

- [main.py](/home/luck/face3/main.py)
- [scripts/admin_api.py](/home/luck/face3/scripts/admin_api.py)
- [scripts/device_status_service.py](/home/luck/face3/scripts/device_status_service.py)
- [scripts/database/sqlite_db.py](/home/luck/face3/scripts/database/sqlite_db.py)
- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)

## 13. 2026-04-21 增量变更记录

这一节只写 **相对于上一版文档新增的变化**，方便 Windows 管理项目按增量适配。

### 13.1 是否改动了 Windows 端原有接口

没有改动已有接口的：

- 路由路径
- HTTP 方法
- 鉴权方式
- 主要返回结构外层格式

也就是说，下面这些接口地址没有变：

- `/api/admin/device/info`
- `/api/admin/device/health`
- `/api/admin/device/metrics`
- `/api/admin/roster-members`
- `/api/admin/users`
- `/api/admin/users/{user_id}`
- `/api/admin/face-profiles`
- `/api/admin/attendance`
- `/api/admin/attendance/today-summary`

所以如果 Windows 那边已经按这些地址写请求，**请求本身不会失效**。

### 13.2 本次属于“新增字段”，不是破坏性修改

这次新增的是树莓派本地严格识别接入后带出来的状态字段，主要体现在：

- `GET /api/admin/device/health`

`data.camera` 下新增字段：

- `known_faces_count`
- `last_attendance_message`
- `last_attendance_record`

新增字段示例：

```json
{
  "camera": {
    "configured": true,
    "running": true,
    "last_frame_at": "2026-04-21T09:30:10+08:00",
    "last_opened_at": "2026-04-21T09:28:00+08:00",
    "last_error": null,
    "detected_faces": 1,
    "known_faces_count": 3,
    "last_attendance_message": "签到成功: 张三/S2026001",
    "last_attendance_record": {
      "attendance_id": 15,
      "user_id": 2,
      "name": "张三",
      "code": "S2026001",
      "confidence": 0.93,
      "snapshot_path": "data/snapshots/20260421/20260421093010-S2026001.jpg"
    }
  }
}
```

说明：

- `known_faces_count`：当前树莓派终端已加载到内存中的可识别人脸档案数量
- `last_attendance_message`：最近一次识别状态提示，适合 Windows 后台首页直接显示
- `last_attendance_record`：最近一次真正写入成功的考勤记录摘要

### 13.3 本次新增的运行行为

树莓派本地终端识别现在已经接入严格识别流程。

新增行为：

- 本地摄像头会对已注册用户做严格人脸识别
- 满足稳定识别条件后，会自动写入 `attendance_records`
- 同时自动保存一张考勤快照到 `data/snapshots/...`

这意味着 Windows 端已有的下面两个接口，现在会开始读到真实新增数据：

- `GET /api/admin/attendance`
- `GET /api/admin/attendance/today-summary`

如果 Windows 后台之前已经实现了考勤记录列表和今日汇总页面，那么现在它们应该会自然看到新识别产生的数据，不需要改请求地址。

### 13.4 Windows 端是否一定能接收到

结论：

- 如果 Windows 端只是按接口地址发请求并读取已有字段，那么**可以继续正常工作**
- 如果 Windows 端对 JSON 做了“严格字段白名单反序列化”，那就需要把新增字段设为可选字段

最稳妥的建议：

- Windows 端数据模型对 `device/health` 的 `camera` 对象使用“可选字段兼容”
- 不要要求返回 JSON 必须和旧版字段完全一致

推荐把下面 3 个字段在 Windows 端定义为可选：

- `known_faces_count?: number`
- `last_attendance_message?: string | null`
- `last_attendance_record?: object | null`

### 13.5 Windows 端 AI 需要重点知道的结论

给 Windows 侧 AI 的一句话总结：

- 本次没有改管理员 API 的路由和鉴权
- 只是给 `/api/admin/device/health` 增加了几个可选字段
- 树莓派本地终端现在会自动写入真实考勤记录和快照
- 所以 Windows 侧只需要兼容新增字段，不需要重写原有请求层
