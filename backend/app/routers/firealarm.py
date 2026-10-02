"""消防设施接口：台账筛选、有效期/剂量分档、批量检查与更换流转。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.firealarm import FirealarmService

router = APIRouter(prefix="/api/firealarm", tags=["消防设施"])

service = FirealarmService()

LIST_FIELDS = ["设施编号", "设施类型", "所属站点", "灭火剂量", "上次检查", "有效期至", "检查人员", "设施状态"]
STATUSES = ["合格", "压力不足", "已过期"]
DOSE_TIERS = ["手提式", "推车式"]
EXPIRY_TIERS = ["已过期", "30天内到期", "31-90天到期", "正常在用"]


@router.get("/expiry-overview")
def expiry_overview() -> dict[str, Any]:
    """到期看板：按月列出已过期与即将到期设施，压力不足单独一组。"""
    return service.expiry_overview()


@router.get("/checklist")
def checklist() -> dict[str, Any]:
    """下一轮检查清单：逐台带出上次检查日期与人员，已过期设施不排入。"""
    items = service.checklist()
    return {"total": len(items), "items": items}


@router.get("/checks")
def list_checks(facility: str | None = Query(default=None, description="按设施编号过滤检查记录")) -> dict[str, Any]:
    """检查记录流水，最新在前。"""
    items = service.list_checks(facility)
    return {"total": len(items), "items": items}


@router.post("/batch-check")
def batch_check(payload: EntryPayload) -> dict[str, Any]:
    """批量登记检查：已过期的单独退回要求先更换；同批次号重复提交只记一次。"""
    return service.batch_check(payload.values)


@router.post("/{entry_id}/replace", response_model=ActionResult)
def replace_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对已过期（或其他需更换）设施安排更换，写入新有效期后重新纳入检查清单。"""
    entry, message = service.replace(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设施编号或类型检索"),
    site: str | None = Query(default=None, description="按所属站点模糊检索"),
    dose_tier: str | None = Query(default=None, description="手提式 / 推车式"),
    expiry_tier: str | None = Query(default=None, description="已过期 / 30天内到期 / 31-90天到期 / 正常在用"),
    status: str | None = Query(default=None, description="合格、压力不足、已过期"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按站点、灭火剂量分档、有效期分档、状态过滤台账；状态以有效期当天重算为准。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        site=site,
        dose_tier=dose_tier,
        expiry_tier=expiry_tier,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出消防设施台账：返回当前全量数据及分档字段。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "firealarm", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
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
    """旧版单条动作入口（登记不足/登记过期/安排更换），保留兼容。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
