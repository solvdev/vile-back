# accounts/views.py
from rest_framework import viewsets, permissions
from rest_framework.pagination import PageNumberPagination
from .models import CustomUser, Client
from rest_framework.response import Response
from .serializers import CustomUserSerializer, ClientSerializer
from rest_framework import filters
from rest_framework.decorators import action
from datetime import date
from studio.models import Payment, PlanIntent
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.contrib.auth.models import Group as AuthGroup

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    serializer = CustomUserSerializer(request.user)
    return Response(serializer.data)

class CustomUserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer
    # Solo administradores podrán acceder a estos endpoints
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['get'], url_path='coaches')
    def list_coaches(self, request):
        coach_group = AuthGroup.objects.filter(name="coach").first()
        if not coach_group:
            return Response([], status=200)

        coaches = CustomUser.objects.filter(groups=coach_group)
        serializer = self.get_serializer(coaches, many=True)
        return Response(serializer.data)


# class ClientPagination(PageNumberPagination):
#     page_size = 10
#     page_size_query_param = 'page_size'
#     max_page_size = 100


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('id')  # ← orden opcional
    serializer_class = ClientSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['email', 'first_name', 'last_name', 'phone', 'dpi']  # ← puedes buscar por más campos
    # pagination_class = ClientPagination

    @action(detail=True, methods=['get'], url_path='estado')
    def estado_cliente(self, request, pk=None):
        client = self.get_object()

        # Verificar membresía activa
        latest_payment = Payment.objects.filter(client=client).order_by('-date_paid').first()
        plan_activo = latest_payment and latest_payment.valid_until >= date.today()

        # Verificar si tiene intención de plan pendiente (no confirmada)
        plan_intent = PlanIntent.objects.filter(client=client, is_confirmed=False).order_by('-selected_at').first()

        if not client.trial_used and not plan_intent:
            estado = 'nuevo'
        elif not client.trial_used and plan_intent:
            estado = 'conClaseGratisPendienteYPlanSeleccionado'
        elif client.trial_used and not plan_activo and plan_intent:
            estado = 'conClaseGratisUsadaYPlanSeleccionado'
        elif client.trial_used and not plan_activo and not plan_intent:
            estado = 'conClaseGratisUsada'
        elif plan_activo:
            estado = 'conPlanActivo'
        else:
            estado = 'desconocido'

        puede_agendar = not client.trial_used or plan_activo

        return Response({
            "estado": estado,
            "puede_agendar": puede_agendar,
            "trial_used": client.trial_used,
            "plan_activo": bool(plan_activo),
            "plan_seleccionado": bool(plan_intent),
            "mensaje": self._mensaje_por_estado(estado),
            "plan_intent": {
                "membership_id": plan_intent.membership.id,
                "membership_name": plan_intent.membership.name,
                "price": plan_intent.membership.price
            } if plan_intent else None
        })

    def _mensaje_por_estado(self, estado):
        mensajes = {
            'nuevo': "Bienvenido, agenda tu clase de prueba gratuita.",
            'conClaseGratisPendienteYPlanSeleccionado': "Puedes usar tu clase gratuita o activar el plan que seleccionaste.",
            'conClaseGratisUsada': "Ya usaste tu clase gratuita. Suscríbete para seguir entrenando con nosotros.",
            'conClaseGratisUsadaYPlanSeleccionado': "Ya usaste tu clase gratuita. Tienes un plan pendiente, actívalo para continuar entrenando con nosotros.",
            'conPlanActivo': "Tu plan está activo. Puedes agendar tus clases.",
            'desconocido': "No pudimos determinar tu estado, por favor contáctanos."
        }
        return mensajes.get(estado, '')
    
    @action(detail=False, methods=['get'], url_path='dpi')
    def client_por_dpi(self, request):
        dpi = request.query_params.get('dpi')
        if not dpi:
            return Response({"detail": "Se requiere el parámetro 'dpi'."}, status=400)
        
        client = Client.objects.filter(dpi=dpi).first()
        if client:
            # Reutilizamos la función de estado para obtener el estado del cliente
            latest_payment = Payment.objects.filter(client=client).order_by('-date_paid').first()
            plan_activo = latest_payment and latest_payment.valid_until >= date.today()
            plan_intent = PlanIntent.objects.filter(client=client, is_confirmed=False).order_by('-selected_at').first()
            if not client.trial_used and not plan_intent:
                estado = 'nuevo'
            elif not client.trial_used and plan_intent:
                estado = 'conClaseGratisPendienteYPlanSeleccionado'
            elif client.trial_used and not plan_activo and plan_intent:
                estado = 'conClaseGratisUsadaYPlanSeleccionado'
            elif client.trial_used and not plan_activo and not plan_intent:
                estado = 'conClaseGratisUsada'
            elif plan_activo:
                estado = 'conPlanActivo'
            else:
                estado = 'desconocido'

            puede_agendar = not client.trial_used or plan_activo
            mensaje = {
                'nuevo': "Bienvenido, agenda tu clase de prueba gratuita.",
                'conClaseGratisPendienteYPlanSeleccionado': "Puedes usar tu clase gratuita o activar el plan que seleccionaste.",
                'conClaseGratisUsada': "Ya usaste tu clase gratuita. Suscríbete para seguir entrenando con nosotros.",
                'conClaseGratisUsadaYPlanSeleccionado': "Ya usaste tu clase gratuita. Tienes un plan pendiente, actívalo para continuar entrenando con nosotros.",
                'conPlanActivo': "Tu plan está activo. Puedes agendar tus clases.",
                'desconocido': "No pudimos determinar tu estado, por favor contáctanos."
            }.get(estado, '')

            return Response({
                "client": ClientSerializer(client).data,
                "estado": estado,
                "puede_agendar": puede_agendar,
                "trial_used": client.trial_used,
                "plan_activo": bool(plan_activo),
                "plan_seleccionado": bool(plan_intent),
                "mensaje": mensaje,
                "plan_intent": {
                    "membership_id": plan_intent.membership.id,
                    "membership_name": plan_intent.membership.name,
                    "price": plan_intent.membership.price
                } if plan_intent else None
            })
        else:
            return Response({"detail": "No se encontró un cliente con ese DPI."}, status=404)
        
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        original_status = instance.status
        original_membership = instance.active_membership

        response = super().update(request, *args, **kwargs)

        updated_instance = self.get_object()
        updated_status = updated_instance.status
        updated_membership = updated_instance.active_membership

        if (
            (original_status == 'A' and updated_status == 'I') or
            (original_membership and not updated_membership)
        ):
            try:
                from studio.management.mails.mails import send_membership_cancellation_email
                send_membership_cancellation_email(updated_instance)
            except Exception as e:
                print(f"[ERROR] Falló envío de correo de cancelación: {str(e)}")

        return response
    
    @action(detail=False, methods=['get'], url_path='count')
    def count_clients(self, request):
        today = timezone.now().date()
        total = Client.objects.count()
        active = Client.objects.filter(status='A').count()
        inactive = Client.objects.filter(status='I').count()
        new_this_month = Client.objects.filter(
            created_at__year=today.year,
            created_at__month=today.month
        ).count()

        return Response({
            "total": total,
            "active": active,
            "inactive": inactive,
            "new_this_month": new_this_month
    })


