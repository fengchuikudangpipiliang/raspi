从现在开始你遵守这些规则：
1. 你是资深高级工程师，注意开闭原则，高内聚低耦合
2. 代码风格简洁优美，复用性高，注意开闭原则等6大法则，注意设计模式。
3. 严格执行命令本身，不要延伸需求。
4. 做防御性编程，考虑到边缘情况（Edge Cases），并加入必要的错误处理逻辑
5. 所有新增内容同步写入 README.md。
6. 编写代码都要在代码的本身那个文件加上注释，比如一个方法，那么就给这个方法加上详细注释，可能比较难理解加上注释等等

to do:
1.做人脸注册流
新增用户
采集/上传人脸图片
提取人脸编码
保存到 users 和 face_profiles

2.再做人脸身份识别
从数据库读取已注册编码
拿实时画面中的人脸编码去比对
识别出姓名 / 未知用户
在 / 页面显示识别结果
# face3

基于树莓派的人脸识别考勤项目。

本项目当前定位是一个可持续迭代的完整工程骨架，目标不是只做一次性演示，而是逐步形成一套包含前端界面、后端接口、SQLite 数据层、摄像头采集、人脸注册、实时识别、考勤记录、后台管理的完整系统。

## 文档维护约定

从现在开始，本项目后续所有新增模块、页面、流程、约定、运行方式、目录变化，都统一归纳到本 `README.md` 中维护。

这份文档承担以下职责：

- 项目总体说明
- 当前实现进度说明
- 技术方案说明
- 目录结构说明
- 数据库结构说明
- 前端页面说明
- 后续开发任务流说明
- 运行方式说明

后续每完成一个阶段，都应同步更新本文件。

## 一、项目目标

本项目用于实现一个部署在树莓派设备上的人脸识别考勤系统。

核心使用场景如下：

- 树莓派连接摄像头，作为考勤终端
- 用户站在设备前方，系统自动识别人脸并完成签到
- 管理员可以通过后台查看用户信息、考勤记录、终端状态和异常信息
- 系统可以在局域网或单机环境中运行

本项目最终要解决的问题不是单纯“识别人脸”，而是完整地打通下面这条链路：

`用户注册 -> 人脸录入 -> 特征保存 -> 实时识别 -> 自动签到 -> 后台查看记录`

## 二、当前技术栈

当前技术路线已经确定为：

- 前端：Bootstrap
- 后端：FastAPI
- 数据库：SQLite
- 摄像头采集：OpenCV
- 人脸识别：`face_recognition`
- 部署设备：树莓派
- 模板渲染：Jinja2--它的核心作用是**“换汤不换药”**：定义网站通用的结构（头部、脚本、样式），而把具体变化的内容留给子页面去填充。

### 为什么当前选择 `face_recognition`

当前项目是考勤场景，重点是“注册人脸并进行身份比对”，因此第一阶段优先选择 `face_recognition`，原因如下：

- 更贴合“人脸编码 -> 人脸比对 -> 身份识别”的流程
- 对考勤项目来说，上手成本更低
- 适合先完成第一版完整闭环
- 后续如果需要更高效的人脸检测能力，可以再考虑引入 MediaPipe 做辅助检测

当前决策是：

- 第一版先用 `face_recognition` 跑通完整业务
- 后续再根据树莓派性能情况决定是否引入更轻量的检测前置方案

## 三、当前项目整体架构思路

项目逻辑分为五层：

### 1. 配置层

负责管理整个项目的运行参数，比如：

- Web 服务地址
- 摄像头编号
- 图像尺寸
- SQLite 路径
- 考勤时间段
- 人脸识别阈值

当前实现文件：

- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)
- [env.json](/home/luck/face3/env.json)

### 2. 数据层

负责：

- 建立 SQLite 连接
- 初始化表结构
- 管理事务
- 提供基础数据访问接口

当前实现文件：

- [scripts/database/sqlite_db.py](/home/luck/face3/scripts/database/sqlite_db.py)
- [scripts/database/__init__.py](/home/luck/face3/scripts/database/__init__.py)
- [scripts/database/demo.py](/home/luck/face3/scripts/database/demo.py)

### 3. 摄像头采集层

负责：

- 打开摄像头
- 获取视频帧
- 对图像做基础压缩与格式转换

当前实现文件：

- [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py)

### 4. Web 页面层

负责：

- 提供待识别用户端界面
- 提供管理员后台界面
- 通过 FastAPI + Jinja2 输出 HTML 页面

当前实现文件：

- [main.py](/home/luck/face3/main.py)
- [templates/base.html](/home/luck/face3/templates/base.html)
- [templates/user_screen.html](/home/luck/face3/templates/user_screen.html)
- [templates/admin_dashboard.html](/home/luck/face3/templates/admin_dashboard.html)
- [static/css/site.css](/home/luck/face3/static/css/site.css)
- [funnel_test_app.py](/home/luck/face3/scripts/web/funnel_test_app.py)
- [funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)

### 5. 识别与考勤业务层

负责：

- 人脸注册
- 特征提取
- 特征比对
- 去重签到
- 迟到判断
- 异常处理

当前实现文件：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)
- [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py)

当前状态：

- 已经落下“严格版树莓派摄像头人脸识别模块”
- 已经接入树莓派本地摄像头线程
- 已经可以把识别成功结果写入 `attendance_records`
- 已经会在成功签到时落盘保存现场快照到 `data/snapshots/`

## 四、当前已完成内容

截至当前，项目已经完成以下内容。

### 1. 配置系统

已经实现一个基于 JSON 的配置加载类，支持：

- 默认配置
- `env.json` 覆盖默认值
- 配置热重载
- 字典式访问
- 属性式访问

当前已经覆盖的配置内容包括：

- Web 服务配置
- 摄像头配置
- 摄像头 JPEG 质量配置
- 严格识别目标帧率配置
- 人脸识别相关配置
- SQLite 相关配置
- 文件目录配置
- 考勤时间配置
- 外网用户门户会话配置
- 本地成员名单文件路径
- 设备信息配置
- 管理员 API Token 配置

### 2. SQLite 数据库基础设施

已经完成 SQLite 最小可用底座，包括：

- 自动创建数据库文件目录
- 自动建表
- 事务管理
- 连接管理
- 外键约束
- 基础 Repository 封装

已创建的数据表：

- `roster_members`
- `users`
- `face_profiles`
- `attendance_records`

