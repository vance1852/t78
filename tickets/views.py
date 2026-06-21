from datetime import timedelta

from django.contrib.auth import authenticate
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from tickets.models import (
    Hall,
    MaintenancePeriod,
    Performance,
    Show,
    Theater,
    TicketOrder,
)
from tickets.serializers import (
    AutoScheduleSerializer,
    ConflictCheckSerializer,
    ConflictReportSerializer,
    HallCalendarSerializer,
    HallSerializer,
    ImpactAnalysisSerializer,
    LoginSerializer,
    MaintenanceSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PerformanceCreateSerializer,
    PerformanceSerializer,
    ShowSerializer,
    TheaterSerializer,
    UtilizationReportSerializer,
    AvailableSlotSerializer,
)
from tickets.services import (
    auto_schedule,
    calculate_hall_utilization,
    check_maintenance_conflict,
    check_performance_conflict,
    find_available_slots,
    find_impact_analysis,
    generate_conflict_report,
)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(username=s.validated_data["username"], password=s.validated_data["password"])
        if user is None:
            return Response({"detail": "用户名或密码错误"}, status=status.HTTP_401_UNAUTHORIZED)
        token = RefreshToken.for_user(user)
        return Response({"access_token": str(token.access_token), "token_type": "bearer"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    return Response({"id": u.id, "username": u.username, "display_name": u.get_full_name() or "平台管理员"})


class TheaterViewSet(viewsets.ModelViewSet):
    queryset = Theater.objects.all().order_by("id")
    serializer_class = TheaterSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["get"], url_path="halls")
    def halls(self, request, pk=None):
        theater = self.get_object()
        halls = theater.halls.all().order_by("id")
        serializer = HallSerializer(halls, many=True)
        return Response(serializer.data)


class HallViewSet(viewsets.ModelViewSet):
    queryset = Hall.objects.select_related("theater").all().order_by("id")
    serializer_class = HallSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        theater_id = self.request.query_params.get("theater")
        if theater_id:
            qs = qs.filter(theater_id=theater_id)
        return qs

    @action(detail=True, methods=["get"], url_path="calendar")
    def calendar(self, request, pk=None):
        hall = self.get_object()
        serializer = HallCalendarSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        start_date = data["start_date"]
        end_date = data["end_date"]

        perfs = Performance.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        ).select_related("show").order_by("start_at")

        maints = MaintenancePeriod.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        ).order_by("start_at")

        events = []
        for p in perfs:
            events.append({
                "id": p.id,
                "type": "performance",
                "title": p.show.title,
                "show_title": p.show.title,
                "show_id": p.show.id,
                "start_at": p.start_at,
                "end_at": p.end_at,
                "setup_start_at": p.setup_start_at,
                "teardown_end_at": p.teardown_end_at,
                "sold_seats": p.sold_seats,
                "total_seats": p.total_seats,
                "price": str(p.price),
            })

        for m in maints:
            events.append({
                "id": m.id,
                "type": "maintenance",
                "title": m.reason or "厅维护",
                "reason": m.reason,
                "start_at": m.start_at,
                "end_at": m.end_at,
            })

        events.sort(key=lambda x: x["start_at"])

        return Response({
            "hall_id": hall.id,
            "hall_name": hall.name,
            "theater_name": hall.theater.name,
            "capacity": hall.capacity,
            "start_date": start_date,
            "end_date": end_date,
            "events": events,
        })


class ShowViewSet(viewsets.ModelViewSet):
    queryset = Show.objects.all().order_by("id")
    serializer_class = ShowSerializer
    permission_classes = [IsAuthenticated]


