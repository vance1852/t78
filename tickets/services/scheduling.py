"""排期核心服务：冲突校验、智能排期、空档查询、统计分析。"""
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from django.db.models import Q

from tickets.models import (
    Hall,
    MaintenancePeriod,
    Performance,
    Show,
)


def _ranges_overlap(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    """判断两个时间区间是否重叠。"""
    return start1 < end2 and start2 < end1


def check_performance_conflict(
    hall_id: int,
    setup_start_at: datetime,
    teardown_end_at: datetime,
    show_id: Optional[int] = None,
    exclude_performance_id: Optional[int] = None,
) -> dict:
    """
    校验演出场次是否存在冲突。

    冲突类型：
    1. 同一厅时间重叠（含装台/拆台缓冲）
    2. 同一演出同一时间不能在两个厅
    3. 与维护期冲突

    Returns:
        dict: { "has_conflict": bool, "conflicts": [ { "type": str, "detail": str, ... } ] }
    """
    conflicts = []

    hall = Hall.objects.select_related("theater").filter(pk=hall_id).first()
    if not hall:
        return {"has_conflict": True, "conflicts": [{"type": "hall_not_found", "detail": "厅不存在"}]}

    qs = Performance.objects.filter(
        hall_id=hall_id,
        setup_start_at__lt=teardown_end_at,
        teardown_end_at__gt=setup_start_at,
    )
    if exclude_performance_id:
        qs = qs.exclude(pk=exclude_performance_id)

    for p in qs:
        conflicts.append({
            "type": "hall_time_overlap",
            "detail": f"与「{p.show.title}」装拆台时间重叠",
            "performance_id": p.id,
            "show_title": p.show.title,
            "setup_start_at": p.setup_start_at,
            "teardown_end_at": p.teardown_end_at,
        })

    if show_id:
        same_show_qs = Performance.objects.filter(
            show_id=show_id,
            setup_start_at__lt=teardown_end_at,
            teardown_end_at__gt=setup_start_at,
        ).exclude(hall_id=hall_id)
        if exclude_performance_id:
            same_show_qs = same_show_qs.exclude(pk=exclude_performance_id)

        for p in same_show_qs:
            conflicts.append({
                "type": "same_show_time_overlap",
                "detail": f"同一演出「{p.show.title}」在「{p.hall.name}」已有场次，时间重叠",
                "performance_id": p.id,
                "hall_name": p.hall.name,
                "setup_start_at": p.setup_start_at,
                "teardown_end_at": p.teardown_end_at,
            })

    maint_qs = MaintenancePeriod.objects.filter(
        hall_id=hall_id,
        start_at__lt=teardown_end_at,
        end_at__gt=setup_start_at,
    )
    for m in maint_qs:
        conflicts.append({
            "type": "maintenance_overlap",
            "detail": f"与「{m.reason or '厅维护'}」时间重叠",
            "maintenance_id": m.id,
            "start_at": m.start_at,
            "end_at": m.end_at,
        })

    return {"has_conflict": len(conflicts) > 0, "conflicts": conflicts}


def check_maintenance_conflict(
    hall_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_maintenance_id: Optional[int] = None,
) -> dict:
    """校验维护期与已有排期的冲突。"""
    conflicts = []

    perf_qs = Performance.objects.filter(
        hall_id=hall_id,
        setup_start_at__lt=end_at,
        teardown_end_at__gt=start_at,
    ).select_related("show")

    for p in perf_qs:
        has_tickets_sold = p.sold_seats > 0
        conflicts.append({
            "type": "performance_overlap",
            "detail": f"与演出「{p.show.title}」冲突（已售票：{p.sold_seats}）",
            "performance_id": p.id,
            "show_title": p.show.title,
            "sold_seats": p.sold_seats,
            "has_tickets_sold": has_tickets_sold,
            "setup_start_at": p.setup_start_at,
            "teardown_end_at": p.teardown_end_at,
        })

    qs = MaintenancePeriod.objects.filter(
        hall_id=hall_id,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_maintenance_id:
        qs = qs.exclude(pk=exclude_maintenance_id)

    for m in qs:
        conflicts.append({
            "type": "maintenance_overlap",
            "detail": f"与已有维护期重叠",
            "maintenance_id": m.id,
            "start_at": m.start_at,
            "end_at": m.end_at,
        })

    return {"has_conflict": len(conflicts) > 0, "conflicts": conflicts}


def find_impact_analysis(performance_id: int, new_hall_id: int, new_start_at: datetime) -> dict:
    """
    排期变更影响分析：改一场会不会连带影响已售票场次。

    Returns:
        dict: 影响分析结果
    """
    try:
        perf = Performance.objects.select_related("show", "hall").get(pk=performance_id)
    except Performance.DoesNotExist:
        return {"error": "场次不存在"}

    show = perf.show
    setup_start = new_start_at - timedelta(minutes=show.setup_minutes)
    teardown_end = new_start_at + timedelta(minutes=show.duration_minutes + show.teardown_minutes)
    end_at = new_start_at + timedelta(minutes=show.duration_minutes)

    conflict_result = check_performance_conflict(
        hall_id=new_hall_id,
        setup_start_at=setup_start,
        teardown_end_at=teardown_end,
        show_id=show.id,
        exclude_performance_id=performance_id,
    )

    has_ticket_sold = perf.sold_seats > 0

    suggestions = []
    if has_ticket_sold:
        suggestions.append("该场次已售票，改期前需通知已购票观众")
    if conflict_result["has_conflict"]:
        for c in conflict_result["conflicts"]:
            if c.get("has_tickets_sold"):
                suggestions.append(f"与「{c.get('show_title', '')}」冲突，且对方已售票，需谨慎处理")

    hall = Hall.objects.filter(pk=new_hall_id).first()
    hall_capacity_ok = hall is not None and hall.capacity >= show.min_capacity

    facilities_ok = True
    if hall and show.required_facilities:
        missing = [f for f in show.required_facilities if f not in hall.facilities]
        if missing:
            facilities_ok = False
            suggestions.append(f"厅缺少设备：{', '.join(missing)}")

    return {
        "original": {
            "performance_id": perf.id,
            "show_title": show.title,
            "hall_name": perf.hall.name,
            "start_at": perf.start_at,
            "end_at": perf.end_at,
            "sold_seats": perf.sold_seats,
        },
        "proposed": {
            "hall_name": hall.name if hall else "未知厅",
            "start_at": new_start_at,
            "end_at": end_at,
            "setup_start_at": setup_start,
            "teardown_end_at": teardown_end,
        },
        "has_ticket_sold": has_ticket_sold,
        "hall_capacity_ok": hall_capacity_ok,
        "facilities_ok": facilities_ok,
        "has_conflict": conflict_result["has_conflict"],
        "conflicts": conflict_result["conflicts"],
        "suggestions": suggestions,
    }


def find_available_slots(
    start_date: datetime,
    end_date: datetime,
    min_capacity: int = 0,
    duration_minutes: int = 120,
    setup_minutes: int = 60,
    teardown_minutes: int = 30,
    hall_ids: Optional[List[int]] = None,
    required_facilities: Optional[List[str]] = None,
) -> List[dict]:
    """
    查询某时间段内各厅的可用空档。

    返回每个厅在指定日期范围内的可用时段列表。
    """
    total_minutes = setup_minutes + duration_minutes + teardown_minutes
    total_delta = timedelta(minutes=total_minutes)

    halls = Hall.objects.all()
    if hall_ids:
        halls = halls.filter(pk__in=hall_ids)
    if min_capacity:
        halls = halls.filter(capacity__gte=min_capacity)
    if required_facilities:
        hall_list = []
        for h in halls:
            if all(f in h.facilities for f in required_facilities):
                hall_list.append(h)
        halls = hall_list
    else:
        halls = list(halls)

    result = []
    for hall in halls:
        occupied = []

        perfs = Performance.objects.filter(
            hall=hall,
            setup_start_at__lt=end_date,
            teardown_end_at__gt=start_date,
        ).order_by("setup_start_at")
        for p in perfs:
            occupied.append((p.setup_start_at, p.teardown_end_at, "performance", p.id, p.show.title))

        maints = MaintenancePeriod.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        ).order_by("start_at")
        for m in maints:
            occupied.append((m.start_at, m.end_at, "maintenance", m.id, m.reason or "厅维护"))

        occupied.sort(key=lambda x: x[0])

        slots = []
        current = start_date
        for occ_start, occ_end, occ_type, occ_id, occ_label in occupied:
            if current < occ_start and (occ_start - current) >= total_delta:
                slot_start = current
                slot_end = occ_start
                perf_start = slot_start + timedelta(minutes=setup_minutes)
                perf_end = perf_start + timedelta(minutes=duration_minutes)
                if perf_end <= occ_start - timedelta(minutes=teardown_minutes):
                    slots.append({
                        "slot_start": slot_start,
                        "slot_end": slot_end,
                        "performance_start": perf_start,
                        "performance_end": perf_end,
                        "duration_minutes": duration_minutes,
                    })
            current = max(current, occ_end)

        if current < end_date and (end_date - current) >= total_delta:
            perf_start = current + timedelta(minutes=setup_minutes)
            perf_end = perf_start + timedelta(minutes=duration_minutes)
            if perf_end <= end_date - timedelta(minutes=teardown_minutes):
                slots.append({
                    "slot_start": current,
                    "slot_end": end_date,
                    "performance_start": perf_start,
                    "performance_end": perf_end,
                    "duration_minutes": duration_minutes,
                })

        result.append({
            "hall_id": hall.id,
            "hall_name": hall.name,
            "theater_name": hall.theater.name,
            "capacity": hall.capacity,
            "slots": slots,
        })

    return result


def auto_schedule(
    show_ids: List[int],
    start_date: datetime,
    end_date: datetime,
    priority_mode: str = "high_first",
    hall_ids: Optional[List[int]] = None,
) -> dict:
    """
    智能排期：给定一批待排演出，自动排出无冲突且尽量紧凑的档期方案。

    算法：贪心 + 首次适应（First-Fit Decreasing）
    1. 按优先级排序演出（高优先级先排）
    2. 对每个演出，在所有厅的时间轴上找最早可放入的空档
    3. 尽量紧凑以提高利用率

    priority_mode:
        - "high_first": 重点演出优先（按演出ID倒序，即后创建的更重要）
        - "long_first": 长演出优先（提高利用率）
        - "short_first": 短演出优先（尽量都排上）
    """
    shows = Show.objects.filter(pk__in=show_ids)
    show_list = list(shows)

    if not show_list:
        return {"scheduled": [], "failed": [], "utilization": 0.0, "method": "auto"}

    halls_qs = Hall.objects.all()
    if hall_ids:
        halls_qs = halls_qs.filter(pk__in=hall_ids)
    halls = list(halls_qs)

    if not halls:
        return {"scheduled": [], "failed": [{"show_id": s.id, "title": s.title, "reason": "无可用厅"} for s in show_list], "utilization": 0.0, "method": "auto"}

    if priority_mode == "long_first":
        show_list.sort(key=lambda s: -(s.duration_minutes + s.setup_minutes + s.teardown_minutes))
    elif priority_mode == "short_first":
        show_list.sort(key=lambda s: s.duration_minutes + s.setup_minutes + s.teardown_minutes)
    else:
        show_list.sort(key=lambda s: -s.id)

    hall_timelines = {h.id: [] for h in halls}

    for hall in halls:
        perfs = Performance.objects.filter(
            hall=hall,
            setup_start_at__lt=end_date,
            teardown_end_at__gt=start_date,
        ).order_by("setup_start_at")
        for p in perfs:
            hall_timelines[hall.id].append((p.setup_start_at, p.teardown_end_at))

        maints = MaintenancePeriod.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        ).order_by("start_at")
        for m in maints:
            hall_timelines[hall.id].append((m.start_at, m.end_at))

        hall_timelines[hall.id].sort(key=lambda x: x[0])

    scheduled = []
    failed = []

    for show in show_list:
        total_minutes = show.setup_minutes + show.duration_minutes + show.teardown_minutes
        total_delta = timedelta(minutes=total_minutes)

        suitable_halls = []
        for h in halls:
            if h.capacity < show.min_capacity:
                continue
            if show.required_facilities and not all(f in h.facilities for f in show.required_facilities):
                continue
            suitable_halls.append(h)

        if not suitable_halls:
            failed.append({
                "show_id": show.id,
                "title": show.title,
                "reason": "没有满足容量/设备要求的厅",
            })
            continue

        best_slot = None
        best_hall = None

        for hall in suitable_halls:
            timeline = hall_timelines[hall.id]
            current = start_date

            for occ_start, occ_end in timeline:
                if current < occ_start and (occ_start - current) >= total_delta:
                    candidate_start = current
                    if best_slot is None or candidate_start < best_slot:
                        best_slot = candidate_start
                        best_hall = hall
                    break
                current = max(current, occ_end)

            if current < end_date and (end_date - current) >= total_delta:
                if best_slot is None or current < best_slot:
                    best_slot = current
                    best_hall = hall

        if best_slot and best_hall:
            setup_start = best_slot
            perf_start = setup_start + timedelta(minutes=show.setup_minutes)
            perf_end = perf_start + timedelta(minutes=show.duration_minutes)
            teardown_end = perf_end + timedelta(minutes=show.teardown_minutes)

            scheduled.append({
                "show_id": show.id,
                "show_title": show.title,
                "hall_id": best_hall.id,
                "hall_name": best_hall.name,
                "theater_name": best_hall.theater.name,
                "setup_start_at": setup_start,
                "start_at": perf_start,
                "end_at": perf_end,
                "teardown_end_at": teardown_end,
                "duration_minutes": show.duration_minutes,
                "setup_minutes": show.setup_minutes,
                "teardown_minutes": show.teardown_minutes,
            })

            hall_timelines[best_hall.id].append((setup_start, teardown_end))
            hall_timelines[best_hall.id].sort(key=lambda x: x[0])
        else:
            failed.append({
                "show_id": show.id,
                "title": show.title,
                "reason": "指定时段内找不到合适空档",
            })

    total_hall_minutes = len(halls) * (end_date - start_date).total_seconds() / 60
    used_minutes = 0.0
    for hall in halls:
        timeline = hall_timelines[hall.id]
        for s, e in timeline:
            eff_start = max(s, start_date)
            eff_end = min(e, end_date)
            if eff_start < eff_end:
                used_minutes += (eff_end - eff_start).total_seconds() / 60

    utilization = round(used_minutes / total_hall_minutes * 100, 2) if total_hall_minutes > 0 else 0.0

    return {
        "scheduled": scheduled,
        "failed": failed,
        "utilization": utilization,
        "method": "auto",
        "priority_mode": priority_mode,
    }