### 3. 前端原型界面

已经完成两个前端页面原型。

#### 待识别用户界面

路由：

- `/`
- `/video_feed`

主要内容：

- 摄像头识别舞台区
- 人脸框提示区域
- 当前识别状态提示
- 今日签到统计概览
- 识别指引
- 现场公告

设计目标：

- 让站在终端前的用户一眼知道自己该怎么站
- 让页面具备“正在识别”的实时感
- 保持界面简洁、清晰、偏终端设备风格

当前已接通：

- MJPEG 实时视频流
- 摄像头后台线程持续读帧
- 基于 `face_recognition` 的轻量级人脸框检测
- 摄像头不可用时的占位提示画面
- 前端定时探测后台心跳，后台中断时自动切换为离线提示文案
- 首页在线探测与视频流错误状态已经拆分，不再因为单次视频流报错就直接误判“后台失联”

#### 管理员后台界面

路由：

- `/admin`

主要内容：

- 统计卡片
- 今日考勤动态
- 用户等级概览
- 异常提醒
- 终端设备状态
- 快速入口

设计目标：

- 让管理员快速看到关键信息
- 后续容易接入真实数据库数据
- 页面结构先稳定，功能后续逐步接入

#### 外网用户门户界面

路由：

- `/portal/register`
- `/portal/login`
- `/portal/home`
- `/portal/face`

主要内容：

- 首次注册页
- 正式密码登录页
- 登录后的用户中心
- 登录后的人脸资料现场拍摄页

设计目标：

- 让树莓派终端页和外网用户门户彻底分离
- 首次注册时强制校验本地名单和管理员预置初始密码
- 登录态下再做人脸上传，避免匿名公网接口直接入库
- 登录态下再做人脸现场拍摄和提交，避免匿名公网接口直接入库
- 后续容易继续扩展为密码修改、历史记录、审核结果页

### 4. 外网用户门户与名单注册流

当前已经实现一条面向单位内部成员的最小业务闭环：

- 服务启动时自动读取 `data/member_roster.csv`
- 名单导入到 `roster_members`
- 用户使用“姓名 + 学号/工号 + 初始密码”完成首次注册
- 注册成功时强制设置新密码
- 后续登录只认新密码，不再认初始密码
- 登录后才能进入外网人脸拍摄页
- `/portal/face` 直接复用 `funnel_test.html` 的动作挑战界面
- 现场拍照提交会复用现有 `RegistrationValidationPipeline`
- 校验通过后提取编码并写入 `face_profiles`

当前新增模块：

- [scripts/web/account_security.py](/home/luck/face3/scripts/web/account_security.py)
- [scripts/web/roster_import_service.py](/home/luck/face3/scripts/web/roster_import_service.py)
- [scripts/web/portal_submission_service.py](/home/luck/face3/scripts/web/portal_submission_service.py)
- [templates/portal_register.html](/home/luck/face3/templates/portal_register.html)
- [templates/portal_login.html](/home/luck/face3/templates/portal_login.html)
- [templates/portal_home.html](/home/luck/face3/templates/portal_home.html)
- [scripts/web/templates/funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)
- [data/member_roster.csv](/home/luck/face3/data/member_roster.csv)

当前门禁规则：

- 不在本地名单中的编号不能注册
- 名字与名单不匹配不能注册
- 初始密码错误不能注册
- 已完成首次注册的编号不能重复注册
- 注册时必须设置符合规则的新密码
- 未登录用户不能访问人脸上传接口
- 每个账号的人脸档案数量有上限，避免被无限写入

### 5. FastAPI 页面入口

当前 [main.py](/home/luck/face3/main.py) 已经实现：

- 启动时初始化数据库
- 启动时同步本地成员名单
- 挂载静态资源目录
- 提供树莓派终端页、后台页和外网门户页路由
- 提供基于 Session 的登录态
- 提供 `/video_feed` 摄像头流接口
- 提供 `/healthz` 前端心跳接口
- 提供 `/api/admin/*` 设备侧管理员 API
- 已为核心页面文件补充结构注释，便于后续继续开发和阅读
- `base.html` 已改为优先使用本地静态前端资源，不再依赖 CDN

### 6. Tailscale Funnel 独立测试页

为避免影响主项目运行逻辑，当前新增了一个独立测试应用：
使用方式
.venv/bin/python -m uvicorn funnel_test_app:app --host 127.0.0.1 --port 8010
- [funnel_test_app.py](/home/luck/face3/funnel_test_app.py)
- [funnel_test_app.py](/home/luck/face3/scripts/web/funnel_test_app.py)
- [funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)

用途：

- 单独启动一个公网用户资料提交 Web 服务
- 不依赖主项目摄像头线程
- 不依赖 SQLite
- 先把“公网入口 + 用户资料采集 + 照片提交”这条链路跑通

当前已支持：

- 浏览器申请摄像头权限并现场采集
- 前端照片预览
- 姓名、学号/工号、电话、备注信息填写
- 授权勾选校验
- 后端图片类型校验
- 后端图片大小限制
- 低流量分步动作挑战
- 动作步骤进度展示
- 采集区单屏紧凑操作布局
- 同人一致性校验
- 可信注册照自动挑选
- 摄像头实时预览镜像校正
- 纸张/屏幕翻拍检测
- 后端注册质量校验流水线
- 单人脸数量检测
- 人脸区域尺寸检测
- 模糊度检测
- 亮度检测
- 姿态检测
- 五官关键点完整性检测
- 后端本地落盘保存
- 每次提交生成独立登记编号

当前保存目录：

- `data/funnel_registrations/<submission_id>/face.xxx`
- `data/funnel_registrations/<submission_id>/metadata.json`

当前质量校验实现文件：

- [registration_validation.py](/home/luck/face3/scripts/web/registration_validation.py)

当前设计特点：

- 使用独立 `RegistrationValidationPipeline` 编排各个校验器
- 每个校验器单独负责一种能力，符合开闭原则和高内聚低耦合
- 校验结果统一输出为 `passed / code / message / score / threshold`
- 前端会把每项校验结果逐项展示给用户

建议测试方式：

```bash
.venv/bin/uvicorn scripts.web.funnel_test_app:app --host 127.0.0.1 --port 8010
sudo tailscale funnel 8010
```

如果 Funnel 打通，手机浏览器打开对应公网地址后，应当能看到公网用户资料提交页，并可执行：