class PerformanceViewSet(viewsets.ModelViewSet):
    queryset = Performance.objects.select_related("show", "hall", "hall__theater").all().order_by("start_at")
    serializer_class = PerformanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        show_id = self.request.query_params.get("show")
        hall_id = self.request.query_params.get("hall")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if show_id:
            qs = qs.filter(show_id=show_id)
        if hall_id:
            qs = qs.filter(hall_id=hall_id)
        if start_date:
            qs = qs.filter(start_at__gte=start_date)
        if end_date:
            qs = qs.filter(end_at__lte=end_date)

        return qs

    def create(self, request, *args, **kwargs):
        s = PerformanceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            show = Show.objects.get(pk=data["show"])
        except Show.DoesNotExist:
            return Response({"detail": "演出不存在"}, status=status.HTTP_404_NOT_FOUND)

        try:
            hall = Hall.objects.get(pk=data["hall"])
        except Hall.DoesNotExist:
            return Response({"detail": "厅不存在"}, status=status.HTTP_404_NOT_FOUND)

        if hall.capacity < show.min_capacity:
            return Response(
                {"detail": f"厅容量不足，需要至少 {show.min_capacity} 座，实际 {hall.capacity} 座"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if show.required_facilities:
            missing = [f for f in show.required_facilities if f not in hall.facilities]
            if missing:
                return Response(
                    {"detail": f"厅缺少所需设备：{', '.join(missing)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        setup_start = data["start_at"] - timedelta(minutes=show.setup_minutes)
        end_at = data["start_at"] + timedelta(minutes=show.duration_minutes)
        teardown_end = end_at + timedelta(minutes=show.teardown_minutes)

        conflict_result = check_performance_conflict(
            hall_id=data["hall"],
            setup_start_at=setup_start,
            teardown_end_at=teardown_end,
            show_id=show.id,
        )
        if conflict_result["has_conflict"]:
            return Response(
                {"detail": "排期冲突", "conflicts": conflict_result["conflicts"]},
                status=status.HTTP_409_CONFLICT,
            )

        perf = Performance.objects.create(
            show=show,
            hall=hall,
            start_at=data["start_at"],
            end_at=end_at,
            setup_start_at=setup_start,
            teardown_end_at=teardown_end,
            total_seats=data["total_seats"],
            price=data["price"],
        )

        return Response(
            PerformanceSerializer(perf).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        original_hall = instance.hall_id
        original_start = instance.start_at

        data = request.data.copy()
        s = PerformanceCreateSerializer(data=data)
        if not s.is_valid():
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

        valid_data = s.validated_data

        show = instance.show
        try:
            hall = Hall.objects.get(pk=valid_data["hall"])
        except Hall.DoesNotExist:
            return Response({"detail": "厅不存在"}, status=status.HTTP_404_NOT_FOUND)

        if hall.capacity < show.min_capacity:
            return Response(
                {"detail": f"厅容量不足，需要至少 {show.min_capacity} 座"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if show.required_facilities:
            missing = [f for f in show.required_facilities if f not in hall.facilities]
            if missing:
                return Response(
                    {"detail": f"厅缺少所需设备：{', '.join(missing)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        setup_start = valid_data["start_at"] - timedelta(minutes=show.setup_minutes)
        end_at = valid_data["start_at"] + timedelta(minutes=show.duration_minutes)
        teardown_end = end_at + timedelta(minutes=show.teardown_minutes)

        hall_changed = valid_data["hall"] != original_hall
        time_changed = valid_data["start_at"] != original_start

        if hall_changed or time_changed:
            conflict_result = check_performance_conflict(
                hall_id=valid_data["hall"],
                setup_start_at=setup_start,
                teardown_end_at=teardown_end,
                show_id=show.id,
                exclude_performance_id=instance.id,
            )
            if conflict_result["has_conflict"]:
                return Response(
                    {"detail": "排期冲突", "conflicts": conflict_result["conflicts"]},
                    status=status.HTTP_409_CONFLICT,
                )

        instance.hall = hall
        instance.start_at = valid_data["start_at"]
        instance.end_at = end_at
        instance.setup_start_at = setup_start
        instance.teardown_end_at = teardown_end
        instance.total_seats = valid_data["total_seats"]
        instance.price = valid_data["price"]
        instance.save()

        return Response(PerformanceSerializer(instance).data)

    @action(detail=False, methods=["post"], url_path="check-conflict")
    def check_conflict(self, request):
        s = ConflictCheckSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        show_id = data.get("show")
        show = None
        if show_id:
            try:
                show = Show.objects.get(pk=show_id)
            except Show.DoesNotExist:
                return Response({"detail": "演出不存在"}, status=status.HTTP_404_NOT_FOUND)

        setup_minutes = show.setup_minutes if show else 60
        duration_minutes = show.duration_minutes if show else 120
        teardown_minutes = show.teardown_minutes if show else 30

        setup_start = data["start_at"] - timedelta(minutes=setup_minutes)
        teardown_end = data["start_at"] + timedelta(minutes=duration_minutes + teardown_minutes)

        result = check_performance_conflict(
            hall_id=data["hall"],
            setup_start_at=setup_start,
            teardown_end_at=teardown_end,
            show_id=show_id,
            exclude_performance_id=data.get("exclude_performance"),
        )

        hall = Hall.objects.filter(pk=data["hall"]).first()
        capacity_ok = True
        facilities_ok = True
        missing_facilities = []
        if show and hall:
            capacity_ok = hall.capacity >= show.min_capacity
            if show.required_facilities:
                missing_facilities = [f for f in show.required_facilities if f not in hall.facilities]
                facilities_ok = len(missing_facilities) == 0

        result.update({
            "capacity_ok": capacity_ok,
            "facilities_ok": facilities_ok,
            "missing_facilities": missing_facilities,
        })

        return Response(result)

    @action(detail=False, methods=["post"], url_path="drag-check")
    def drag_check(self, request):
        s = ImpactAnalysisSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        result = find_impact_analysis(
            performance_id=data["performance"],
            new_hall_id=data["new_hall"],
            new_start_at=data["new_start_at"],
        )

        if "error" in result:
            return Response({"detail": result["error"]}, status=status.HTTP_404_NOT_FOUND)

        return Response(result)

    @action(detail=False, methods=["post"], url_path="impact-analysis")
    def impact_analysis(self, request):
        s = ImpactAnalysisSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        result = find_impact_analysis(
            performance_id=data["performance"],
            new_hall_id=data["new_hall"],
            new_start_at=data["new_start_at"],
        )

        if "error" in result:
            return Response({"detail": result["error"]}, status=status.HTTP_404_NOT_FOUND)

        return Response(result)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = TicketOrder.objects.select_related("performance", "performance__show").all().order_by("-id")
    serializer_class = OrderSerializer
    http_method_names = ["get", "post"]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        s = OrderCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        try:
            perf = Performance.objects.select_related("show").get(pk=data["performance"])
        except Performance.DoesNotExist:
            return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

        remaining = perf.total_seats - perf.sold_seats
        if data["quantity"] > remaining:
            return Response({"detail": "余票不足"}, status=status.HTTP_409_CONFLICT)

        order = TicketOrder.objects.create(
            performance=perf,
            customer_name=data["customer_name"],
            phone=data.get("phone", ""),
            quantity=data["quantity"],
            amount=perf.price * data["quantity"],
            status="paid",
        )
        perf.sold_seats += data["quantity"]
        perf.save(update_fields=["sold_seats"])
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class MaintenanceViewSet(viewsets.ModelViewSet):
    queryset = MaintenancePeriod.objects.select_related("hall", "hall__theater").all().order_by("start_at")
    serializer_class = MaintenanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        hall_id = self.request.query_params.get("hall")
        if hall_id:
            qs = qs.filter(hall_id=hall_id)
        return qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        if data["start_at"] >= data["end_at"]:
            return Response({"detail": "结束时间必须晚于开始时间"}, status=status.HTTP_400_BAD_REQUEST)

        conflict = check_maintenance_conflict(
            hall_id=data["hall"].id if hasattr(data["hall"], "id") else data["hall"],
            start_at=data["start_at"],
            end_at=data["end_at"],
        )
        if conflict["has_conflict"]:
            affected_sold = [c for c in conflict["conflicts"] if c.get("has_tickets_sold")]
            if affected_sold:
                return Response(
                    {"detail": "维护期与已售票场次冲突", "conflicts": conflict["conflicts"]},
                    status=status.HTTP_409_CONFLICT,
                )

        self.perform_create(s)
        headers = self.get_success_headers(s.data)
        return Response(s.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        s = self.get_serializer(instance, data=request.data, partial=partial)
        s.is_valid(raise_exception=True)

        data = s.validated_data
        hall_id = data.get("hall", instance.hall)
        if hasattr(hall_id, "id"):
            hall_id = hall_id.id

        start_at = data.get("start_at", instance.start_at)
        end_at = data.get("end_at", instance.end_at)

        if start_at >= end_at:
            return Response({"detail": "结束时间必须晚于开始时间"}, status=status.HTTP_400_BAD_REQUEST)

        conflict = check_maintenance_conflict(
            hall_id=hall_id,
            start_at=start_at,
            end_at=end_at,
            exclude_maintenance_id=instance.id,
        )
        if conflict["has_conflict"]:
            affected_sold = [c for c in conflict["conflicts"] if c.get("has_tickets_sold")]
            if affected_sold:
                return Response(
                    {"detail": "维护期与已售票场次冲突", "conflicts": conflict["conflicts"]},
                    status=status.HTTP_409_CONFLICT,
                )

        self.perform_update(s)
        return Response(s.data)

    @action(detail=False, methods=["post"], url_path="check-conflict")
    def check_conflict(self, request):
        s = MaintenanceSerializer(data=request.data)
        if not s.is_valid():
            return Response({"detail": "参数错误"}, status=status.HTTP_400_BAD_REQUEST)
        data = s.validated_data

        result = check_maintenance_conflict(
            hall_id=data["hall"].id if hasattr(data["hall"], "id") else data["hall"],
            start_at=data["start_at"],
            end_at=data["end_at"],
        )
        return Response(result)

    @action(detail=False, methods=["post"], url_path="reschedule-suggestions")
    def reschedule_suggestions(self, request):
        hall_id = request.data.get("hall")
        start_at = request.data.get("start_at")
        end_at = request.data.get("end_at")

        if not hall_id or not start_at or not end_at:
            return Response({"detail": "缺少必要参数"}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import datetime as dt
        from dateutil import parser
        try:
            if isinstance(start_at, str):
                start_at = parser.isoparse(start_at)
            if isinstance(end_at, str):
                end_at = parser.isoparse(end_at)
        except Exception:
            return Response({"detail": "时间格式错误"}, status=status.HTTP_400_BAD_REQUEST)

        conflict = check_maintenance_conflict(hall_id, start_at, end_at)
        if not conflict["has_conflict"]:
            return Response({"can_schedule": True, "suggestions": [], "conflicts": []})

        affected_perfs = [c for c in conflict["conflicts"] if c.get("type") == "performance_overlap"]

        suggestions = []
        for perf_conflict in affected_perfs:
            perf_id = perf_conflict.get("performance_id")
            try:
                perf = Performance.objects.select_related("show").get(pk=perf_id)
            except Performance.DoesNotExist:
                continue

            total_minutes = perf.show.setup_minutes + perf.show.duration_minutes + perf.show.teardown_minutes

            before_slot = {
                "direction": "before",
                "new_start": perf.teardown_end_at,
                "new_end": perf.teardown_end_at + timedelta(minutes=total_minutes),
                "detail": f"将「{perf.show.title}」移到维护期之后",
            }
            suggestions.append(before_slot)

        return Response({
            "can_schedule": False,
            "conflicts": conflict["conflicts"],
            "suggestions": suggestions,
        })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def available_slots(request):
    s = AvailableSlotSerializer(data=request.query_params)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    slots = find_available_slots(
        start_date=data["start_date"],
        end_date=data["end_date"],
        min_capacity=data.get("min_capacity", 0),
        duration_minutes=data.get("duration_minutes", 120),
        setup_minutes=data.get("setup_minutes", 60),
        teardown_minutes=data.get("teardown_minutes", 30),
        hall_ids=data.get("hall_ids"),
        required_facilities=data.get("required_facilities"),
    )

    return Response(slots)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def auto_schedule_view(request):
    s = AutoScheduleSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    result = auto_schedule(
        show_ids=data["show_ids"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        priority_mode=data.get("priority_mode", "high_first"),
        hall_ids=data.get("hall_ids"),
    )

    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def utilization_report(request):
    s = UtilizationReportSerializer(data=request.query_params)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    result = calculate_hall_utilization(
        start_date=data["start_date"],
        end_date=data["end_date"],
        hall_id=data.get("hall_id"),
    )

    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def conflict_report(request):
    s = ConflictReportSerializer(data=request.query_params)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    result = generate_conflict_report(
        start_date=data["start_date"],
        end_date=data["end_date"],
    )

    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hall_calendar_view(request):
    s = HallCalendarSerializer(data=request.query_params)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    start_date = data["start_date"]
    end_date = data["end_date"]
    hall_id = data.get("hall_id")

    halls = Hall.objects.select_related("theater").all()
    if hall_id:
        halls = halls.filter(pk=hall_id)

    result = []
    for hall in halls:
        perfs = Performance.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        ).select_related("show").order_by("start_at")

        maints = MaintenancePeriod.objects.filter(
            hall=hall,
            start_at__lt=end_date,
            end_at__gt=start_date,
        ).order_by("start_at")

        events = []
        for p in perfs:
            events.append({
                "id": p.id,
                "type": "performance",
                "title": p.show.title,
                "show_title": p.show.title,
                "show_id": p.show.id,
                "start_at": p.start_at,
                "end_at": p.end_at,
                "setup_start_at": p.setup_start_at,
                "teardown_end_at": p.teardown_end_at,
                "sold_seats": p.sold_seats,
                "total_seats": p.total_seats,
                "price": str(p.price),
            })

        for m in maints:
            events.append({
                "id": m.id,
                "type": "maintenance",
                "title": m.reason or "厅维护",
                "reason": m.reason,
                "start_at": m.start_at,
                "end_at": m.end_at,
            })

        events.sort(key=lambda x: x["start_at"])

        result.append({
            "hall_id": hall.id,
            "hall_name": hall.name,
            "theater_name": hall.theater.name,
            "capacity": hall.capacity,
            "events": events,
        })

    return Response({
        "start_date": start_date,
        "end_date": end_date,
        "halls": result,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    show_total = Show.objects.count()
    show_on_sale = Show.objects.filter(status="on_sale").count()
    perf_total = Performance.objects.count()
    order_paid = TicketOrder.objects.filter(status="paid").count()
    sold = sum(p.sold_seats for p in Performance.objects.all())
    capacity = sum(p.total_seats for p in Performance.objects.all())
    theater_count = Theater.objects.count()
    hall_count = Hall.objects.count()
    return Response({
        "show_total": show_total,
        "show_on_sale": show_on_sale,
        "performance_total": perf_total,
        "order_paid": order_paid,
        "seats_sold": sold,
        "seats_capacity": capacity,
        "theater_count": theater_count,
        "hall_count": hall_count,
    })
