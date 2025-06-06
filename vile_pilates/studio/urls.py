from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AvailabilityView, BookingViewSet, MembershipViewSet, PlanIntentViewSet, PaymentViewSet, PromotionInstanceViewSet, PromotionViewSet, ScheduleViewSet, MonthlyRevenueViewSet, VentaViewSet, summary_by_class_type, attendance_summary, clases_por_mes, get_today_payments_total, get_weekly_closing_summary

# Crear un router para manejar las rutas
router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='bookings')
router.register(r'planintents', PlanIntentViewSet, basename='planintents')
router.register(r'memberships', MembershipViewSet, basename='memberships')
router.register(r'payments', PaymentViewSet, basename='payments')
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'monthly-revenue', MonthlyRevenueViewSet, basename='monthly-revenue')
router.register(r'promotions', PromotionViewSet, basename='promotions')
router.register(r'promotion-instances', PromotionInstanceViewSet, basename='promotion-instances')
router.register(r'ventas', VentaViewSet)

urlpatterns = [
    # Endpoint para la gestión de reservas
    path('', include(router.urls)),
    # Endpoint para consultar la disponibilidad
    path('availability/', AvailabilityView.as_view(), name='availability'),
    path('summary-by-class-type/', summary_by_class_type),
    path('attendance-summary/', attendance_summary),
    path('clases-por-mes/', clases_por_mes, name='clases-por-mes'),
    path('today/', get_today_payments_total, name='payments-today'),
    path('cierres-semanales/', get_weekly_closing_summary, name='cierres-semanales'),

]   