def calculate_occupation_rate(
    start_date: datetime,
    end_date: datetime,
    hall_ids: Optional[List[int]] = None,
) -> dict:
    """计算厅占用率（含装台拆台）。"""
    halls = Hall.objects.all()
    if hall_ids:
        halls = halls.filter(pk__in=hall_ids)

    total_seconds = (end_date - start_date).total_seconds()
    if total_seconds <= 0:
        return {"halls": [], "overall": 0.0}

    hall_stats = []
    total_used = 0.0
    total_available = 0.0

    for hall in halls:
        used = 0.0

        perfs = Performance.objects.filter(
            hall=hall,
            setup_start_at__lt=end_date,
            teardown_end_at__gt=start_date,
        )
        for p in perfs:
            s = max(p.setup_start_at, start_date)
            e = min(p.teardown_end_at, end_date)
            if s < e:
                used += (e - s).total_seconds()

        maints = MaintenancePeriod.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        )
        for m in maints:
            s = max(m.start_at, start_date)
            e = min(m.end_at, end_date)
            if s < e:
                used += (e - s).total_seconds()

        rate = round(used / total_seconds * 100, 2) if total_seconds > 0 else 0.0
        hall_stats.append({
            "hall_id": hall.id,
            "hall_name": hall.name,
            "theater_name": hall.theater.name,
            "capacity": hall.capacity,
            "used_seconds": used,
            "total_seconds": total_seconds,
            "occupation_rate": rate,
        })
        total_used += used
        total_available += total_seconds

    overall = round(total_used / total_available * 100, 2) if total_available > 0 else 0.0
    return {"halls": hall_stats, "overall": overall}


