from rest_framework import serializers
from .models import (
    ClassType,
    PromotionInstance,
    Schedule,
    Membership,
    Payment,
    Booking,
    PlanIntent,
    MonthlyRevenue,
    Promotion,
    Venta,
)
from accounts.models import Client


class ClassTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassType
        fields = "__all__"


class ScheduleSerializer(serializers.ModelSerializer):
    class_type = ClassTypeSerializer(read_only=True)
    class_type_id = serializers.PrimaryKeyRelatedField(
        source="class_type", queryset=ClassType.objects.all(), write_only=True
    )
    day_display = serializers.CharField(source="get_day_display", read_only=True)
    time_display = serializers.CharField(source="get_time_slot_display", read_only=True)
    coach_username = serializers.CharField(source="coach.username", read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "day",
            "day_display",
            "time_slot",
            "time_display",
            "capacity",
            "is_individual",
            "class_type",
            "class_type_id",
            "coach",
            "coach_username",
        ]


class SimpleClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"


class BookingAttendanceInlineSerializer(serializers.ModelSerializer):
    client = SimpleClientSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "client", "attendance_status", "class_date"]


class ScheduleWithBookingsSerializer(serializers.ModelSerializer):
    class_type = ClassTypeSerializer(read_only=True)
    bookings = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            "id",
            "day",
            "time_slot",
            "class_type",
            "is_individual",
            "capacity",
            "bookings",
        ]

    def get_bookings(self, obj):
        today = self.context.get("today")
        bookings = Booking.objects.filter(
            schedule=obj, class_date=today, status="active"
        )
        return BookingAttendanceInlineSerializer(bookings, many=True).data


class BookingAttendanceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["attendance_status"]
        extra_kwargs = {
            "attendance_status": {
                "required": True,
                "choices": Booking.ATTENDANCE_CHOICES,
            }
        }


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(
        source="client", queryset=Client.objects.all(), write_only=True
    )
    membership = MembershipSerializer(read_only=True)
    membership_id = serializers.PrimaryKeyRelatedField(
        source="membership", queryset=Membership.objects.all(), write_only=True
    )

    promotion_id = serializers.PrimaryKeyRelatedField(
        source="promotion",
        queryset=Promotion.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    promotion = serializers.StringRelatedField(read_only=True)

    date_paid = serializers.DateTimeField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "client",
            "client_id",
            "membership",
            "membership_id",
            "promotion",
            "promotion_id",
            "promotion_instance",
            "promotion_instance_id",
            "amount",
            "date_paid",
            "valid_until",
        ]

class BookingSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(
        source="client",
        queryset=__import__("accounts.models").models.Client.objects.all(),
        write_only=True,
    )
    schedule = serializers.StringRelatedField(read_only=True)
    schedule_id = serializers.PrimaryKeyRelatedField(
        source="schedule", queryset=Schedule.objects.all(), write_only=True
    )
    membership = serializers.StringRelatedField(read_only=True)
    membership_id = serializers.PrimaryKeyRelatedField(
        source="membership",
        queryset=Membership.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Booking
        fields = [
            "id",
            "client",
            "client_id",
            "schedule",
            "schedule_id",
            "class_date",
            "date_booked",
            "membership",
            "membership_id",
        ]


class PlanIntentSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    membership = serializers.SerializerMethodField()

    class Meta:
        model = PlanIntent
        fields = "__all__"

    def get_client(self, obj):
        from accounts.serializers import ClientSerializer

        return ClientSerializer(obj.client).data

    def get_membership(self, obj):
        return MembershipSerializer(obj.membership).data


class BookingHistorialSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    membership = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()
    schedule_id = serializers.IntegerField(
        source="schedule.id", read_only=True
    )  # 🔥 importante
    class_date = serializers.DateField(format="%Y-%m-%d")

    class Meta:
        model = Booking
        fields = [
            "id",
            "client",
            "schedule",
            "schedule_id",
            "class_date",
            "attendance_status",
            "date_booked",
            "membership",
            "cancellation_reason",
        ]

    def get_client(self, obj):
        return f"{obj.client.first_name} {obj.client.last_name}"
    
    def get_membership(self, obj):
        if obj.membership:
            return f"{obj.membership.name} ({obj.membership.price})"
        return "-"

    def get_schedule(self, obj):
        if obj.schedule:
            day_name = obj.class_date.strftime("%A")
            day_name_es = {
                "Monday": "Lunes",
                "Tuesday": "Martes",
                "Wednesday": "Miércoles",
                "Thursday": "Jueves",
                "Friday": "Viernes",
                "Saturday": "Sábado",
                "Sunday": "Domingo",
            }.get(day_name, day_name)
            return f"{day_name_es} {obj.schedule.time_slot} ({'Individual' if obj.schedule.is_individual else 'Grupal'})"
        return "-"


class MonthlyRevenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyRevenue
        fields = [
            "id",
            "year",
            "month",
            "total_amount",
            "payment_count",
            "venta_total",
            "venta_count",
            "last_updated",
        ]


class PromotionSerializer(serializers.ModelSerializer):
    membership = serializers.SerializerMethodField()
    membership_id = serializers.PrimaryKeyRelatedField(
        source='membership', queryset=Membership.objects.all(), write_only=True
    )
    
    class Meta:
        model = Promotion
        fields = [
            'id', 'name', 'description',
            'start_date', 'end_date', 'price',
            'membership', 'membership_id',
        ]

    def get_membership(self, obj):
        # No se importa nada, MembershipSerializer ya está en este archivo
        return MembershipSerializer(obj.membership).data



class PromotionInstanceSerializer(serializers.ModelSerializer):
    promotion = PromotionSerializer(read_only=True)
    promotion_id = serializers.PrimaryKeyRelatedField(
        source='promotion', queryset=Promotion.objects.all(), write_only=True
    )
    clients = serializers.SerializerMethodField()
    client_ids = serializers.PrimaryKeyRelatedField(
        source='clients', many=True, queryset=Client.objects.all(), write_only=True
    )

    class Meta:
        model = PromotionInstance
        fields = ['id', 'promotion', 'promotion_id', 'clients', 'client_ids', 'created_at']

    def get_clients(self, obj):
        from accounts.serializers import ClientSerializer
        return ClientSerializer(obj.clients.all(), many=True).data
    

class VentaSerializer(serializers.ModelSerializer):
    client_id = serializers.PrimaryKeyRelatedField(
        source='client',
        queryset=Client.objects.all()
    )
    date_sold = serializers.DateTimeField(required=False)

    class Meta:
        model = Venta
        fields = [
            'id', 'client_id', 'product_name', 'quantity',
            'price_per_unit', 'total_amount', 'payment_method', 'notes', 'date_sold'
        ]
        read_only_fields = ['id']