- 开启摄像头
- 开始动作挑战
- 按步骤抓拍当前动作
- 提交资料并拿到登记编号

### 7. 摄像头实时流、严格识别与自动考勤

当前 [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py) 已实现：

- 后台线程持续读取摄像头
- 根据配置设置分辨率和帧率
- 镜像和旋转处理
- 周期性重载已注册人脸库
- 每隔若干帧执行一次严格识别
- 将识别结果叠加到原始画面上
- 识别稳定成功后自动写入 `attendance_records`
- 自动保存现场抓拍图到 `data/snapshots/<日期>/`
- 编码成 JPEG 后通过 MJPEG 持续推送给前端

当前这样设计的原因是：

- 比“每个请求都临时打开一次摄像头”更流畅
- 更适合树莓派持续运行
- `detect_every_n_frames` 可以降低 CPU 压力
- 即使摄像头失败，页面也不会直接崩，而是显示占位提示
- 已注册人脸库定时热重载，避免新增用户后必须重启整个服务
- 识别成功后走冷却时间，避免同一个人站在镜头前被重复签到
- 采集线程与识别线程已解耦，严格识别不会再直接拖垮 MJPEG 画面刷新率

### 8. 严格版树莓派摄像头人脸识别模块

当前新增模块：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)

这个模块的定位不是“简单框出一张脸”，而是给树莓派终端提供一套可以真正用于考勤的严格识别引擎。

#### 模块做了什么

它主要完成下面 10 件事：

1. 从 SQLite 读取所有可识别的人脸档案
2. 只加载“已经正式注册且状态正常”的用户
3. 对每一帧图像做人脸检测
4. 拒绝无人脸和多人脸场景
5. 拒绝脸太小、太模糊、太暗、太亮、姿态不正的帧
6. 对合格单人脸提取编码
7. 和本地已注册编码库做距离比对
8. 拒绝距离过大或结果歧义过高的识别结果
9. 要求同一身份连续多帧稳定命中
10. 稳定成功后再进入考勤写入资格

#### 它为什么叫“严格识别”

因为它不是“只要像就认”，而是把识别拆成多道门禁：

- 单人门禁
- 图像质量门禁
- 姿态门禁
- 身份距离门禁
- 多帧稳定门禁
- 考勤冷却门禁
- 考勤时间窗门禁

只有全部满足，才会返回 `attendance_ready`。

#### 模块内部核心数据结构

1. `KnownFaceProfile`

作用：

- 表示一条已注册人脸档案
- 包含 `face_profile_id / user_id / code / name / image_path / encoding`

2. `PoseSummary`

作用：

- 保存当前帧的人脸姿态摘要
- 包含：
  - `roll_angle`
  - `yaw_offset`
  - `signed_yaw`
  - `pitch_ratio`

3. `RecognitionResult`

作用：

- 表示“当前这一帧”严格识别的完整结果
- 既可以给摄像头线程使用，也可以给调试日志、状态面板和后续前端状态接口使用

它包含的信息有：

- 是否成功
- 失败原因
- 当前画面里有几张脸
- 是否已经识别出身份
- 是否已经满足写考勤条件
- 当前识别到的用户 ID / 姓名 / 编号
- 匹配距离与置信度
- 当前稳定帧数
- 冷却剩余时间
- 是否处于考勤时间段内
- 人脸面积、清晰度、亮度、姿态等中间指标

#### 模块内部主流程

`process_frame(frame_bgr)` 的处理顺序如下：

1. 输入校验

- 空帧直接拒绝
- 没有已注册人脸库直接拒绝

2. 图像预处理

- 根据配置做镜像校正
- 根据配置做旋转校正

3. 人脸检测

- 用缩放后的图像做人脸检测，降低树莓派计算压力
- 没有人脸则返回 `no_face`
- 超过一张脸则返回 `multi_face`

4. 人脸尺寸门禁

- 计算人脸区域在整张图中的占比
- 太小直接返回 `face_too_small`

5. 图像质量门禁

- 对脸部 ROI 做 Laplacian 方差
- 太模糊返回 `image_blurry`

6. 亮度门禁

- 对脸部 ROI 做灰度均值统计
- 过暗或过亮返回 `bad_lighting`

7. 姿态门禁

- 提取人脸 landmarks
- 计算 `roll / yaw / pitch`
- 歪头过大返回 `roll_too_large`
- 侧脸过大返回 `yaw_too_large`
- 抬头低头异常返回 `pitch_bad`

8. 人脸编码提取

- 对当前合格人脸提取 128 维编码
- 提取失败返回 `face_encoding_failed`

9. 身份匹配

- 用当前编码和本地 `known_encodings` 做距离计算
- 最小距离超过阈值则返回 `unknown`
- 如果第一名和第二名太接近，则返回 `ambiguous_match`

10. 多帧稳定确认

- 不是“一帧命中就签到”
- 必须连续多帧识别到同一身份
- 如果还没达到稳定帧数，返回 `match_not_stable_yet`

11. 考勤时间段门禁

- 如果当前时间不在考勤时间窗内
- 返回 `outside_attendance_window`

12. 冷却时间门禁

- 如果同一个人刚刚签到过
- 在冷却期内返回 `attendance_cooldown`

13. 最终放行

- 所有条件都满足时
- 返回 `attendance_ready`

#### 当前严格识别里已经实现的规则

当前已经启用的规则包括：

- 必须是单人入镜
- 人脸面积必须达到最低占比
- 人脸编码距离必须小于系统阈值
- 候选结果不能过于接近，避免误认
- 同一身份只需要最短稳定确认
- 同一身份存在签到冷却时间
- 必须在考勤时间段内才允许写记录

#### 2026-04-22 这一版对严格识别做了什么调整

为了避免“终端画面更流畅了，但识别人太难通过”的问题，这一版把识别策略从“多重质量门禁”改成了“适合考勤现场的快速匹配”。

主要变化：

- 不再把模糊、亮度、姿态等条件作为硬性拦截门槛
- 识别主链路收敛为：
  - 单人检测
  - 人脸面积校验
  - 直接提取编码
  - 与已注册人脸库做距离匹配
  - 最短稳定确认后写入考勤
- 人脸最小面积占比进一步下调，用户不必贴得很近
- 编码距离阈值放宽到 `0.52`
- 稳定确认次数下调到 `1`
- 严格识别目标频率上调到 `5 FPS`

