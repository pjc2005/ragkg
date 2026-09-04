# WorldQuant BRAIN — 新手上路

> 创建：2026-09-01（是我 Ayana 第一次接触 BRAIN）。来源：两篇微信文章《顾问收入组成及计算》《一文助你成为BRAIN兼职研究顾问》+ 平台实操。

## 我的账号信息
- User ID：JP65204
- 注册日期：2026/09/01
- 大学：Nanjing University of Posts and Telecommunications（注册时学校里没有就选 Other 手填全名）
- 当前阶段：用户权限（蓝色导航）/ Score 0 / Alphas 0 / No Level
- 目标：凑齐 Challenge Score **10,000 分（Gold Level）** → 次日等顾问邀请

## 平台两类权限
- **用户权限**（导航栏蓝色）：初始状态，数据/地区/算力都受限。
- **顾问权限**（导航栏绿色）：收到邀请、签合同后才有。提交才开始真正计报酬。

## Challenge Score 攒分规则（敲黑板）
- 每日提交加分上限 **2000 分**，交再多也只按 2000 算。
- 分数 **T+1 更新**，约北京时间下午 14:00–15:00。
- 通常 **1 个 alpha ≈ 1500–2000 分，2 个 alpha 稳拿当天 2000 分**。
- 平台统一用**美东时间**：北京时间 19 号下午–20 号上午计为美东 19 号。
- 查到一万分（Gold）后次日系统自动发顾问邀请；有风控，不一定人人都收到。

## 推荐提交节奏（新人）
- 每天 2 个 alpha（能拿满当天 2000 分）即可，不必贪多。
- 前三个月是"试用期"，重点是提升 value factor（初始 0.5），不是刷量。
- 1.5 大法：一天只交 1 个 alpha 却拿到 Base Payment>1.5USD，说明质量不错；只有 1.2 说明质量差、会拉低 value factor。

## 第一个 Alpha 往哪个方向找（新手思路）
- 用 1~3 个数据字段 + 常用算子组合，先做出能通过默认筛选、样本外别太差的信号。
- 常用算子：ts_rank, ts_zscore, group_rank, zscore, ts_delay, ts_mean, returns, 各数据集的 *_ret_* 字段。
- 优先看官网给的示例：https://platform.worldquantbrain.com/learn/documentation/create-alphas/19-alpha-examples
- 别一上来就上几十个字段的大杂烩——新手期做"少字段、稳定、能过平台筛选"的 alpha 更划算。

## 学习资源
- 平台 LEARN 界面（视频+文档）：https://platform.worldquantbrain.com/learn
- Alpha 示例：learn/documentation/create-alphas/19-alpha-examples
- 中文论坛（转正后解锁更多进阶内容）
- 《零基础学量化》官方免费公开课（WQ 研究员主讲，不定时开课）

## 从"用户"到"正式顾问"的完整链条
1. 注册账号（已完成）
2. 提交 Alpha 攒 Challenge Score 到 10,000 → Gold Level → 次日收邀请
3. 填顾问申请表（务必先读"申请流程"，避免退回）
4. 签顾问合同 → 解锁顾问权限 → 成为"有条件顾问"
5. 背调（3–4 周，在职者可能被联系补充材料，但不会联系雇主）
6. 提供银行卡 → 正式顾问

## 顾问收入四部分（转正后才开始，先了解）
1. Base Payment：基础薪酬，每日结算，Regular+Super 各 1–60 USD，日上限 120。
2. Quarterly Payment：季度奖，每季度有 20 天提交过 alpha 才够格，100–25000 USD。
3. Competition：比赛奖金（如 IQC/ATOM，4–6 周一场）。
4. Referral Bonus：推荐奖金，200 USD/人，上不封顶。
- 税务：劳务所得代扣代缴，800 以内免税，以上 20%，每年 4 月汇算清缴。

## 待办 / 下一步
- [ ] 自己动手交 2 个 alpha，体验平台流程、看分数怎么涨
- [ ] 记下每天的 Challenge Score 变化，确认 T+1 更新规律
- [ ] 有余力再考虑自动化（先别急着投——见下面原则）

## 自动化前提与原则（重要）
- 自动化的价值在省机械劳动 + 保节奏，**不是代替研究**。
- 无脑批量交垃圾会拉低质量因子/value factor，反而扣分。自动化要克制、像人。
- 真正能赚钱的信号靠研究思路，本地 12B 级模型胜任不了独立研发，别指望躺赚。
- 评估阶段：注册一周交了 alpha 觉得有戏 → 再上"表达式模板 + 批量回测"半自动流水线。