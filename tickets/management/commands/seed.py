"""初始化内置管理员与种子业务数据（幂等）。"""
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from tickets.models import (
    Hall,
    MaintenancePeriod,
    Performance,
    Show,
    Theater,
    TicketOrder,
)


class Command(BaseCommand):
    help = "初始化管理员与演出票务种子数据"

    def handle(self, *args, **options):
        username = settings.DEFAULT_ADMIN_USERNAME
        password = settings.DEFAULT_ADMIN_PASSWORD
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, password=password, first_name="平台管理员")
            self.stdout.write("已创建管理员账号")

        if Theater.objects.exists():
            self.stdout.write("业务数据已存在，跳过")
            return

        grand_theater = Theater.objects.create(
            name="星河大剧院",
            address="上海市浦东新区世纪大道100号",
            description="城市地标级综合演艺中心",
        )
        art_center = Theater.objects.create(
            name="城南艺术中心",
            address="北京市朝阳区朝阳门外大街200号",
            description="专注于话剧与音乐剧的专业剧场",
        )
        concert_hall = Theater.objects.create(
            name="音乐厅",
            address="广州市天河区珠江新城300号",
            description="专业声学设计的音乐演出场馆",
        )

        hall1 = Hall.objects.create(
            theater=grand_theater,
            name="歌剧厅",
            capacity=1500,
            facilities=["专业舞台", "升降乐池", "LED大屏", "环绕音响", "专业灯光", "化妆间x10"],
            description="大剧院主厅，可承接大型歌剧、舞剧、演唱会",
        )
        hall2 = Hall.objects.create(
            theater=grand_theater,
            name="戏剧厅",
            capacity=600,
            facilities=["镜框式舞台", "专业灯光", "基础音响", "化妆间x5"],
            description="中型剧场，适合话剧、戏曲演出",
        )
        hall3 = Hall.objects.create(
            theater=grand_theater,
            name="小剧场",
            capacity=200,
            facilities=["黑匣子舞台", "基础灯光音响", "化妆间x2"],
            description="实验小剧场，适合先锋戏剧、小型演出",
        )

        hall4 = Hall.objects.create(
            theater=art_center,
            name="大剧场",
            capacity=800,
            facilities=["专业话剧舞台", "专业灯光", "扩声系统", "化妆间x8"],
            description="话剧专用剧场",
        )
        hall5 = Hall.objects.create(
            theater=art_center,
            name="小剧场",
            capacity=150,
            facilities=["灵活舞台", "基础设备", "化妆间x2"],
            description="小型实验剧场",
        )

        hall6 = Hall.objects.create(
            theater=concert_hall,
            name="交响乐厅",
            capacity=1200,
            facilities=["专业声学设计", "管风琴", "舞台升降", "化妆间x6"],
            description="专业交响乐演出厅",
        )
        hall7 = Hall.objects.create(
            theater=concert_hall,
            name="室内乐厅",
            capacity=400,
            facilities=["自然声学设计", "小型舞台", "化妆间x3"],
            description="室内乐独奏演出厅",
        )

        self.stdout.write("已创建 3 个剧场、7 个厅")

        shows_data = [
            {
                "title": "星河巡回演唱会·上海站",
                "troupe": "星河乐团",
                "genre": "concert",
                "status": "on_sale",
                "duration_minutes": 150,
                "setup_minutes": 120,
                "teardown_minutes": 60,
                "min_capacity": 1000,
                "required_facilities=["专业舞台", "LED大屏", "环绕音响", "专业灯光"],
            },
            {
                "title": "金陵往事",
                "troupe": "城南剧社",
                "genre": "drama",
                "status": "on_sale",
                "duration_minutes": 130,
                "setup_minutes": 90,
                "teardown_minutes": 45,
                "min_capacity": 400,
                "required_facilities=["镜框式舞台", "专业灯光"],
            },
            {
                "title": "敦煌·丝路飞天",
                "troupe": "丝路艺术团",
                "genre": "musical",
                "status": "upcoming",
                "duration_minutes": 160,
                "setup_minutes": 180,
                "teardown_minutes": 90,
                "min_capacity": 800,
                "required_facilities=["专业舞台", "LED大屏", "专业灯光"],
            },
            {
                "title": "经典戏曲专场",
                "troupe": "梨园名家",
                "genre": "opera",
                "status": "ended",
                "duration_minutes": 140,
                "setup_minutes": 60,
                "teardown_minutes": 30,
                "min_capacity": 300,
                "required_facilities=["专业灯光"],
            },
            {
                "title": "贝多芬交响乐之夜",
                "troupe": "国家交响乐团",
                "genre": "concert",
                "status": "upcoming",
                "duration_minutes": 120,
                "setup_minutes": 60,
                "teardown_minutes": 30,
                "min_capacity": 800,
                "required_facilities=["专业声学设计"],
            },
            {
                "title": "小王子",
                "troupe": "星空儿童剧团",
                "genre": "musical",
                "status": "upcoming",
                "duration_minutes": 90,
                "setup_minutes": 60,
                "teardown_minutes": 30,
                "min_capacity": 300,
                "required_facilities=["专业灯光", "基础音响"],
            },
            {
                "title": "雷雨",
                "troupe": "人民艺术剧院",
                "genre": "drama",
                "status": "upcoming",
                "duration_minutes": 150,
                "setup_minutes": 120,
                "teardown_minutes": 60,
                "min_capacity": 500,
                "required_facilities=["镜框式舞台", "专业灯光", "扩声系统"],
            },
            {
                "title": "钢琴独奏音乐会",
                "troupe": "李云迪工作室",
                "genre": "concert",
                "status": "upcoming",
                "duration_minutes": 100,
                "setup_minutes": 30,
                "teardown_minutes": 15,
                "min_capacity": 200,
                "required_facilities=["自然声学设计"],
            },
        ]

        shows = []
        for sd in shows_data:
            show = Show.objects.create(**sd)
            shows.append(show)

        self.stdout.write(f"已创建 {len(shows)} 个演出剧目")

        now = datetime.now().replace(microsecond=0, second=0, minute=0)
        day = timedelta(days=1)
        hour = timedelta(hours=1)

        performances_data = [
            (shows[0], hall1, now + 3 * day + 19 * hour, 1500, 860, 380, 150, 120, 60),
            (shows[0], hall1, now + 4 * day + 19 * hour, 1500, 300, 380, 150, 120, 60),
            (shows[1], hall2, now + 2 * day + 19 * hour, 600, 290, 180, 130, 90, 45),
            (shows[2], hall4, now + 20 * day + 19 * hour, 800, 0, 280, 160, 180, 90),
            (shows[3], hall2, now - 2 * day + 19 * hour, 600, 580, 150, 140, 60, 30),
            (shows[4], hall6, now + 10 * day + 19 * hour, 1200, 0, 480, 120, 60, 30),
            (shows[5], hall3, now + 5 * day + 14 * hour, 200, 0, 120, 90, 60, 30),
            (shows[5], hall3, now + 5 * day + 19 * hour, 200, 0, 120, 90, 60, 30),
            (shows[6], hall4, now + 15 * day + 19 * hour, 800, 0, 220, 150, 120, 60),
            (shows[7], hall7, now + 7 * day + 19 * hour, 400, 0, 200, 100, 30, 15),
        ]

        perfs = []
        for show, hall, start_at, total, sold, price, dur, setup, teardown in performances_data:
            end_at = start_at + timedelta(minutes=dur)
            setup_start = start_at - timedelta(minutes=setup)
            teardown_end = end_at + timedelta(minutes=teardown)

            perf = Performance.objects.create(
                show=show,
                hall=hall,
                start_at=start_at,
                end_at=end_at,
                setup_start_at=setup_start,
                teardown_end_at=teardown_end,
                total_seats=total,
                sold_seats=sold,
                price=price,
            )
            perfs.append(perf)

        self.stdout.write(f"已创建 {len(perfs)} 个演出场次")

        TicketOrder.objects.create(
            performance=perfs[0],
            customer_name="陈静",
            phone="13900001111",
            quantity=2,
            amount=760,
            status="paid",
        )
        TicketOrder.objects.create(
            performance=perfs[2],
            customer_name="刘洋",
            phone="13900002222",
            quantity=4,
            amount=720,
            status="paid",
        )
        TicketOrder.objects.create(
            performance=perfs[0],
            customer_name="孙琳",
            phone="13900003333",
            quantity=1,
            amount=380,
            status="cancelled",
        )
        self.stdout.write("已创建 3 个订单")

        MaintenancePeriod.objects.create(
            hall=hall1,
            start_at=now + 30 * day,
            end_at=now + 30 * day + timedelta(hours=8),
            reason="舞台设备定期检修",
        )
        MaintenancePeriod.objects.create(
            hall=hall6,
            start_at=now + 25 * day,
            end_at=now + 26 * day,
            reason="声学系统升级",
        )
        self.stdout.write("已创建 2 个维护期")

        self.stdout.write("种子数据初始化完成")