这次调整的目标是：

- 保留“单人入镜 + 编码比对 + 冷却时间 + 时间窗”这些真正影响正确性的约束
- 去掉那些会明显拖慢速度、却不一定提升考勤体验的重门槛
- 让系统先做到“准确识别对应的人脸”和“尽快签到”

#### 终端画面图例文档

我把树莓派终端页里所有可见元素都单独写成了一份文档，便于你后续继续改前端、调后端，或者让 Windows 端 AI 理解页面含义：

- [docs/terminal_recognition_overlay.md](/home/luck/face3/docs/terminal_recognition_overlay.md)

这份文档说明了：

- 页面外层在线/离线提示的含义
- 当前终端页只保留哪些提示
- 每一种识别状态码是什么意思
- 当前版本为什么比之前更容易识别和更容易签到
- 中文字体为什么以前会变成 `????`，现在又是怎么解决的

#### 当前模块还额外提供了什么能力

除了识别本身，它还额外提供：

1. `reload_known_faces()`

作用：

- 从数据库重新加载全部已注册编码
- 供摄像头线程定时热更新使用

2. `prepare_frame()`

作用：

- 统一做镜像和旋转处理
- 避免摄像头线程和识别逻辑各自重复处理方向

3. `annotate_frame()`

作用：

- 保留视频叠加接口
- 当前默认不再绘制常驻调试 HUD
- 便于后续如果需要恢复调试层时继续复用

4. `mark_attendance_committed()`

作用：

- 只有外层真正把考勤记录写入数据库成功后，才开始冷却计时
- 避免“识别成功但数据库写入失败”时误进入冷却状态

5. `known_faces_count()`

作用：

- 返回当前内存中已加载的人脸档案数量
- 便于调试和后台状态展示

#### 这个模块没有做什么

为了边界清晰，这个模块没有直接负责：

- 打开摄像头
- 持续读帧
- MJPEG 推流
- 写数据库考勤记录
- 保存快照文件
- 管理员后台展示

这些都交给外层去做。

这样设计的好处是：

- 模块边界清晰
- 后续接到别的摄像头源也能复用
- 可以单独测试识别逻辑，不强绑定 Web 或摄像头线程
- 符合高内聚、低耦合和开闭原则

### 9. 严格识别接入树莓派摄像头后新增的行为

当前 [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py) 在接入严格识别后，新增了这些运行行为：

1. 启动时初始化严格识别器

- 会尝试创建 `StrictFaceRecognizer`
- 会立即加载当前数据库中的已注册人脸编码

2. 定时热重载人脸库

- 默认每 60 秒重新加载一次人脸档案
- 这样用户在外网门户刚完成人脸注册后，树莓派终端不需要重启太久就能识别到新用户

3. 识别状态实时写入终端内存

- 当前帧识别结果会保存在 `self.recognition_result`
- 当前终端状态文案会保存在 `self.last_attendance_message`
- 最近一次真正写入成功的签到记录摘要会保存在 `self.last_attendance_record`

4. 自动写入考勤记录

- 一旦 `RecognitionResult.attendance_ready == True`
- 外层摄像头线程会自动执行：
  - 保存现场快照
  - 写入 `attendance_records`
  - 通知识别器开启冷却时间

5. 自动保存现场快照

- 快照保存目录：
  - `data/snapshots/<YYYYMMDD>/`
- 文件名格式：
  - `<时间戳>-<人员编号>.jpg`

6. 终端叠字信息更真实

当前终端画面已经去掉常驻调试叠字、扫描取景框和底部等待状态条。

现在只保留：

- 摄像头原始画面
- 左上角一块很小的实时进度提示
- 签到成功后的短暂成功提示
- 摄像头异常时的占位提示

7. 采集线程与识别线程解耦

这是当前树莓派终端提升帧率最关键的一次改造。

旧实现的问题：

- 摄像头线程在同一个循环里同时做：
  - 读帧
  - 严格识别
  - 叠字
  - JPEG 编码
  - MJPEG 推流
- 只要严格识别稍慢，整个视频流就会一起卡住

新实现的改法：

- 采集线程只负责尽快读取摄像头、取最新识别结果做叠加，然后持续输出画面
- 识别线程单独运行，只处理“最新的一帧”
- 识别线程不会追赶旧帧，因此不会不断积压待处理图像

这样做的结果是：

- 严格识别仍然存在
- 但严格识别不再直接阻塞视频流刷新
- 远端页面看到的 MJPEG 流畅度会明显好于“全部堆在一个线程”的实现

8. 终端页前端装饰层已大幅精简

这次把这些 UI 从终端页里移除了：

- 青色扫描取景框
- 扫描线
- 底部等待识别状态条
- 视频流内部左上角常驻调试面板

这样做的原因是：

- 这些元素会遮挡真实摄像头画面
- 对“是否签到成功”这个核心目标帮助不大
- 长时间显示会让终端页更像演示页，而不是现场设备页
- 现在的终端页逻辑是“平时尽量干净，只有成功时给反馈”

同时新增了一块左上角小进度提示：

- 通过 `/api/terminal/status` 获取轻量状态
- 只显示很短的标签、说明和一条细进度条
- 目的是让终端前的人知道“系统是否正在识别”，但不遮挡画面主体

9. 摄像头连续读帧失败时会主动自恢复

当前摄像头线程不再在 `camera read failed` 状态里无限停留。

现在的处理方式是：

- 如果 `capture.read()` 偶发失败，会先显示占位提示
- 如果连续多次读帧失败，系统会主动释放当前摄像头句柄
- 下一轮再重新按正常流程打开摄像头

这样做的原因是：

- 树莓派摄像头在现场运行时，偶发读帧失败并不一定代表设备永久不可用
- 主动释放再重连，通常比“保持一个半失效句柄反复 read”更容易恢复
- 能降低终端长期卡在“摄像头读取失败”占位图上的概率

10. JPEG 压缩质量做成了配置项

新增配置项：

- `camera_jpeg_quality`

作用：

- 控制视频流 JPEG 质量
- 可以在“图像清晰度”和“推流带宽/编码开销”之间做平衡

11. 严格识别目标频率做成了配置项

新增配置项：

- `recognition_target_fps`

作用：

- 控制严格识别线程每秒最多处理多少帧
- 这不是视频流帧率，而是“识别线程的工作频率”
- 把识别频率和画面刷新率分开后，终端性能更容易调优

