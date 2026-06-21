from django.db import models


class Theater(models.Model):
    """剧场。"""

    name = models.CharField(max_length=128)
    address = models.CharField(max_length=256, blank=True, default="")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "theaters"

    def __str__(self):
        return self.name


class Hall(models.Model):
    """演出厅。"""

    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name="halls")
    name = models.CharField(max_length=64)
    capacity = models.IntegerField(default=0)
    facilities = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "halls"
        unique_together = ("theater", "name")

    def __str__(self):
        return f"{self.theater.name} - {self.name}"


class Show(models.Model):
    """演出剧目。"""

    GENRE_CHOICES = [
        ("concert", "演唱会"),
        ("drama", "话剧"),
        ("musical", "音乐剧"),
        ("opera", "戏曲"),
        ("other", "其他"),
    ]
    STATUS_CHOICES = [
        ("on_sale", "售票中"),
        ("upcoming", "待开票"),
        ("ended", "已结束"),
    ]

    title = models.CharField(max_length=128)
    troupe = models.CharField(max_length=128, blank=True, default="")
    genre = models.CharField(max_length=16, choices=GENRE_CHOICES, default="concert")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="upcoming")
    duration_minutes = models.IntegerField(default=120)
    setup_minutes = models.IntegerField(default=60)
    teardown_minutes = models.IntegerField(default=30)
    min_capacity = models.IntegerField(default=0)
    required_facilities = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shows"

    def __str__(self):
        return self.title


class Performance(models.Model):
    """演出场次。"""

    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="performances")
    hall = models.ForeignKey(Hall, on_delete=models.PROTECT, related_name="performances")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    setup_start_at = models.DateTimeField()
    teardown_end_at = models.DateTimeField()
    total_seats = models.IntegerField(default=0)
    sold_seats = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "performances"
        indexes = [
            models.Index(fields=["hall", "start_at"]),
            models.Index(fields=["show", "start_at"]),
        ]

    def __str__(self):
        return f"{self.show.title} - {self.hall.name} - {self.start_at}"


class MaintenancePeriod(models.Model):
    """厅维护期。"""

    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name="maintenance_periods")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "maintenance_periods"
        indexes = [
            models.Index(fields=["hall", "start_at"]),
        ]

    def __str__(self):
        return f"{self.hall.name} 维护 - {self.start_at} ~ {self.end_at}"


class TicketOrder(models.Model):
    """购票订单。"""

    STATUS_CHOICES = [
        ("paid", "已支付"),
        ("cancelled", "已取消"),
    ]

    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="orders")
    customer_name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32, blank=True, default="")
    quantity = models.IntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="paid")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_orders"