def calculate_hall_utilization(
    start_date: datetime,
    end_date: datetime,
    hall_id: Optional[int] = None,
) -> dict:
    """
    厅利用率统计（纯演出时间，不含装拆台维护）。

    区分演出占用、装台拆台占用、维护占用。
    """
    halls = Hall.objects.all()
    if hall_id:
        halls = halls.filter(pk=hall_id)

    total_seconds = (end_date - start_date).total_seconds()

    stats = []
    for hall in halls:
        perf_seconds = 0.0
        setup_teardown_seconds = 0.0
        maintenance_seconds = 0.0

        perfs = Performance.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        )
        for p in perfs:
            s = max(p.start_at, start_date)
            e = min(p.end_at, end_date)
            if s < e:
                perf_seconds += (e - s).total_seconds()

            setup_s = max(p.setup_start_at, start_date)
            setup_e = min(p.start_at, end_date)
            if setup_s < setup_e:
                setup_teardown_seconds += (setup_e - setup_s).total_seconds()

            teardown_s = max(p.end_at, start_date)
            teardown_e = min(p.teardown_end_at, end_date)
            if teardown_s < teardown_e:
                setup_teardown_seconds += (teardown_e - teardown_s).total_seconds()

        maints = MaintenancePeriod.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        )
        for m in maints:
            s = max(m.start_at, start_date)
            e = min(m.end_at, end_date)
            if s < e:
                maintenance_seconds += (e - s).total_seconds()

        perf_rate = round(perf_seconds / total_seconds * 100, 2) if total_seconds > 0 else 0.0
        setup_rate = round(setup_teardown_seconds / total_seconds * 100, 2) if total_seconds > 0 else 0.0
        maint_rate = round(maintenance_seconds / total_seconds * 100, 2) if total_seconds > 0 else 0.0
        total_rate = round((perf_seconds + setup_teardown_seconds + maintenance_seconds) / total_seconds * 100, 2) if total_seconds > 0 else 0.0

        perf_count = perfs.count()
        ticket_sold = sum(p.sold_seats for p in perfs)
        ticket_total = sum(p.total_seats for p in perfs)

        stats.append({
            "hall_id": hall.id,
            "hall_name": hall.name,
            "theater_name": hall.theater.name,
            "capacity": hall.capacity,
            "performance_count": perf_count,
            "perf_seconds": perf_seconds,
            "setup_teardown_seconds": setup_teardown_seconds,
            "maintenance_seconds": maintenance_seconds,
            "perf_rate": perf_rate,
            "setup_teardown_rate": setup_rate,
            "maintenance_rate": maint_rate,
            "total_occupation_rate": total_rate,
            "tickets_sold": ticket_sold,
            "tickets_total": ticket_total,
            "ticket_sell_rate": round(ticket_sold / ticket_total * 100, 2) if ticket_total > 0 else 0.0,
        })

    return {
        "period_start": start_date,
        "period_end": end_date,
        "halls": stats,
    }


