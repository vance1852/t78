from rest_framework import serializers

from tickets.models import (
    Hall,
    MaintenancePeriod,
    Performance,
    Show,
    Theater,
    TicketOrder,
)


class TheaterSerializer(serializers.ModelSerializer):
    hall_count = serializers.SerializerMethodField()

    class Meta:
        model = Theater
        fields = ["id", "name", "address", "description", "hall_count", "created_at"]
        read_only_fields = ["id", "hall_count", "created_at"]

    def get_hall_count(self, obj):
        return obj.halls.count()


class HallSerializer(serializers.ModelSerializer):
    theater_name = serializers.CharField(source="theater.name", read_only=True)

    class Meta:
        model = Hall
        fields = [
            "id", "theater", "theater_name", "name", "capacity",
            "facilities", "description", "created_at",
        ]
        read_only_fields = ["id", "theater_name", "created_at"]


class HallDetailSerializer(serializers.ModelSerializer):
    theater_name = serializers.CharField(source="theater.name", read_only=True)

    class Meta:
        model = Hall
        fields = [
            "id", "theater", "theater_name", "name", "capacity",
            "facilities", "description", "created_at",
        ]
        read_only_fields = ["id", "theater_name", "created_at"]


class ShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Show
        fields = [
            "id", "title", "troupe", "genre", "status",
            "duration_minutes", "setup_minutes", "teardown_minutes",
            "min_capacity", "required_facilities", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PerformanceSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="show.title", read_only=True)
    hall_name = serializers.CharField(source="hall.name", read_only=True)
    theater_name = serializers.CharField(source="hall.theater.name", read_only=True)
    remaining_seats = serializers.SerializerMethodField()

    class Meta:
        model = Performance
        fields = [
            "id", "show", "show_title", "hall", "hall_name", "theater_name",
            "start_at", "end_at", "setup_start_at", "teardown_end_at",
            "total_seats", "sold_seats", "remaining_seats", "price", "created_at",
        ]
        read_only_fields = [
            "id", "show_title", "hall_name", "theater_name",
            "sold_seats", "remaining_seats", "created_at",
        ]

    def get_remaining_seats(self, obj):
        return obj.total_seats - obj.sold_seats


class PerformanceCreateSerializer(serializers.Serializer):
    show = serializers.IntegerField()
    hall = serializers.IntegerField()
    start_at = serializers.DateTimeField()
    total_seats = serializers.IntegerField(min_value=0)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class MaintenanceSerializer(serializers.ModelSerializer):
    hall_name = serializers.CharField(source="hall.name", read_only=True)
    theater_name = serializers.CharField(source="hall.theater.name", read_only=True)

    class Meta:
        model = MaintenancePeriod
        fields = [
            "id", "hall", "hall_name", "theater_name",
            "start_at", "end_at", "reason", "created_at",
        ]
        read_only_fields = ["id", "hall_name", "theater_name", "created_at"]


class ConflictCheckSerializer(serializers.Serializer):
    hall = serializers.IntegerField()
    show = serializers.IntegerField(required=False, allow_null=True)
    start_at = serializers.DateTimeField()
    exclude_performance = serializers.IntegerField(required=False, allow_null=True)


class DragCheckSerializer(serializers.Serializer):
    performance = serializers.IntegerField()
    new_hall = serializers.IntegerField()
    new_start_at = serializers.DateTimeField()


class AvailableSlotSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    min_capacity = serializers.IntegerField(min_value=0, required=False, default=0)
    duration_minutes = serializers.IntegerField(min_value=1, required=False, default=120)
    setup_minutes = serializers.IntegerField(min_value=0, required=False, default=60)
    teardown_minutes = serializers.IntegerField(min_value=0, required=False, default=30)
    hall_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=None,
    )
    required_facilities = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True, default=None,
    )


class AutoScheduleSerializer(serializers.Serializer):
    show_ids = serializers.ListField(child=serializers.IntegerField())
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    priority_mode = serializers.ChoiceField(
        choices=["high_first", "long_first", "short_first"],
        required=False,
        default="high_first",
    )
    hall_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=None,
    )


class ImpactAnalysisSerializer(serializers.Serializer):
    performance = serializers.IntegerField()
    new_hall = serializers.IntegerField()
    new_start_at = serializers.DateTimeField()


class HallCalendarSerializer(serializers.Serializer):
    hall_id = serializers.IntegerField(required=False, allow_null=True)
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()


class OrderSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="performance.show.title", read_only=True)

    class Meta:
        model = TicketOrder
        fields = [
            "id", "performance", "show_title", "customer_name", "phone",
            "quantity", "amount", "status", "created_at",
        ]
        read_only_fields = ["id", "amount", "status", "created_at"]


class OrderCreateSerializer(serializers.Serializer):
    performance = serializers.IntegerField()
    customer_name = serializers.CharField(max_length=64)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, max_value=10)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class UtilizationReportSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    hall_id = serializers.IntegerField(required=False, allow_null=True)


class ConflictReportSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
