"""消防设施业务规则：灭火剂量分档、有效期分档、批量检查与更换流转。

口径约定（日期一律取服务端当天，避免浏览器改时区绕过提醒）：
- 灭火剂量分档：标称剂量不超过 8kg 为「手提式」，其余为「推车式」。
- 有效期分档：有效期早于今天为「已过期」；90 天内到期为「即将到期」，
  再细分为 30 天内（本月关注）与 31-90 天；更远的为「正常在用」。
- 设施状态：已过期与压力不足分开标记，优先级「已过期 > 压力不足 > 合格」；
  「已更换」不是终态——更换后写入新有效期，设施重新按新有效期参与分档与检查。
- 已过期的设施不进入下一轮检查清单，必须先安排更换。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "firealarm"
CHECKS_MODULE = "firealarm_checks"
BATCHES_MODULE = "firealarm_batches"

REQUIRED_FIELDS = ["设施编号", "设施类型", "所属站点"]
STATUS_ORDER = ["合格", "压力不足", "已过期"]
ACTION_RULES = {"登记不足": "压力不足", "登记过期": "已过期", "安排更换": "已更换"}

SOON_DAYS = 30          # 30 天内到期：本月重点盯
WINDOW_DAYS = 90        # 90 天内到期：纳入到期分档看板
CART_MIN_KG = 8.0       # 超过 8kg 归为推车式


def _today() -> date:
    return date.today()


def parse_day(value: Any) -> date | None:
    """把 'YYYY-MM-DD' 文本解析成日期；空值或异常格式返回 None，不阻断列表渲染。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def dose_weight_kg(row: dict[str, Any]) -> float | None:
    """从 '4kg'、'35 kg' 这类文本里解析出千克数；解析不出来时返回 None。"""
    text = str(row.get("灭火剂量") or "").strip().lower()
    digits = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def derive(row: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """补出分档与提醒字段，并把状态、待处理标记同步到最新口径。

    有效期每天都在向过期逼近，状态不能只靠登记时的静态值，因此读数据时统一重算。
    """
    today = today or _today()
    weight = dose_weight_kg(row)
    dose_tier = "未标注" if weight is None else ("推车式" if weight > CART_MIN_KG else "手提式")

    expiry = parse_day(row.get("有效期至"))
    expired = expiry is not None and expiry < today
    days_left: int | None = None
    if expiry is not None and not expired:
        days_left = (expiry - today).days

    low_pressure = str(row.get("压力状态") or "正常").strip() == "不足"
    if expired:
        status = "已过期"
    elif low_pressure:
        status = "压力不足"
    else:
        status = "合格"

    if days_left is None or expired:
        expiry_tier = "已过期" if expired else "未标注"
    elif days_left <= SOON_DAYS:
        expiry_tier = "30天内到期"
    elif days_left <= WINDOW_DAYS:
        expiry_tier = "31-90天到期"
    else:
        expiry_tier = "正常在用"

    expiry_month = expiry.strftime("%Y-%m") if expiry is not None else ""

    derived = dict(row)
    derived.update(
        {
            "灭火剂量分档": dose_tier,
            "有效期分档": expiry_tier,
            "到期月份": expiry_month,
            "剩余天数": days_left if days_left is not None else (-1 if expired else None),
            "过期标记": expired,
            "压力异常": low_pressure,
            "压力不足标记": low_pressure and not expired,
            "status": status,
            "pending": status != "合格",
            "abnormal": status != "合格",
        }
    )
    # 回写状态，让单条动作、导出等老接口看到的口径也一致。
    row["status"] = status
    row["pending"] = derived["pending"]
    row["abnormal"] = derived["abnormal"]
    return derived


class FirealarmService:
    # ------------------------------------------------------------------ 台账
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        site: str | None = None,
        dose_tier: str | None = None,
        expiry_tier: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        today = _today()
        rows = [derive(row, today=today) for row in store.rows(MODULE)]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("设施编号", ""))
                or keyword in str(row.get("设施类型", ""))
            ]
        if site:
            rows = [row for row in rows if site in str(row.get("所属站点", ""))]
        if dose_tier:
            rows = [row for row in rows if row.get("灭火剂量分档") == dose_tier]
        if expiry_tier:
            rows = [row for row in rows if row.get("有效期分档") == expiry_tier]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return derive(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ["设施编号", "设施类型", "所属站点", "灭火剂量", "有效期至", "上次检查", "检查人员"]:
            entry[field] = str(values.get(field) or "").strip()
        entry["压力状态"] = str(values.get("压力状态") or "正常").strip() or "正常"
        entry["更换日期"] = ""
        rows.append(entry)
        return derive(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """兼容旧的单条动作入口；「安排更换」按默认一年新有效期走更换流程。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"消防设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于消防设施可执行范围"
        if action == "安排更换":
            entry, message = self.replace(entry_id, {"检查人员": str(entry.get("检查人员") or "")})
            return entry, message
        if action == "登记不足":
            entry["压力状态"] = "不足"
        elif action == "登记过期":
            # 仅做标记用，真实过期以有效期重算为准；把有效期回拨一天确保落档。
            entry["有效期至"] = (_today() - timedelta(days=1)).isoformat()
        return derive(entry), f"消防设施已{action}"

    # ------------------------------------------------------------- 到期分档
    def expiry_overview(self) -> dict[str, Any]:
        """按月聚合：已过期的与即将到期的分开列出，30/90 天边界给出数量。"""
        today = _today()
        rows = [derive(row, today=today) for row in store.rows(MODULE)]

        expired = [row for row in rows if row["过期标记"]]
        expiring_soon = [
            row for row in rows if row["剩余天数"] is not None and 0 <= row["剩余天数"] <= WINDOW_DAYS
        ]

        def month_bucket(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            buckets: dict[str, list[dict[str, Any]]] = {}
            for row in items:
                buckets.setdefault(row["到期月份"], []).append(row)
            return [
                {"month": month, "count": len(buckets[month]), "items": buckets[month]}
                for month in sorted(buckets)
            ]

        low_pressure = [row for row in rows if row["压力不足标记"]]
        return {
            "today": today.isoformat(),
            "cards": [
                {"label": "已过期", "value": len(expired)},
                {"label": f"{SOON_DAYS}天内到期", "value": sum(1 for r in expiring_soon if r["剩余天数"] <= SOON_DAYS)},
                {"label": f"{SOON_DAYS + 1}-{WINDOW_DAYS}天到期", "value": sum(1 for r in expiring_soon if r["剩余天数"] > SOON_DAYS)},
                {"label": "压力不足", "value": len(low_pressure)},
            ],
            "expired_months": month_bucket(expired),
            "expiring_months": month_bucket(expiring_soon),
            "low_pressure": low_pressure,
        }

    # --------------------------------------------------------------- 检查
    def latest_check(self, facility_code: str) -> dict[str, Any] | None:
        """取某台设施最近一次检查记录（检查日期倒序）。"""
        records = [
            row
            for row in store.rows(CHECKS_MODULE)
            if str(row.get("设施编号")) == facility_code
        ]
        records.sort(key=lambda row: str(row.get("检查日期") or ""), reverse=True)
        return records[0] if records else None

    def checklist(self) -> list[dict[str, Any]]:
        """下一轮检查清单：逐台带出上次检查日期与人员；已过期的不排入，须先更换。"""
        today = _today()
        items: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            derived = derive(row, today=today)
            if derived["过期标记"]:
                continue
            latest = self.latest_check(str(derived.get("设施编号")))
            derived["上次检查日期"] = (latest or {}).get("检查日期", derived.get("上次检查") or "")
            derived["上次检查人员"] = (latest or {}).get("检查人员", derived.get("检查人员") or "")
            items.append(derived)
        items.sort(key=lambda row: (row.get("到期月份") or "9999", str(row.get("设施编号"))))
        return items

    def list_checks(self, facility_code: str | None = None) -> list[dict[str, Any]]:
        rows = list(store.rows(CHECKS_MODULE))
        if facility_code:
            rows = [row for row in rows if str(row.get("设施编号")) == facility_code]
        rows.sort(key=lambda row: (str(row.get("检查日期") or ""), int(row.get("id", 0))), reverse=True)
        return rows

    def batch_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        """批量登记检查。

        - batch_no 幂等：同一批次号重复提交，直接回放首次结果，只记一次。
        - 已过期的单独退回（rejected），提示先安排更换，不写检查记录。
        - 其余逐台落检查记录，并回写台账的上次检查日期/人员与压力状态。
        """
        batch_no = str(payload.get("batch_no") or "").strip()
        inspector = str(payload.get("检查人员") or "").strip()
        check_day = str(payload.get("检查日期") or "").strip() or _today().isoformat()
        ids = payload.get("ids") or []
        note = str(payload.get("备注") or "").strip()

        if not batch_no:
            return {"ok": False, "message": "缺少批次号 batch_no，无法保证重复提交只记一次", "duplicated": False}
        if not inspector:
            return {"ok": False, "message": "请填写本次检查人员", "duplicated": False}
        if parse_day(check_day) is None:
            return {"ok": False, "message": f"检查日期 {check_day} 不是有效的 YYYY-MM-DD", "duplicated": False}

        batches = store.rows(BATCHES_MODULE)
        for done in batches:
            if str(done.get("batch_no")) == batch_no:
                first = dict(done.get("result") or {})
                first["duplicated"] = True
                first["message"] = f"批次 {batch_no} 已提交过，本次为重复提交，未重复登记"
                return first

        if not isinstance(ids, list) or not ids:
            return {"ok": False, "message": "请至少勾选一台消防设施", "duplicated": False}

        today = _today()
        recorded: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        missing: list[str] = []
        check_rows = store.rows(CHECKS_MODULE)
        next_check_id = max((int(row.get("id", 0)) for row in check_rows), default=0) + 1

        for raw_id in ids:
            entry = self._find_by_code_or_id(raw_id)
            if entry is None:
                missing.append(str(raw_id))
                continue
            derived = derive(entry, today=today)
            if derived["过期标记"]:
                rejected.append(
                    {
                        "设施编号": derived.get("设施编号"),
                        "所属站点": derived.get("所属站点"),
                        "有效期至": derived.get("有效期至"),
                        "原因": "灭火剂已过有效期，已退回，请先安排更换后再纳入检查",
                    }
                )
                continue
            low_pressure = bool(derived["压力不足标记"])
            result = "压力不足" if low_pressure else "合格"
            record = {
                "id": next_check_id,
                "设施编号": derived.get("设施编号"),
                "检查日期": check_day,
                "检查人员": inspector,
                "检查结果": result,
                "备注": note,
            }
            next_check_id += 1
            check_rows.append(record)
            entry["上次检查"] = check_day
            entry["检查人员"] = inspector
            recorded.append(
                {
                    "设施编号": derived.get("设施编号"),
                    "所属站点": derived.get("所属站点"),
                    "检查结果": result,
                    "检查日期": check_day,
                    "检查人员": inspector,
                }
            )

        ok = not missing
        if missing:
            message = f"以下设施未找到，未登记：{'、'.join(missing)}"
        elif rejected and recorded:
            message = f"已登记 {len(recorded)} 台；{len(rejected)} 台已过期被退回，需先安排更换"
        elif rejected:
            ok = False
            message = f"{len(rejected)} 台设施均已过期，整批退回，请先安排更换"
        else:
            message = f"本批 {len(recorded)} 台设施检查记录已登记"

        result = {
            "ok": ok,
            "duplicated": False,
            "message": message,
            "batch_no": batch_no,
            "检查日期": check_day,
            "检查人员": inspector,
            "recorded": recorded,
            "rejected": rejected,
            "missing": missing,
        }
        batches.append(
            {
                "id": max((int(row.get("id", 0)) for row in batches), default=0) + 1,
                "batch_no": batch_no,
                "检查日期": check_day,
                "检查人员": inspector,
                "result": {k: v for k, v in result.items() if k != "duplicated"},
            }
        )
        return result

    # --------------------------------------------------------------- 更换
    def replace(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """安排更换：写入新有效期与更换日期，压力恢复正常，设施重新进入检查清单。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"消防设施 {entry_id} 不存在或已归档"
        today = _today()
        new_expiry = str(values.get("新有效期") or "").strip()
        if not new_expiry:
            new_expiry = (today.replace(year=today.year + 1)).isoformat()
        expiry_day = parse_day(new_expiry)
        if expiry_day is None:
            return None, f"新有效期 {new_expiry} 不是有效的 YYYY-MM-DD"
        if expiry_day <= today:
            return None, "新有效期必须晚于今天，否则更换后仍是过期状态"
        inspector = str(values.get("检查人员") or "").strip()
        entry["有效期至"] = new_expiry
        entry["压力状态"] = "正常"
        entry["更换日期"] = today.isoformat()
        if inspector:
            entry["检查人员"] = inspector
        return derive(entry, today=today), f"消防设施 {entry.get('设施编号')} 已安排更换，新有效期至 {new_expiry}"

    def _find_by_code_or_id(self, raw: Any) -> dict[str, Any] | None:
        text = str(raw).strip()
        if text.isdigit():
            by_id = store.find(MODULE, int(text))
            if by_id is not None:
                return by_id
        for row in store.rows(MODULE):
            if str(row.get("设施编号")) == text:
                return row
        return None