def generate_conflict_report(
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """生成排期冲突报告：扫描所有场次，检测各类冲突。"""
    conflicts = []

    perfs = Performance.objects.filter(
        start_at__lt=end_date,
        end_at__gt=start_date,
    ).select_related("show", "hall", "hall__theater").order_by("start_at")

    perf_list = list(perfs)

    for i, p1 in enumerate(perf_list):
        for j, p2 in enumerate(perf_list):
            if j <= i:
                continue

            if p1.hall_id == p2.hall_id:
                if _ranges_overlap(p1.setup_start_at, p1.teardown_end_at, p2.setup_start_at, p2.teardown_end_at):
                    conflicts.append({
                        "type": "hall_time_overlap",
                        "severity": "high",
                        "detail": f"「{p1.hall.name}」中「{p1.show.title}」与「{p2.show.title}」时间重叠",
                        "hall_name": p1.hall.name,
                        "performance_1": {
                            "id": p1.id,
                            "show_title": p1.show.title,
                            "setup_start": p1.setup_start_at,
                            "teardown_end": p1.teardown_end_at,
                        },
                        "performance_2": {
                            "id": p2.id,
                            "show_title": p2.show.title,
                            "setup_start": p2.setup_start_at,
                            "teardown_end": p2.teardown_end_at,
                        },
                    })

            if p1.show_id == p2.show_id and p1.hall_id != p2.hall_id:
                if _ranges_overlap(p1.setup_start_at, p1.teardown_end_at, p2.setup_start_at, p2.teardown_end_at):
                    conflicts.append({
                        "type": "same_show_overlap",
                        "severity": "high",
                        "detail": f"同一演出「{p1.show.title}」同时在「{p1.hall.name}」和「{p2.hall.name}」",
                        "show_title": p1.show.title,
                        "performance_1": {
                            "id": p1.id,
                            "hall_name": p1.hall.name,
                            "setup_start": p1.setup_start_at,
                            "teardown_end": p1.teardown_end_at,
                        },
                        "performance_2": {
                            "id": p2.id,
                            "hall_name": p2.hall.name,
                            "setup_start": p2.setup_start_at,
                            "teardown_end": p2.teardown_end_at,
                        },
                    })

    maint_qs = MaintenancePeriod.objects.filter(
        start_at__lt=end_date,
        end_at__gt=start_date,
    ).select_related("hall")

    for m in maint_qs:
        for p in perf_list:
            if p.hall_id == m.hall_id and _ranges_overlap(m.start_at, m.end_at, p.setup_start_at, p.teardown_end_at):
                conflicts.append({
                    "type": "maintenance_perf_overlap",
                    "severity": "high" if p.sold_seats > 0 else "medium",
                    "detail": f"「{m.hall.name}」维护期与「{p.show.title}」冲突（已售{p.sold_seats}张票）",
                    "hall_name": m.hall.name,
                    "maintenance": {
                        "id": m.id,
                        "start_at": m.start_at,
                        "end_at": m.end_at,
                        "reason": m.reason,
                    },
                    "performance": {
                        "id": p.id,
                        "show_title": p.show.title,
                        "sold_seats": p.sold_seats,
                        "setup_start": p.setup_start_at,
                        "teardown_end": p.teardown_end_at,
                    },
                })

    return {
        "period_start": start_date,
        "period_end": end_date,
        "total_conflicts": len(conflicts),
        "conflicts": conflicts,
    }
