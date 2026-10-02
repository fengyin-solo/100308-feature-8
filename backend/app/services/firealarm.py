"""消防设施业务规则。

围绕「灭火剂什么时候失效」这条主线组织：

* 有效期与压力都按当天实时计算，过期和压力不足用两个独立标记分开标；
* 按月分档列出已过期与 30 天内快到期的设施；
* 批量检查一次勾选多台：逐台带出上次检查日期与检查人员，已过期的整台退回、
  要求先安排更换，其余照常落检查记录；
* 同一批次号重复提交只记一次（幂等），已过期/已更换的设施不再进入下一轮清单。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.store import store

MODULE = "firealarm"
CHECKS_TABLE = "_firealarm_checks"
BATCHES_TABLE = "_firealarm_batches"

REQUIRED_FIELDS = ["设施编号", "设施类型", "所属站点", "灭火剂量", "有效期至"]
STATUSES = ["合格", "压力不足", "已过期", "已更换"]
ACTION_RULES = {"登记不足": "压力不足", "登记过期": "已过期", "安排更换": "已更换"}

EXPIRE_SOON_DAYS = 30
LOW_PRESSURE = "不足"
NORMAL_PRESSURE = "正常"

# 灭火剂量按充装质量分档（kg）；气体灭火装置按钢瓶充装量也走同一口径。
AGENT_BUCKETS = [
    (5, "小容量（≤5kg）"),
    (20, "中容量（5-20kg）"),
    (10**9, "大容量（>20kg）"),
]


def _today() -> date:
    return date.today()


def parse_date(value: Any) -> date | None:
    """容忍各种日期写法；解析不了时返回 None，由调用方决定怎么提示。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_agent_kg(value: Any) -> float | None:
    """从「4kg」「35 kg」这类写法里取出数值，用于灭火剂量分档。"""
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


def agent_bucket(value: Any) -> str:
    kg = parse_agent_kg(value)
    if kg is None:
        return "未标注量"
    for limit, label in AGENT_BUCKETS:
        if kg <= limit:
            return label
    return AGENT_BUCKETS[-1][1]


def expire_bucket(expire: date | None, today: date) -> str:
    if expire is None:
        return "无有效期"
    if expire < today:
        return "已过期"
    if (expire - today).days <= EXPIRE_SOON_DAYS:
        return f"{EXPIRE_SOON_DAYS}天内到期"
    return "正常"


def month_key(value: date | None) -> str:
    """分月键：已过期的归到实际过期月份，便于按月翻看。"""
    return value.strftime("%Y-%m") if value else "未知月份"


