"""消防设施接口。

* 台账：分页列表（支持灭火剂量档/有效期档/状态过滤）、明细、登记、单台动作；
* GET  /expiry-overview   按月列出已过期与快到期设施，压力不足单独成组；
* GET  /checklist         下一轮检查清单（已过期、已更换的不再排进来）；
* POST /batch-checks      一次勾选一批批量登记检查（幂等、过期单独退回）；
* GET  /checks            检查记录流水。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, BatchCheckPayload, EntryPayload, PageResult
from app.services.firealarm import (
    AGENT_BUCKETS,
    EXPIRE_SOON_DAYS,
    FirealarmService,
)

router = APIRouter(prefix="/api/firealarm", tags=["消防设施"])

service = FirealarmService()

LIST_FIELDS = ["设施编号", "设施类型", "所属站点", "灭火剂量", "灭火剂量档", "上次检查", "有效期至", "有效期档", "检查人员", "实时状态"]
STATUSES = ["合格", "压力不足", "已过期", "已更换"]
AGENT_TIERS = [label for _, label in AGENT_BUCKETS]
EXPIRY_TIERS = ["已过期", f"{EXPIRE_SOON_DAYS}天内到期", "正常", "无有效期", "已更换"]


@router.get("/expiry-overview")
def expiry_overview(
    within_days: int = Query(default=EXPIRE_SOON_DAYS, ge=1, le=365),
) -> dict[str, Any]:
    """有效期分档看板：按月列出已过期和快到期设施，压力不足单独一组。"""
    return service.expiry_overview(within_days=within_days)


@router.get("/checklist")
def checklist(site: str | None = Query(default=None)) -> list[dict[str, Any]]:
    """下一轮检查清单：逐台带出上次检查日期与检查人员；过期/已更换不再排入。"""
    return service.checklist(site=site)


@router.get("/checks")
def list_checks() -> dict[str, Any]:
    """检查记录流水（最新在前）。"""
    items = service.list_checks()
    return {"total": len(items), "items": items}


@router.post("/batch-checks")
def batch_checks(payload: BatchCheckPayload) -> dict[str, Any]:
    """批量登记检查：已过期的单独退回要求先更换；同批次号重复提交只记一次。"""
    result, status_code = service.batch_check(payload.model_dump())
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result["message"])
    return result


@router.get("/filters")
def filters() -> dict[str, Any]:
    """给前端筛选栏提供分档选项。"""
    sites = sorted({row.get("所属站点") for row in service.list_entries(page=1, size=10000)[0] if row.get("所属站点")})
    return {"statuses": STATUSES, "agent_tiers": AGENT_TIERS, "expiry_tiers": EXPIRY_TIERS, "sites": sites}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出消防设施清单：返回全量台账（含分档计算字段）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "firealarm", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设施编号、设施类型或所属站点检索"),
    status: str | None = Query(default=None, description="实时状态：合格、压力不足、已过期、已更换"),
    agent: str | None = Query(default=None, description="灭火剂量档"),
    expiry: str | None = Query(default=None, description="有效期档：已过期/30天内到期/正常"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字与分档过滤消防设施列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, agent=agent, expiry=expiry, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条消防设施明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"消防设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条消防设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="消防设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条消防设施执行登记不足、登记过期、安排更换；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