12. 摄像头叠字已支持中文字体

新增文件：

- [scripts/camera/frame_text.py](/home/luck/face3/scripts/camera/frame_text.py)

作用：

- 统一负责树莓派视频帧内的文字绘制
- 优先查找系统中文字体或项目内字体
- 使用 Pillow 而不是 `cv2.putText`
- 解决终端画面里中文变成 `????` 的问题

字体查找顺序：

1. `env.json` 中显式配置的 `camera_overlay_font_path`
2. 项目 `static/fonts/` 下的字体
3. 树莓派系统常见中文字体，例如：
   - `wqy-zenhei`
   - `wqy-microhei`
   - `Noto Sans CJK`
   - `DroidSansFallbackFull`

### 10. 树莓派摄像头识别模块当前仍然保留的降级能力

如果严格识别器初始化失败，例如：

- `face_recognition` 模块不可用
- 数据库异常
- 识别人脸库加载失败

当前摄像头线程不会直接崩掉，而是回退到原先的简单人脸框检测逻辑。

这样做的意义是：

- 终端页至少还能继续显示摄像头画面
- 不会因为识别模块异常导致整条视频流直接中断
- 便于现场排查

## 五、数据库设计说明

当前 SQLite 表结构如下。

### 1. `roster_members`

成员名单表，存储允许注册的单位内部成员。

字段：

- `id`：主键
- `name`：姓名
- `code`：唯一学号/工号
- `role`：成员角色
- `status`：状态，当前支持 `active / disabled`
- `initial_password_hash`：管理员预置初始密码的哈希
- `created_at`：创建时间
- `updated_at`：更新时间

作用：

- 作为首次注册的白名单来源
- 把“允许注册的人”和“已经正式注册的人”拆开，降低耦合
- 后续可以继续扩展为班级、课题组、部门维度的导入来源

### 2. `users`

用户主表，存储系统中已登记的身份对象。

字段：

- `id`：主键
- `roster_member_id`：关联名单成员
- `name`：姓名
- `code`：唯一编号，可用于学号、工号或人员编码
- `password_hash`：正式登录密码哈希
- `password_changed_at`：首次注册或改密时间
- `last_login_at`：最后登录时间
- `created_at`：创建时间

作用：

- 作为所有用户身份信息的主表
- 保存正式登录凭证
- 后续人脸信息、考勤信息都通过 `user_id` 进行关联

### 3. `face_profiles`

人脸特征表，存储与用户相关的人脸资料。

字段：

- `id`：主键
- `user_id`：所属用户
- `image_path`：原始图片路径
- `encoding`：人脸编码字符串
- `created_at`：创建时间

作用：

- 将用户和人脸特征对应起来
- 后续识别时从这里读取特征进行比对

### 4. `attendance_records`

考勤记录表，存储识别成功或考勤相关流水。

字段：

- `id`：主键
- `user_id`：所属用户
- `check_type`：签到类型
- `check_time`：记录时间
- `snapshot_path`：现场抓拍图路径
- `confidence`：识别置信度

作用：

- 存放实际签到流水
- 供后台页面查询和统计

时间约定：

- `created_at`、`updated_at`、`password_changed_at`、`last_login_at`、`check_time` 统一按设备当前本地时区写入
- 当前默认按树莓派本机时区使用，不再直接依赖 SQLite `CURRENT_TIMESTAMP` 的 UTC 默认值
- 这样可以避免后台看到的记录时间比实际时间少 8 小时

## 六、当前目录结构

当前项目核心目录结构如下：

```text
face3/
├── main.py
├── env.json
├── README.md
├── data/
│   ├── face3.db
│   └── member_roster.csv
├── scripts/
│   ├── camera/
│   │   └── camera.py
│   ├── config/
│   │   └── config.py
│   ├── database/
│       ├── __init__.py
│       ├── demo.py
│       └── sqlite_db.py
│   └── web/
│       ├── account_security.py
│       ├── portal_submission_service.py
│       ├── registration_validation.py
│       └── roster_import_service.py
├── static/
│   └── css/
│       └── site.css
└── templates/
    ├── admin_dashboard.html
    ├── base.html
    ├── portal_home.html
    ├── portal_login.html
    ├── portal_register.html
    └── user_screen.html
```

说明：

- `main.py`：FastAPI 入口
- `env.json`：项目运行配置
- `scripts/config/`：配置系统
- `scripts/database/`：SQLite 数据层
- `scripts/camera/`：摄像头采集层
- `templates/`：前端页面模板
- `static/`：静态资源
- `data/`：本地数据库及后续人脸图片、快照等数据目录
- `data/member_roster.csv`：管理员预置成员名单与初始密码来源

## 七、前端页面设计说明

当前项目既包含原型展示页，也已经开始接通部分真实业务页。

### 1. 待识别用户页的定位

这是面向普通使用者的终端页。

设计重点：

- 大面积展示识别区域
- 强调视觉引导
- 少操作、少干扰
- 适合全屏显示在树莓派终端上

目前页面上预留的未来扩展点包括：

- 实时摄像头画面
- 人脸框叠加
- 识别成功提示
- 签到成功动画
- 失败重试提醒
- 时间显示
- 校区/教室/终端编号显示

### 2. 管理员后台页的定位

这是面向管理人员的操作和查看界面。

设计重点：

- 信息密度高于终端页
- 数据概览直观
- 后续容易扩展为真正的管理系统

目前页面上预留的未来扩展点包括：

- 用户管理
- 人脸录入入口
- 考勤记录筛选
- 异常记录审核
- 数据导出
- 终端在线状态监控
- 权限角色管理

### 3. 外网用户门户页的定位

这是面向单位内部普通成员的外网入口。

设计重点：

- 与树莓派终端识别页彻底分离
- 首次注册只允许名单内成员进入
- 初始密码只用于首次注册，不用于后续登录
- 登录后才能做人脸资料现场拍摄

目前页面上已接通的能力包括：

- 首次注册
- 正式密码登录
- Session 登录态
- 用户中心状态展示
- 单图人脸质量校验
- 人脸编码提取和 `face_profiles` 入库

## 八、开发任务流

当前项目建议按以下四个主任务流推进。

### 任务 1：配置与数据层

目标：

- 完成项目基础配置
- 完成 SQLite 数据层

当前状态：

- 已完成基础版本

后续细化方向：

- 增加更多配置分组
- 增加日志配置
- 增加数据库备份配置

