from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

from tickets.views import (
    HallViewSet,
    LoginView,
    MaintenanceViewSet,
    OrderViewSet,
    PerformanceViewSet,
    ShowViewSet,
    TheaterViewSet,
    available_slots,
    auto_schedule_view,
    conflict_report,
    dashboard_stats,
    hall_calendar_view,
    me,
    utilization_report,
)


def health(_request):
    return JsonResponse({"status": "ok", "service": "show-ticketing-admin"})


router = DefaultRouter(trailing_slash=False)
router.register("theaters", TheaterViewSet)
router.register("halls", HallViewSet)
router.register("shows", ShowViewSet)
router.register("performances", PerformanceViewSet)
router.register("orders", OrderViewSet)
router.register("maintenance", MaintenanceViewSet, basename="maintenance")

urlpatterns = [
    path("health", health),
    path("auth/login", LoginView.as_view()),
    path("auth/me", me),
    path("dashboard/stats", dashboard_stats),
    path("scheduling/available-slots", available_slots),
    path("scheduling/auto-schedule", auto_schedule_view),
    path("scheduling/utilization", utilization_report),
    path("scheduling/conflict-report", conflict_report),
    path("scheduling/calendar", hall_calendar_view),
]

urlpatterns += router.urls
