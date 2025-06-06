# studio/admin.py
from django.contrib import admin
from .models import ClassType, PromotionInstance, Schedule, Membership, Payment, Booking, PlanIntent, MonthlyRevenue, Promotion, Venta

@admin.register(ClassType)
class ClassTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('day', 'get_time_slot_display', 'is_individual', 'capacity')

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'classes_per_month')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'membership', 'amount', 'date_paid', 'valid_until')
    date_hierarchy = 'date_paid'

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'schedule', 'date_booked')

@admin.register(PlanIntent)
class PlanIntentAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'membership', 'selected_at', 'is_confirmed')
    list_filter = ('is_confirmed', 'selected_at')
    search_fields = ('client__first_name', 'client__last_name', 'membership__name')


@admin.register(MonthlyRevenue)
class MonthlyRevenueAdmin(admin.ModelAdmin):
    list_display = ('year', 'month', 'total_amount', 'payment_count', 'last_updated')
    list_filter = ('year', 'month')
    ordering = ('-year', '-month')
    
@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'membership', 'price', 'start_date', 'end_date')
    list_filter = ('start_date', 'end_date', 'membership')
    search_fields = ('name', 'membership__name')

@admin.register(PromotionInstance)
class PromotionInstanceAdmin(admin.ModelAdmin):
  list_display = ('id', 'promotion', 'created_at')
  filter_horizontal = ('clients',)
  list_filter = ('promotion', 'created_at')
  search_fields = ('promotion__name',)

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'product_name', 'quantity', 'price_per_unit', 'total_amount', 'payment_method', 'date_sold')
    list_filter = ('payment_method', 'date_sold')
    search_fields = ('client__first_name', 'client__last_name', 'product_name')
    date_hierarchy = 'date_sold'