### 任务 2：人脸注册流

目标：

- 新增用户
- 上传或拍摄人脸图片
- 提取人脸编码
- 保存到 `face_profiles`

预期产物：

- 用户注册接口
- 图片上传页面
- 人脸编码保存逻辑

当前状态：

- 已完成“名单导入 -> 首次注册改密 -> 正式登录 -> 现场拍照/备用选图 -> 单图入库”的最小闭环
- 独立 Funnel 动作挑战页仍保留，用于后续升级成更严格的公网采集入口
- 树莓派本地终端的严格识别与考勤写入已经接通

真实业务中的常见处理方式：

- 不会直接信任用户随手上传的一张照片，而是先做基础质量校验
- 要求照片中必须只有一张清晰正脸，且人脸面积不能过小
- 检查模糊、逆光、过暗、过曝、遮挡、侧脸、低头等问题
- 通常要求用户提交多张照片，而不是只交一张
- 很多系统会优先引导用户现场拍照，而不是纯相册上传
- 对高风险场景会增加活体检测，防止用户拿别人照片、截图或屏幕翻拍来冒充
- 注册成功前常常还会加入人工审核，尤其是第一次建档时
- 用户身份和照片不会只靠“用户自己填什么就信什么”，而是要绑定学号、工号、手机号、管理员审批等外部身份信息
- 生产环境会保留审核日志、提交时间、来源方式和失败原因，便于追溯

对本项目的建议治理流程：

- 先做人脸检测，没有检测到脸直接拒绝
- 检测到多张脸直接拒绝，要求重新拍
- 对人脸框大小、清晰度、亮度做最低门槛判断
- 当前公网注册入口只保留摄像头现场采集，不再提供本地文件上传
- 每个用户至少采集 3 张合格照片
- 先进入待审核状态，管理员确认后再正式写入 `face_profiles`
- 后续如果条件允许，再补活体检测或人工复核入口

当前已实现的公网注册链路：

- 页面入口只允许浏览器摄像头现场采集
- 前端先请求后端创建一次动作挑战 `challenge_id`
- 后端从离线模板中随机生成一组 3 步动作：`正脸 -> 轻微左/右侧转 -> 正脸`
- 用户每完成一步，只上传一张压缩后的抓拍图，不再持续发送视频帧
- 后端对当前抓拍图执行单人、人脸尺寸、关键点完整性、姿态规则和同人一致性校验
- 所有步骤都通过后，后端会从通过的正脸抓拍里自动挑出最清晰的一张作为最终注册照
- 正式提交时，前端不再上传最终图片，只提交 `challenge_id`
- 后端根据 `challenge_id` 读取可信注册照，再走现有 `RegistrationValidationPipeline`
- 最终注册照会额外执行纸张/屏幕翻拍检测，尽量拦截拿手机播放预录视频或纸张照片冒充的情况
- 质量校验通过后才保存到 `data/funnel_registrations/<submission_id>/`
- 质量校验失败时，该 challenge 直接作废，必须重新做一次动作挑战

当前活体调优说明：

- 第一轮实测发现“连续眨眼 + 连续送帧”在移动端浏览器下容易漏检自然眨眼，同时后端逐帧分析成本偏高
- 当前已改为“分步动作挑战”，每一步只上传一张抓拍图，显著降低网络流量和后端解码压力
- 现在的挑战步骤基于本地固定模板生成，不依赖在线模型下载
- 后端会在步骤级别做姿态校验和同人一致性校验，避免中途换人继续挑战
- 最终注册照从通过步骤的正脸抓拍里按清晰度自动挑选，减少用户额外拍照次数
- 左右转头门槛已经放宽成“轻微侧转即可通过”，减少普通摄像头下因为转头过猛或过小导致的连续失败

本次新增模块：

- `scripts/web/liveness.py`
  - `ActionChallengeSession`
  - `ActionChallengeAnalyzer`
  - `LivenessChallengeService`
  - `TrustedCapture`
- `scripts/web/funnel_test_app.py`
  - 新增 `POST /api/liveness/challenges`
  - 新增 `POST /api/liveness/challenges/{challenge_id}/captures`
  - `POST /api/submissions` 改为只接受 `challenge_id`
- `scripts/web/templates/funnel_test.html`
  - 改成纯摄像头动作挑战流程
  - 移除连续送帧活体逻辑
  - 前端新增步骤抓拍、步骤进度展示、可信注册照预览和提交门禁
- `scripts/web/registration_validation.py`
  - 新增姿态度量、清晰度评分、人脸编码提取和纸张/屏幕翻拍检测的复用函数

建议的实现架构：

- 不把所有校验逻辑硬写在一个接口函数里，而是拆成独立校验器
- 采用“采集层 -> 质量校验层 -> 活体校验层 -> 审核层 -> 入库层”的流水线结构
- 每个校验器只负责一种能力，例如：
  - `FaceCountValidator`：检查是否只有一张脸
  - `FaceSizeValidator`：检查人脸占比是否足够大
  - `BlurValidator`：检查是否模糊
  - `BrightnessValidator`：检查过暗/过曝
  - `OcclusionValidator`：检查遮挡
  - `PoseValidator`：检查是否大角度侧脸
  - `LivenessValidator`：检查活体
- 每个校验器输出统一结果结构，例如：`passed / code / message / score`
- 主流程只负责编排这些校验器，不关心每个算法细节
- 以后要新增规则时，只新增一个校验器并挂到流水线里，避免改核心主流程

这样做的好处：

- 符合开闭原则：对扩展开放，对修改关闭
- 高内聚：每个模块只管一种质量问题
- 低耦合：活体、模糊、遮挡、亮度等能力可以独立替换
- 方便调参：每个校验项可以单独调整阈值
- 方便审计：能明确知道一张照片为什么失败

当前动作挑战方案说明：

- 不把“注册活体”塞进单张图片质量校验流水线，因为动作挑战本质上是多张抓拍之间的顺序关系，不是单图问题
- 不采用“先挑战通过，再让用户额外拍一张注册照”的模式，因为这样仍然存在挑战通过后换照片的漏洞
- 当前注册端采用“摄像头预览 -> 分步动作挑战 -> 从挑战通过的抓拍中挑选最终注册照 -> 后端质量校验 -> 待审核保存”的链路
- 前端只负责开启摄像头、展示当前步骤、抓拍当前动作和展示步骤进度
- 后端负责动作步骤校验、同人一致性比对、最佳正脸抓拍挑选和可信注册照读取
- 当前入口只有摄像头模式，后续树莓派考勤端也会延续“本地动作挑战 + 同流识别”的思路