def enrich(row: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """给台账行补上实时计算的分档/标记字段；不改动原始记录。"""
    today = today or _today()
    expire = parse_date(row.get("有效期至"))
    days_left = (expire - today).days if expire else None
    is_expired = bool(expire and expire < today) and row.get("status") != "已更换"
    is_low_pressure = str(row.get("压力状态") or "").strip() == LOW_PRESSURE
    replaced = row.get("status") == "已更换"

    if replaced:
        state = "已更换"
    elif is_expired:
        state = "已过期"
    elif is_low_pressure:
        state = "压力不足"
    else:
        state = "合格"

    item = dict(row)
    if replaced:
        # 已更换的设施已脱离有效期管理，归档单独成档，避免混进「已过期」。
        expiry_tier = "已更换"
    else:
        expiry_tier = expire_bucket(expire, today)
    item.update({
        "灭火剂量档": agent_bucket(row.get("灭火剂量")),
        "有效期档": expiry_tier,
        "剩余天数": days_left,
        "过期": is_expired,
        "压力不足": is_low_pressure,
        "已更换": replaced,
        "实时状态": state,
        "纳入检查清单": not (is_expired or replaced),
    })
    return item


def latest_check(facility_id: int) -> dict[str, Any] | None:
    """一台设施最新一次检查记录，供清单逐台带出。"""
    records = [c for c in store.rows(CHECKS_TABLE) if int(c.get("facility_id", 0)) == facility_id]
    if not records:
        return None
    return sorted(records, key=lambda c: str(c.get("check_date", "")), reverse=True)[0]


class FirealarmService:
    # ---------- 台账 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        agent: str | None = None,
        expiry: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        today = _today()
        items = [enrich(row, today) for row in store.rows(MODULE)]
        if keyword:
            items = [
                item for item in items
                if keyword in str(item.get("设施编号", ""))
                or keyword in str(item.get("所属站点", ""))
                or keyword in str(item.get("设施类型", ""))
            ]
        # status 兼容老页面（合格/压力不足/已过期/已更换），按实时状态过滤。
        if status:
            items = [item for item in items if item["实时状态"] == status]
        if agent:
            items = [item for item in items if item["灭火剂量档"] == agent]
        if expiry:
            items = [item for item in items if item["有效期档"] == expiry]
        # 默认把最该处理的排前面：已过期 > 快到期 > 其他，同档按剩余天数升序。
        items.sort(key=lambda item: (
            0 if item["过期"] else (1 if item["有效期档"] == f"{EXPIRE_SOON_DAYS}天内到期" else 2),
            item["剩余天数"] if item["剩余天数"] is not None else 99999,
        ))
        total = len(items)
        start = max(page - 1, 0) * size
        return items[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return enrich(row) if row else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        if parse_date(values.get("有效期至")) is None:
            return None, ["有效期至（需为 YYYY-MM-DD 日期）"]
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ["设施编号", "设施类型", "所属站点", "灭火剂量", "有效期至"]:
            entry[field] = str(values.get(field)).strip()
        entry["压力状态"] = NORMAL_PRESSURE
        entry["上次检查"] = None
        entry["检查人员"] = None
        entry["status"] = "合格"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return enrich(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"消防设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于消防设施可执行范围"
        target = ACTION_RULES[action]

        if action == "登记不足":
            row["压力状态"] = LOW_PRESSURE
            row["status"] = "压力不足"
            row["abnormal"] = True
        elif action == "登记过期":
            # 直接落到昨天，保证有效期档立刻变成「已过期」，不依赖调用方传日期。
            row["有效期至"] = (_today() - timedelta(days=1)).isoformat()
            row["status"] = "已过期"
            row["pending"] = False
            row["abnormal"] = True
        elif action == "安排更换":
            # 更换是终态：脱离下一轮检查清单，只在台账留档可查。
            row["status"] = "已更换"
            row["压力状态"] = NORMAL_PRESSURE
            row["pending"] = False
            row["abnormal"] = False
        return enrich(row), f"消防设施已{action}"

    # ---------- 有效期分档（按月） ----------
    def expiry_overview(self, within_days: int = EXPIRE_SOON_DAYS) -> dict[str, Any]:
        today = _today()
        items = [enrich(row, today) for row in store.rows(MODULE)]
        expired = [item for item in items if item["过期"]]
        soon = [
            item for item in items
            if not item["过期"]
            and item["剩余天数"] is not None
            and 0 <= item["剩余天数"] <= within_days
        ]
        # 压力不足分组与已过期分月互斥：既过期又缺压的只进过期组，
        # 行数据上「压力不足」标记仍为 true，两个问题在台面上分开标出。
        low_pressure = [
            item for item in items
            if item["压力不足"] and not item["已更换"] and not item["过期"]
        ]

        def group_by_month(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            buckets: dict[str, list[dict[str, Any]]] = {}
            for item in rows:
                expire = parse_date(item.get("有效期至"))
                buckets.setdefault(month_key(expire), []).append(item)
            result = []
            for month, group in sorted(buckets.items()):
                group.sort(key=lambda x: x["剩余天数"] if x["剩余天数"] is not None else 99999)
                result.append({
                    "month": month,
                    "count": len(group),
                    "facilities": group,
                })
            return result

        return {
            "today": today.isoformat(),
            "within_days": within_days,
            "summary": {
                "total": len(items),
                "expired_count": len(expired),
                "expiring_soon_count": len(soon),
                "low_pressure_count": len(low_pressure),
                "replaced_count": sum(1 for item in items if item["已更换"]),
            },
            # 过期与压力不足分开标：过期按月，压力不足单独一组，不混在一起。
            "expired_by_month": group_by_month(expired),
            "expiring_by_month": group_by_month(soon),
            "low_pressure": low_pressure,
        }

    # ---------- 检查清单 ----------
    def checklist(self, site: str | None = None) -> list[dict[str, Any]]:
        """下一轮检查清单：已过期、已更换的不再排进来。"""
        today = _today()
        items = []
        for row in store.rows(MODULE):
            item = enrich(row, today)
            if not item["纳入检查清单"]:
                continue
            if site and site != item.get("所属站点"):
                continue
            last = latest_check(int(item["id"]))
            item["上次检查日期"] = last.get("check_date") if last else item.get("上次检查")
            item["上次检查人员"] = last.get("inspector") if last else item.get("检查人员")
            items.append(item)
        # 最久没检的排前面，方便一次勾一批。
        items.sort(key=lambda x: (str(x.get("上次检查日期") or ""), str(x.get("设施编号"))))
        return items

    # ---------- 检查记录 ----------
    def list_checks(self) -> list[dict[str, Any]]:
        rows = sorted(
            store.rows(CHECKS_TABLE),
            key=lambda c: (str(c.get("check_date", "")), int(c.get("id", 0))),
            reverse=True,
        )
        facility_map = {int(r["id"]): r for r in store.rows(MODULE)}
        result = []
        for check in rows:
            facility = facility_map.get(int(check.get("facility_id", 0)))
            line = dict(check)
            line["设施编号"] = facility.get("设施编号") if facility else None
            line["所属站点"] = facility.get("所属站点") if facility else None
            result.append(line)
        return result

    def batch_check(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """批量登记检查。返回 (结果体, HTTP 状态码)。

        * 同 batch_id 重复提交：幂等返回首次结果，HTTP 200，不重复落记录；
        * 勾选里夹着已过期设施：逐台退回，要求先「安排更换」，其余照常登记；
        * 压力状态为不足的照常落记录（结果记为「压力不足」），供后续处置。
        """
        batch_id = str(payload.get("batch_id") or "").strip()
        inspector = str(payload.get("inspector") or "").strip()
        facility_ids = payload.get("facility_ids") or []
        remark = str(payload.get("remark") or "").strip()

        if not batch_id:
            return {"ok": False, "message": "缺少批次号 batch_id，无法登记"}, 400
        if not inspector:
            return {"ok": False, "message": "缺少检查人员，无法登记检查记录"}, 400
        if not isinstance(facility_ids, list) or not facility_ids:
            return {"ok": False, "message": "请至少勾选一台消防设施再提交"}, 400

        batches = store.rows(BATCHES_TABLE)
        duplicate = next((b for b in batches if b.get("batch_id") == batch_id), None)
        if duplicate is not None:
            return {
                "ok": True,
                "duplicate": True,
                "message": f"批次 {batch_id} 已提交过，本次为重复提交，检查记录只保留首次登记的一次",
                "batch": duplicate,
            }, 200

        today = _today()
        check_rows = store.rows(CHECKS_TABLE)
        next_check_id = max((int(c.get("id", 0)) for c in check_rows), default=0) + 1

        recorded: list[dict[str, Any]] = []
        rejected_expired: list[dict[str, Any]] = []
        skipped_replaced: list[dict[str, Any]] = []
        missing: list[int] = []
        low_pressure_count = 0

        for raw_id in facility_ids:
            row = store.find(MODULE, int(raw_id))
            if row is None:
                missing.append(int(raw_id))
                continue
            item = enrich(row, today)
            if item["已更换"]:
                skipped_replaced.append({"facility_id": item["id"], "设施编号": item.get("设施编号"),
                                         "reason": "设施已更换，台账留档不再检查"})
                continue
            # 已过期的单独退回：不落检查记录，先安排更换之后才能进下一轮。
            if item["过期"]:
                rejected_expired.append({
                    "facility_id": item["id"],
                    "设施编号": item.get("设施编号"),
                    "所属站点": item.get("所属站点"),
                    "有效期至": item.get("有效期至"),
                    "reason": f"灭火剂已于 {item.get('有效期至')} 过期，请先安排更换再检查",
                })
                continue

            result = "压力不足" if item["压力不足"] else "正常"
            if item["压力不足"]:
                low_pressure_count += 1
            record = {
                "id": next_check_id,
                "facility_id": item["id"],
                "batch_id": batch_id,
                "check_date": today.isoformat(),
                "inspector": inspector,
                "result": result,
                "remark": remark,
            }
            next_check_id += 1
            check_rows.append(record)
            # 台账行同步刷新「上次检查/检查人员」。
            row["上次检查"] = today.isoformat()
            row["检查人员"] = inspector
            if result == "压力不足":
                row["压力状态"] = LOW_PRESSURE
                row["status"] = "压力不足"
                row["abnormal"] = True
            elif row.get("status") != "压力不足":
                row["status"] = "合格"
                row["abnormal"] = False
                row["pending"] = True
            recorded.append({
                "facility_id": item["id"],
                "设施编号": item.get("设施编号"),
                "所属站点": item.get("所属站点"),
                "result": result,
                "check_date": today.isoformat(),
            })

        if not recorded and not rejected_expired and not skipped_replaced:
            return {"ok": False, "message": f"勾选的设施编号不存在：{', '.join(map(str, missing))}"}, 404

        batch_row = {
            "batch_id": batch_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "inspector": inspector,
            "recorded_count": len(recorded),
            "low_pressure_count": low_pressure_count,
            "rejected_expired_count": len(rejected_expired),
        }
        batches.append(batch_row)

        message = f"批次 {batch_id} 登记完成：{len(recorded)} 台已落检查记录"
        if low_pressure_count:
            message += f"，其中 {low_pressure_count} 台压力不足已单独标出"
        if rejected_expired:
            message += f"；{len(rejected_expired)} 台已过期已退回，须先安排更换"
        return {
            "ok": True,
            "duplicate": False,
            "message": message,
            "batch": batch_row,
            "recorded": recorded,
            "rejected_expired": rejected_expired,
            "skipped_replaced": skipped_replaced,
            "missing_ids": missing,
        }, 200