建议的模块拆分：

- `ActionChallengeSession`：负责一次动作挑战会话的创建、过期时间、当前步骤和已通过抓拍
- `ActionChallengeAnalyzer`：负责判断当前抓拍是否满足动作步骤，并做同人一致性校验
- `LivenessChallengeService`：负责串联挑战创建、抓拍校验、完成判定和可信注册照读取
- `LivenessResult`：统一返回 `passed / code / message / steps`，供前端展示挑战状态
- `TrustedCapture`：负责把最终可信注册照和步骤进度一起交给正式提交流程

建议的交互顺序：

- 用户选择“摄像头采集”
- 前端开启摄像头后，先请求后端创建一次动作挑战
- 页面显示当前步骤，例如“第 1 步：正视镜头”
- 用户拍摄当前步骤，前端只上传这一张抓拍图
- 后端返回当前步骤是否通过，以及下一步动作指引
- 所有步骤通过后，后端直接从已通过抓拍里挑出最终注册照
- 被选中的最终注册照继续走现有 `RegistrationValidationPipeline`
- 质量校验通过后再保存为 `pending_review`

动作挑战的核心思路：

- 每一步先做人脸检测和 landmarks 提取
- 使用关键点估计轻量姿态，校验当前抓拍是否满足“正脸 / 轻微左转 / 轻微右转”等动作要求
- 每一步都提取人脸编码，并和第一步抓拍做同人一致性比对
- 全部步骤通过后，从所有正脸抓拍里按 Laplacian 清晰度挑出最终注册照
- 最终注册照还会做纸张/屏幕翻拍检测，重点看包裹人脸的矩形边框、周期纹理和高亮反光信号
- 如果检测到多人脸、脸过小、姿态不符、关键点缺失、换人、疑似翻拍或超时，当前步骤直接失败并要求重试

这样接入的原因：

- 不破坏现有单图质量校验流水线，符合开闭原则
- 活体挑战和图片质量检测职责分离，模块边界清晰
- 后续如果要把“左转头”替换成“右转头”“点头”“张嘴”，只需要替换动作步骤规则，不需要改注册主流程
- 动作挑战成功和最终注册照被强绑定，能显著降低“先挑战、后换照片”的绕过风险

如何实现判断“画质太模糊、太暗、被遮挡”：

- 模糊：对脸部 ROI 做 Laplacian variance，低于阈值拒绝
- 光线：检查灰度均值，检查高亮像素比例、低亮像素比例，检查脸部区域左右亮度差
- 遮挡：用 landmarks 看眼睛、鼻尖、嘴角是否稳定存在，关键区域缺失或置信度低则拒绝
- 姿态：根据关键点估计 yaw/pitch/roll，超阈值拒绝
- 单人：多张脸直接拒绝
- 纸张/屏幕翻拍：在最终正脸注册照上检测包裹式矩形边框、疑似屏幕/印刷周期纹理和低饱和高亮反光，多信号同时命中时拒绝

### 任务 3：实时识别考勤流

目标：

- 摄像头实时取流
- 检测人脸
- 比对人脸特征
- 写入考勤记录

预期产物：

- 摄像头识别主循环
- 去重逻辑
- 置信度判定
- 考勤时间判定

当前状态：

- 已完成实时视频流和人脸框检测
- 已完成严格身份识别模块接入
- 已完成自动写入 `attendance_records`
- 已完成自动保存考勤快照

### 任务 4：后台管理与查询流

目标：

- 接通后台页面
- 从数据库读取真实数据
- 显示今日考勤、用户列表、设备状态

预期产物：

- 管理后台接口
- 表格查询
- 筛选与统计
- 异常信息展示

当前状态：

- 树莓派本地 HTML 原型页已完成
- 设备侧管理员 API 已接通，可供 Windows 管理项目通过 Tailscale 调用
- 纯前端意义上的完整管理员后台页面仍待 Windows 侧项目实现

## 九、当前运行方式

### 1. 进入项目目录

```bash
cd /home/luck/face3
```

### 2. 激活虚拟环境

Linux / 树莓派环境下：

```bash
source .venv/bin/activate
```

### 3. 启动 FastAPI 页面

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

页面访问地址：

- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/admin`
- `http://127.0.0.1:5000/portal/register`
- `http://127.0.0.1:5000/portal/login`
- `http://127.0.0.1:5000/portal/home`
- `http://127.0.0.1:5000/portal/face`

### 4. 外网用户门户首次使用说明

1. 先编辑 [data/member_roster.csv](/home/luck/face3/data/member_roster.csv)，维护单位成员姓名、学号/工号、角色、初始密码和状态。
2. 启动服务后，系统会在 startup 阶段自动把名单同步到 `roster_members`。
3. 用户访问 `/portal/register`，使用管理员分发的初始密码完成首次注册，并设置新密码。
4. 首次注册成功后，系统会自动跳转到 `/portal/face` 现场拍摄人脸资料。
5. 后续登录统一访问 `/portal/login`，只使用新密码。

### 5. 外网访问方式

当前项目最适合的外网访问方式是把整个主应用端口暴露出去，而不是只暴露单独测试页。

推荐方式一：Tailscale Funnel

先启动主应用：

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

再开 Funnel：

```bash
sudo tailscale funnel 5000
```

执行成功后，Tailscale 会返回一个公网地址，例如：

```text
https://<你的设备名>.<随机后缀>.ts.net
```

此时外网访问方式就是把本地地址替换成这个公网域名：

- 终端页：`https://<你的域名>/`
- 管理后台：`https://<你的域名>/admin`
- 首次注册页：`https://<你的域名>/portal/register`
- 登录页：`https://<你的域名>/portal/login`
- 用户中心：`https://<你的域名>/portal/home`
- 人脸上传页：`https://<你的域名>/portal/face`

说明：

- `/` 是树莓派终端识别页，主要给现场设备使用
- `/portal/*` 是外网用户门户，给成员在手机或电脑浏览器访问
- 如果用户未登录，直接访问 `/portal/home` 或 `/portal/face` 会自动跳到 `/portal/login`

推荐方式二：内网穿透或反向代理

如果你不用 Tailscale，也可以把 `5000` 端口通过下面任一方式暴露到公网：

- 路由器端口映射
- `frp`
- `nginx` 反向代理 + 公网域名
- 云服务器反向代理回树莓派

无论你用哪种方式，最终都要把公网流量转发到：

```text
http://树莓派IP:5000
```

### 6. 初始化数据库

如果只想验证 SQLite 是否可用，可以执行：

```bash
python main.py
```

或者：

```bash
python -m scripts.database.demo
```

### 7. 树莓派终端严格识别与考勤写入

当前主应用启动后，树莓派本地终端页已经不只是“显示视频流”，而是会真实执行严格识别和自动考勤。

启动命令：

```bash
cd /home/luck/face3
source .venv/bin/activate
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

终端页入口：

- `http://127.0.0.1:5000/`
- 或树莓派局域网/Tailscale 对应地址的 `/`

当前终端运行时会自动执行：

- 打开树莓派摄像头
- 加载本地已注册人脸库
- 周期性重载已注册编码
- 对实时画面执行严格识别
- 在画面上叠加识别状态
- 识别稳定成功后自动写入考勤记录
- 自动保存现场快照到 `data/snapshots/`
- 采集线程和识别线程分离运行，优先保障视频流刷新

当前识别结果写入位置：

- 数据库表：`attendance_records`
- 快照目录：`data/snapshots/<日期>/`

注意：

- 只有已经在 `face_profiles` 中存在编码的用户，终端才能识别
- 只有正式注册且状态正常的用户会被加载到识别人脸库
- 如果现场一直无人脸、多人脸、模糊、侧脸、歪头或亮度异常，终端不会写考勤记录
- 同一用户识别成功后会进入冷却时间，避免连续重复签到
- 识别层通过后，终端现在还会再经过一层可配置的考勤规则门禁，只有规则放行才真正写库
- 当前 `env.json` 已切到测试友好的 `interval_only` 模式，同一用户 `60` 秒内不会重复写入签到，便于现场反复测试
- 后续如果要切回更正式的规则，只需要把 `attendance_rule_mode` 改成 `daily_once`
- 如果你修改了 `camera_jpeg_quality` 或 `recognition_target_fps`，需要重启服务让新参数生效
- 如果你需要指定一套固定的中文字体，可以在 `env.json` 中配置 `camera_overlay_font_path`
- 当前终端页已把前端取景框、状态条和右侧信息卡整体缩小，并把视频流显示方式改成 `contain`
- 这样做的目的是尽量减少页面装饰层对真实摄像头画面的遮挡

### 8. Windows 管理端对接说明

Windows 侧管理员项目不需要启动这个仓库里的额外服务，它只需要通过 Tailscale 请求树莓派设备侧 API。

设备侧管理员 API 文档：

- [docs/raspberry_pi_admin_api.md](/home/luck/face3/docs/raspberry_pi_admin_api.md)

如果 Windows 侧只想看本次增量变化，重点阅读该文档最后的：

- `14. 2026-04-22 增量变更记录`

本次对 Windows 侧可见的新增内容主要有：

- `/api/admin/device/info`
  - 新增 `attendance_policy`
- `/api/admin/device/health` 的 `camera` 对象新增：
  - `known_faces_count`
  - `last_attendance_message`
  - `last_attendance_record`
- `/api/admin/device/health`
  - 新增 `attendance_policy`
  - `camera` 下新增 `last_policy_event`
- `/api/admin/device/metrics`
  - 新增 `attendance_policy`
- `GET /api/admin/attendance`
  - 现在会开始读到树莓派终端实时新增的真实签到记录
- `GET /api/admin/attendance/today-summary`
  - 现在会随着树莓派本地识别成功而实时变化

说明：

- 本次没有修改已有管理员 API 的路由地址
- 本次没有修改管理员 API 的 Bearer Token 鉴权方式
- 本次主要是“新增字段”和“开始产生真实考勤数据”，不是破坏性修改
- 最新一轮又新增了考勤规则策略摘要和最近一次规则判定结果，方便 Windows 端解释为什么这次识别被放行或拦截

### 9. 首页在线探测策略说明

当前树莓派终端首页会同时做两类探测：

1. 后台心跳探测

- 使用 `/healthz`
- 用于判断树莓派 Web 后端是否还在线

2. 视频流可用性探测

- 使用 `/video_feed`
- 用于判断 MJPEG 视频流是否正常显示

当前实现已经把这两者分开处理：

- 单次视频流报错不再直接判定后台失联
- 只有 `/healthz` 连续多次失败时，首页才会切到“离线”
- 视频流异常时，页面会优先尝试自动重连视频流

这样做的原因：

- 某些远端浏览器、Tailscale 中继链路、代理链路下，MJPEG 图片流比普通 JSON 心跳更容易短时失败
- 如果把“视频流出错”和“后台挂了”混为一谈，就很容易出现误报
- 现在的策略更适合远端访问场景，也更符合真实含义

## 十、当前注意事项

### 1. 当前前端是原型页面

说明：

- 外网门户和管理员 HTML 页仍然有原型性质
- 但树莓派本地终端页对应的摄像头识别与考勤写入已经接通，不再只是纯展示

### 2. 当前后端依赖仍需补齐

项目已经开始使用 FastAPI、Jinja2、StaticFiles 等能力，因此后续需要确保依赖环境完整。

当前 `pyproject.toml` 中的人脸识别和图像处理依赖已存在，但 Web 相关依赖还需要根据实际运行情况补充。

### 3. 当前配置类会在导入时触发一次加载

因为项目中存在全局 `cfg = AppConfig()`，所以导入配置模块时会读取一次配置文件，这是当前设计的一部分。

## 十一、后续开发建议

接下来建议按下面顺序推进：

1. 继续优化树莓派终端页实时反馈
2. 完善管理员后台前端页面
3. 增加考勤记录人工修正与补签能力
4. 增加成员名单在线导入与维护能力
5. 增加审核、日志与异常追踪能力
6. 增加更细的统计、筛选、导出能力

## 十二、当前项目一句话总结

`face3` 当前已经具备：

- 配置系统
- SQLite 数据层
- 树莓派摄像头采集与严格识别
- FastAPI 页面入口
- 外网注册与人脸入库闭环
- 设备侧管理员 API
- 自动写入真实考勤记录

下一阶段的重点，是把 Windows 管理项目、树莓派终端实时反馈和后台运维能力继续做完整。
