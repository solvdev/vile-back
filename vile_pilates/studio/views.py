# studio/views.py
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from .models import Promotion, PromotionInstance, Schedule, Membership, Payment, Booking, PlanIntent, MonthlyRevenue, Venta
from .serializers import BookingSerializer, MembershipSerializer, PlanIntentSerializer, PaymentSerializer, PromotionInstanceSerializer, PromotionSerializer, ScheduleSerializer, ScheduleWithBookingsSerializer, BookingAttendanceUpdateSerializer, MonthlyRevenueSerializer, BookingHistorialSerializer, VentaSerializer
from accounts.serializers import ClientSerializer
from rest_framework import permissions
from rest_framework.views import APIView
from django.utils.dateparse import parse_date
from datetime import datetime, time as dtime, timedelta
from django.utils import timezone
from django.utils.timezone import now, localtime
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import F
from .utils import recalculate_monthly_revenue, recalculate_all_monthly_revenue
from .management.mails.mails import send_booking_confirmation_email, send_subscription_confirmation_email, send_individual_booking_pending_email
from rest_framework.decorators import api_view
from collections import Counter
from rest_framework.permissions import IsAdminUser
from accounts.models import Client
from decimal import Decimal, InvalidOperation
import pandas as pd
from studio.alerts import get_clients_with_consecutive_no_shows
import random, time, unicodedata
from studio.models import Client, Booking, Schedule, Membership, Payment
import time as pytime
from datetime import date as date_cls
import pytz 
from django.db import transaction
from django.utils.dateparse import parse_date
from math import ceil
from collections import defaultdict

import unicodedata

# Función que verifica si el cliente tiene una membresía activa
def has_active_membership(client):
    # Verificamos si el cliente tiene un pago reciente con una membresía activa
    latest_payment = Payment.objects.filter(client=client).order_by('-date_paid').first()
    return latest_payment and latest_payment.valid_until >= timezone.now().date()


from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import datetime, timedelta
from django.utils.timezone import now
from django.db.models import Q

@api_view(['GET'])
def clases_por_mes(request):
    """
    Devuelve resumen de clases válidas, no-shows y penalización sugerida por cliente en el mes.
    Solo penaliza los no-show sin causa justificada (sin cancellation_reason).
    """
    year = int(request.query_params.get('year', now().year))
    month = int(request.query_params.get('month', now().month))

    first_day = datetime(year, month, 1).date()
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)

    clients = Client.objects.filter(status="A")
    full_data = []

    for client in clients:
        active_payment = Payment.objects.filter(
            client=client,
            valid_until__gte=first_day
        ).order_by('-date_paid').first()

        if not active_payment:
            continue

        clases_esperadas = active_payment.membership.classes_per_month or 0

        clases_validas = Booking.objects.filter(
            client=client,
            class_date__range=[first_day, last_day],
            attendance_status__in=['attended', 'cancelled']
        ).count()

        # No-shows sin justificación
        clases_no_show = Booking.objects.filter(
            client=client,
            class_date__range=[first_day, last_day],
            attendance_status='no_show',
        ).filter(
            Q(cancellation_reason__isnull=True) | Q(cancellation_reason__exact='')
        ).count()

        # Fechas de no-show sin justificación
        date_no_show = Booking.objects.filter(
            client=client,
            class_date__range=[first_day, last_day],
            attendance_status='no_show',
        ).filter(
            Q(cancellation_reason__isnull=True) | Q(cancellation_reason__exact='')
        ).values_list('class_date', flat=True).distinct()

        penalizacion = clases_no_show * 35

        full_data.append({
            'client_id': client.id,
            'client_name': f"{client.first_name} {client.last_name}",
            'membership': active_payment.membership.name,
            'expected_classes': clases_esperadas,
            'valid_classes': clases_validas,
            'no_show_classes': clases_no_show,
            'date_no_show': date_no_show,
            'penalty': penalizacion,
        })

    return Response(full_data)


@api_view(['GET'])
def get_weekly_closing_summary(request):
    from collections import defaultdict
    from django.db.models import Sum
    from datetime import datetime
    from django.utils.timezone import localtime

    all_dates = Payment.objects.dates('date_paid', 'day')

    data_por_dia = []
    for date in all_dates:
        pagos = Payment.objects.filter(date_paid__date=date)
        ventas = Venta.objects.filter(date_sold__date=date)
        bookings = Booking.objects.filter(class_date=date)

        total_pago = sum(p.amount for p in pagos)
        total_venta = sum(v.total_amount for v in ventas)

        tarjeta = pagos.filter(payment_method='Tarjeta').aggregate(Sum('amount'))['amount__sum'] or 0
        efectivo = pagos.filter(payment_method='Efectivo').aggregate(Sum('amount'))['amount__sum'] or 0
        visalink = pagos.filter(payment_method='Visalink').aggregate(Sum('amount'))['amount__sum'] or 0

        pruebas = bookings.filter(client__trial_used=True).count()
        clases_ind = bookings.filter(schedule__is_individual=True).count()
        paquetes = pagos.count()
        asistencias = bookings.count()
        porcentaje = round((paquetes / asistencias * 100), 2) if asistencias else 0

        data_por_dia.append({
            "fecha": date.isoformat(),
            "total": round(total_pago + total_venta, 2),
            "asistencias": asistencias,
            "paquetes_vendidos": paquetes,
            "clases_individuales": clases_ind,
            "pruebas": pruebas,
            "tarjeta": float(tarjeta),
            "efectivo": float(efectivo),
            "visalink": float(visalink),
            "porcentaje_compra": porcentaje
        })

    # Agrupar por semana
    semanas = defaultdict(list)
    for dia in data_por_dia:
        fecha = datetime.fromisoformat(dia["fecha"])
        key = (fecha.isocalendar().year, fecha.isocalendar().week)
        semanas[key].append(dia)

    # Formatear la respuesta
    response = []
    for (año, semana), dias in semanas.items():
        fecha_inicio = min(datetime.fromisoformat(d["fecha"]) for d in dias)
        fecha_fin = max(datetime.fromisoformat(d["fecha"]) for d in dias)

        response.append({
            "semana": semana,
            "año": año,
            "rango": f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}",
            "total_semana": round(sum(d["total"] for d in dias), 2),
            "total_asistencias": sum(d["asistencias"] for d in dias),
            "total_paquetes": sum(d["paquetes_vendidos"] for d in dias),
            "total_clases_ind": sum(d["clases_individuales"] for d in dias),
            "total_pruebas": sum(d["pruebas"] for d in dias),
            "total_tarjeta": round(sum(d["tarjeta"] for d in dias), 2),
            "total_efectivo": round(sum(d["efectivo"] for d in dias), 2),
            "total_visalink": round(sum(d["visalink"] for d in dias), 2),
            "dias": dias
        })

    response = sorted(response, key=lambda s: (s["año"], s["semana"]))
    return Response(response)



class BookingViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = serializer.validated_data['client']
        schedule = serializer.validated_data['schedule']

        # Verificar si quien crea es admin o secretaria
        is_manual_checkin = request.user and request.user.is_authenticated and request.user.groups.filter(name__in=['admin', 'secretaria']).exists()

        # Extraer y convertir el valor de membership_id
        selected_membership = request.data.get('membership_id', None)
        try:
            selected_membership = int(selected_membership) if selected_membership is not None else None
        except ValueError:
            selected_membership = None

        # Verificar asistencia si viene en el request
        attendance_status = 'pending'
        if is_manual_checkin and request.data.get('attendance_status') == 'attended':
            attendance_status = 'attended'

        # 1) Validar cupo en el horario
        current_bookings = Booking.objects.filter(schedule=schedule, class_date=request.data.get("class_date")).count()
        if current_bookings >= schedule.capacity:
            return Response(
                {"detail": "No hay cupo disponible para este horario."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) Si seleccionó clase individual
        if selected_membership == 1:
            booking = serializer.save(
                membership=Membership.objects.get(pk=1),
                status='pending'
            )
            send_individual_booking_pending_email(booking)
            return Response({
                "detail": "Tu reserva para la clase individual está pendiente de confirmación. Realiza el depósito del 40% (aprox. Q36) para confirmar tu clase.",
                "booking_id": booking.id
            }, status=status.HTTP_201_CREATED)

        # 3) Si aún tiene clase de prueba gratuita
        if not client.trial_used:
            booking = serializer.save(attendance_status=attendance_status)
            if attendance_status == 'attended':
                client.trial_used = True
                client.save(update_fields=['trial_used'])
            send_booking_confirmation_email(booking)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # # 4) Si no tiene membresía activa
        # if not client.active_membership and not is_manual_checkin:
        #     return Response(
        #         {"detail": "No tienes una membresía activa. Por favor adquiere un plan para continuar."},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )

        # 5) Validar límite de clases según membresía o promoción
        latest_payment = Payment.objects.filter(client=client).order_by('-date_paid').first()
        if latest_payment:
            membership_plan = latest_payment.membership
            from .utils import count_valid_monthly_bookings

            monthly_bookings = count_valid_monthly_bookings(client)

            if latest_payment.promotion_id:
                promotion = latest_payment.promotion

                # Buscar instancia de promoción donde participe este cliente
                promo_instance = PromotionInstance.objects.filter(
                    promotion=promotion,
                    clients=client
                ).order_by('-created_at').first()

                if not promo_instance:
                    return Response({
                        "detail": "Esta promoción no está asociada correctamente a tu cuenta."
                    }, status=status.HTTP_400_BAD_REQUEST)

                if not promo_instance.is_active():
                    return Response({
                        "detail": "La promoción que adquiriste ya no está activa."
                    }, status=status.HTTP_400_BAD_REQUEST)

                if monthly_bookings >= promotion.clases_por_cliente:
                    return Response({
                        "detail": f"Has alcanzado tu límite de clases ({promotion.clases_por_cliente}) para esta promoción."
                    }, status=status.HTTP_400_BAD_REQUEST)

            elif membership_plan.classes_per_month and membership_plan.classes_per_month > 0:
                if monthly_bookings >= membership_plan.classes_per_month:
                    return Response({
                        "detail": "Has alcanzado tu límite de clases este mes."
                    }, status=status.HTTP_400_BAD_REQUEST)


        # 6) Crear reserva normal con membresía activa
        booking = serializer.save(
            membership=client.active_membership,
            attendance_status=attendance_status
        )
        if attendance_status == 'attended' and not client.trial_used:
            client.trial_used = True
            client.save(update_fields=['trial_used'])
        send_booking_confirmation_email(booking)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


    @action(detail=False, methods=['get'], url_path='by-client/(?P<client_id>[^/.]+)')
    def bookings_by_client(self, request, client_id=None):
        bookings = Booking.objects.filter(client_id=client_id).order_by('-class_date')
        serializer = BookingHistorialSerializer(bookings, many=True)
        return Response(serializer.data)

    
    @action(detail=True, methods=['put'], url_path='attendance')
    def mark_attendance(self, request, pk=None):
        try:
            booking = self.get_object()
        except Booking.DoesNotExist:
            return Response({"error": "Reserva no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookingAttendanceUpdateSerializer(booking, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            client = booking.client
            if not client.trial_used:
                client.trial_used = True
                client.save(update_fields=['trial_used'])
            return Response({'message': 'Asistencia actualizada correctamente.', 'data': serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], url_path='historial')
    def historial_asistencia(self, request):
        date_filter = request.query_params.get("date")
        queryset = Booking.objects.filter(status='active').select_related('client', 'schedule', 'schedule__class_type')


        if date_filter:
            try:
                date_obj = datetime.strptime(date_filter, "%Y-%m-%d").date()
                queryset = queryset.filter(class_date=date_obj)
            except ValueError:
                return Response({"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}, status=400)

        queryset = queryset.order_by('-class_date')
        serializer = BookingHistorialSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['put'], url_path='cancel')
    def cancel_booking(self, request, pk=None):
        booking = self.get_object()
        reason = request.data.get('reason', '')
        cancelled_by = request.data.get('by', 'client')  # client, instructor, admin

        booking.status = 'cancelled'
        booking.cancellation_type = cancelled_by
        booking.cancellation_reason = reason
        booking.save()

        return Response({"message": "Reserva cancelada correctamente."})

    @action(detail=True, methods=['put'], url_path='reschedule')
    def reschedule_booking(self, request, pk=None):
        booking = self.get_object()
        new_schedule_id = request.data.get('schedule_id')
        new_date = request.data.get('class_date')

        try:
            new_schedule = Schedule.objects.get(id=new_schedule_id)
        except Schedule.DoesNotExist:
            return Response({"error": "Nuevo horario no válido."}, status=400)

        # Validar que no exista una reserva duplicada
        if Booking.objects.filter(
            client=booking.client,
            schedule=new_schedule,
            class_date=new_date
        ).exists():
            return Response({"error": "Ya tienes una reserva para esa clase."}, status=400)

        # Validar capacidad
        count = Booking.objects.filter(
            schedule=new_schedule,
            class_date=new_date,
            status='active'
        ).count()
        if count >= new_schedule.capacity:
            return Response({"error": "No hay cupo disponible."}, status=400)

        # Actualizar
        booking.schedule = new_schedule
        booking.class_date = new_date
        booking.save()

        return Response({"message": "Clase reagendada correctamente."})
    
    
    
    
        return phone[:10] if phone else None
    

    def import_payments_from_excel(file_obj):

        def strip_accents(text):
            """Quitar acentos y minúsculas."""
            if not text:
                return ""
            text = unicodedata.normalize('NFD', text)
            return ''.join(c for c in text if unicodedata.category(c) != 'Mn').lower().strip()

        """
        Procesa un archivo Excel para asociar pagos a clientes existentes por nombre completo.
        También actualiza el estado del cliente a Activo si corresponde.
        """
        try:
            df = pd.read_excel(file_obj)
        except Exception as e:
            return {"error": f"Error al leer el archivo: {e}"}

        required_cols = {"name", "membership", "amount", "payment_date"}
        if not required_cols.issubset(df.columns):
            return {"error": "El archivo debe tener columnas: 'name', 'membership', 'amount', 'payment_date'."}

        memberships = {m.name.lower(): m for m in Membership.objects.all()}
        clients = {(f"{c.first_name} {c.last_name}"): c for c in Client.objects.all()}
        today = timezone.now().date()

        success = 0
        failed = []

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    name_raw = str(row.get("name", "")).strip()
                    membership_name = str(row.get("membership", "")).strip()
                    amount_raw = row.get("amount")
                    payment_date_raw = row.get("payment_date")

                    name_normalized = strip_accents(name_raw)
                    client = clients.get(name_normalized)

                    if not client:
                        failed.append({"row": idx + 2, "error": f"Cliente no encontrado: {name_raw}"})
                        continue

                    # Buscar membresía
                    membership = memberships.get(membership_name.lower())
                    if not membership:
                        failed.append({"row": idx + 2, "error": f"Membresía no encontrada: {membership_name}"})
                        continue

                    # Parsear monto
                    try:
                        amount = Decimal(str(amount_raw))
                    except Exception:
                        amount = membership.price

                    # Parsear fecha
                    try:
                        if isinstance(payment_date_raw, datetime):
                            date_paid = payment_date_raw
                        else:
                            date_paid = pd.to_datetime(payment_date_raw)
                    except Exception:
                        failed.append({"row": idx + 2, "error": "Fecha de pago inválida"})
                        continue

                    # Crear el Payment
                    payment = Payment.objects.create(
                        client=client,
                        membership=membership,
                        amount=amount,
                        date_paid=date_paid,
                        valid_until=date_paid.date() + timedelta(days=30)
                    )

                    # Verificar y actualizar estado activo
                    if payment.valid_until >= today and client.status != "A":
                        client.status = "A"
                        client.save(update_fields=["status"])

                    success += 1

                except Exception as exc:
                    failed.append({"row": idx + 2, "error": str(exc)})

        return {"message": f"Pagos importados correctamente: {success}", "errors": failed}

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        permission_classes=[IsAdminUser],
    )
    def import_bookings_from_excel(self, request):
        """
        Importa reservas (attended, no-show y canceladas) desde un archivo
        Excel / CSV exportado de Calendly.  Crea clientes, pagos y bookings
        en lote, evitando duplicados y time-outs.
        """
        import pandas as pd
        import pytz, unicodedata, random, time as pytime
        from decimal import Decimal, InvalidOperation
        from datetime import datetime, timedelta, time as dtime
        from django.db import transaction

        # ───────── helpers ──────────────────────────────────────────
        ALL_TZ = set(pytz.all_timezones)

        def is_tz(val: str | None) -> bool:
            return val in ALL_TZ if val else False

        def strip(txt: str | None) -> str:
            if not txt:
                return ""
            return "".join(
                c for c in unicodedata.normalize("NFD", txt)
                if unicodedata.category(c) != "Mn"
            ).lower().strip()

        def synth_dpi() -> str:
            base = int(pytime.time() * 1000) % 10_000_000_000  # 10 dígitos
            rand = random.randint(10, 99)                      # 2 dígitos
            return f"S{base:010d}{rand:02d}"                   # 13 chars

        def norm_email(e: str | None) -> str:
            if not e:
                return ""
            e = e.strip().lower()
            local, at, dom = e.partition("@")

            if dom in {"gmail.com", "googlemail.com"}:
                # Recorta alias +algo → nombre+familia  ⇒  nombre
                local = local.split("+", 1)[0]
                # Mantiene los puntos:
                #   claus.melgar+fam ⇒ claus.melgar   (✓ puntos intactos)
            return f"{local}{at}{dom}"

        def utf8(obj) -> str:
            if obj is None or str(obj).lower() in {"nan", "none"}:
                return ""
            return (str(obj)
                    .encode("utf-8", "ignore")
                    .decode("utf-8", "ignore")
                    .strip())

        def clean_phone(raw: str | None) -> str | None:
            """Normaliza a formato +502XXXXXXXX.
            - Elimina todos los caracteres no numéricos.
            - Si vienen 8 dígitos → añade prefijo 502.
            - Si ya viene con 502 (11 o 12 dígitos) se conserva.
            - En cualquier otro caso se devuelve tal cual para que QA lo revise.
            """
            if not raw or str(raw).lower() in {"nan", "none"}:
                return None
            digits = re.sub(r"[^0-9]", "", str(raw))
            if len(digits) == 8:          # local
                digits = "502" + digits
            elif digits.startswith("502") and len(digits) in {11, 12}:
                pass  # ya bien
            else:
                # número extraño, se retorna como apareció (sin +)
                return f"+{digits}" if digits else None
            return f"+{digits}"

        # ───────── leer archivo ─────────────────────────────────────
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "Archivo no proporcionado"}, status=400)

        try:
            df = pd.read_excel(
                file_obj,
                dtype={"payment_date": str, "valid_until": str, "class_date": str},
            )
        except Exception:
            file_obj.seek(0)
            try:
                df = pd.read_csv(file_obj, dtype=str)
            except Exception as e:
                return Response({"error": f"Error al leer archivo: {e}"}, status=400)

        required_cols = {
            "first_name", "last_name", "email", "phone",
            "class_date", "time_slot", "day",
        }
        faltantes = required_cols - set(df.columns)
        if faltantes:
            return Response({"error": f"Faltan columnas: {', '.join(faltantes)}"}, status=400)

        # ───────── caches y contenedores bulk ───────────────────────
        bulk_bookings, bulk_payments, bulk_updates = [], [], []
        touched_clients: set[int] = set()
        failed: list[dict] = []
        success = 0

        memberships = {m.name.lower(): m for m in Membership.objects.all()}
        schedules   = {(s.day, s.time_slot[:5]): s for s in Schedule.objects.all()}
        clients_e   = {
            c.email.lower(): c
            for c in Client.objects.only(
                "id", "email", "first_name", "last_name", "dpi",
                "phone", "notes", "status", "trial_used"
            )
        }
        name_phone_cache: dict[tuple[str, str | None], Client] = {}

        status_map = {
            "attended":    ("active",    "attended"),
            "no_show":     ("active",    "no_show"),
            "no attended": ("active",    "no_show"),
            "no asistio":  ("active",    "no_show"),
            "no asistió":  ("active",    "no_show"),
            "pending":     ("active",    "pending"),
            "cancelled":   ("cancelled", "pending"),
            "canceled":    ("cancelled", "pending"),
        }

        # ───────── iterar filas ─────────────────────────────────────
        for idx, row in df.iterrows():
            excel_row = idx + 2  # fila real en Excel
            try:
                # ―― normalizar campos ――――――――――――――――――――――――――
                fn  = utf8(row.get("first_name"))
                ln  = utf8(row.get("last_name"))
                em  = norm_email(utf8(row.get("email")))
                ph  = clean_phone(row.get("phone"))
                dpi = utf8(row.get("dpi"))
                nt  = utf8(row.get("notes"))
                src = utf8(row.get("source")) or "Migración Excel"

                memb_raw = utf8(row.get("membership"))
                att_raw  = utf8(row.get("attendance_status")).lower() or "attended"
                b_status, a_status = status_map.get(att_raw, ("active", "pending"))

                fn_n, ln_n = strip(fn), strip(ln)
                key_np = (fn_n + ln_n, ph)

                # ―― resolver / crear cliente ――――――――――――――――――
                cli = None
                if dpi.isdigit():
                    cli = Client.objects.filter(dpi=dpi).first()
                if not cli and em:
                    cli = clients_e.get(em)
                if not cli and ph:
                    cli = name_phone_cache.get(key_np)

                if not cli:
                    dpi_final = dpi if dpi.isdigit() else synth_dpi()
                    while Client.objects.filter(dpi=dpi_final).exists():
                        dpi_final = synth_dpi()
                    cli = Client.objects.create(
                        dpi=dpi_final,
                        first_name=fn,
                        last_name=ln,
                        email=em or f"{dpi_final}@noemail.com",
                        phone=ph,
                        notes=nt,
                        source=src,
                        status="I",
                    )
                    clients_e[cli.email.lower()] = cli
                name_phone_cache[key_np] = cli

                # actualizar campos faltantes
                dirty = False
                if not cli.phone and ph:
                    cli.phone, dirty = ph, True
                if not cli.dpi and dpi.isdigit():
                    cli.dpi, dirty = dpi, True
                if not cli.notes and nt:
                    cli.notes, dirty = nt, True
                if dirty and cli.id not in touched_clients:
                    bulk_updates.append(cli)
                    touched_clients.add(cli.id)

                # ―― schedule ―――――――――――――――――――――――――――――――
                day_code = utf8(row.get("day")).upper()
                time_raw = utf8(row.get("time_slot"))
                time_key = time_raw[:5] if ":" in time_raw else time_raw
                sched = schedules.get((day_code, time_key))
                if not sched:
                    failed.append({"row": excel_row, "error": f"No hay horario: {day_code} {time_key}"})
                    continue

                # ―― fecha de clase ―――――――――――――――――――――――――
                try:
                    class_date = pd.to_datetime(utf8(row.get("class_date"))).date()
                except Exception:
                    failed.append({"row": excel_row, "error": "class_date inválido"})
                    continue

                # ―― membresía / pago ―――――――――――――――――――――――
                member = None
                if memb_raw:
                    is_trial = memb_raw.lower() in {"trial", "clase de prueba"}
                    if not is_trial:
                        member = memberships.get(memb_raw.lower())
                        if not member:
                            failed.append({"row": excel_row,
                                        "error": f"Membresía no encontrada: {memb_raw}"})
                            continue

                        pay_raw = utf8(row.get("payment_date"))
                        if is_tz(pay_raw):
                            failed.append({"row": excel_row,
                                        "error": "payment_date contiene TZ"})
                            continue
                        try:
                            pay_day = pd.to_datetime(pay_raw).date()
                        except Exception:
                            failed.append({"row": excel_row, "error": "payment_date inválida"})
                            continue

                        pay_dt = timezone.make_aware(datetime.combine(pay_day, dtime.min))

                        val_raw = utf8(row.get("valid_until"))
                        if is_tz(val_raw):
                            val_raw = ""
                        try:
                            val_until = (pd.to_datetime(val_raw).date()
                                        if val_raw else None)
                        except Exception:
                            val_until = None
                        if not val_until:
                            val_until = pay_day + timedelta(days=30)

                        amt_raw = row.get("amount")
                        try:
                            amt = Decimal(str(amt_raw)) if amt_raw else member.price
                        except (InvalidOperation, TypeError):
                            amt = member.price

                        bulk_payments.append(
                            Payment(
                                client=cli,
                                membership=member,
                                date_paid=pay_dt,
                                valid_until=val_until,
                                amount=amt,
                            )
                        )
                    else:
                        if not cli.trial_used and a_status == "attended":
                            cli.trial_used = True
                            if cli.id not in touched_clients:
                                bulk_updates.append(cli)
                                touched_clients.add(cli.id)

                # ―― crear booking en memoria ――――――――――――――――――
                bulk_bookings.append(
                    Booking(
                        client=cli,
                        schedule=sched,
                        class_date=class_date,
                        attendance_status=a_status,
                        membership=member,
                        status=b_status,
                    )
                )
                success += 1

            except Exception as exc:
                failed.append({"row": excel_row, "error": str(exc)})

        # ───────── bulk DB ops ──────────────────────────────────────
        with transaction.atomic():
            if bulk_updates:
                Client.objects.bulk_update(
                    bulk_updates,
                    ["phone", "dpi", "notes", "status", "trial_used"],
                )
            if bulk_payments:
                Payment.objects.bulk_create(
                    bulk_payments, ignore_conflicts=True, batch_size=500
                )
            if bulk_bookings:
                Booking.objects.bulk_create(
                    bulk_bookings, ignore_conflicts=True, batch_size=500
                )

        return Response(
            {"message": f"Se importaron {success} filas.", "errors": failed},
            status=status.HTTP_200_OK,
        )



    
    @action(detail=False, methods=['get'], url_path='clientes-en-riesgo')
    def clientes_en_riesgo(self, request):
        from accounts.serializers import ClientSerializer

        clientes = get_clients_with_consecutive_no_shows(limit=3)
        data = ClientSerializer(clientes, many=True).data
        return Response(data)




class AvailabilityView(APIView):
    permission_classes = [permissions.AllowAny]
    """
    Endpoint que, dado un parámetro 'date' (YYYY-MM-DD), devuelve los slots disponibles
    para ese día, calculando el número de reservas activas y comparándolo con la capacidad.
    """
    def get(self, request, format=None):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({"detail": "Se requiere el parámetro 'date' en formato YYYY-MM-DD."}, status=400)
        
        requested_date = parse_date(date_str)
        if not requested_date:
            return Response({"detail": "Formato de fecha inválido."}, status=400)
        
        # Mapear weekday (0=Monday) a código de día definido en Schedule.DAY_CHOICES
        day_code_map = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}
        day_code = day_code_map[requested_date.weekday()]
        
        # Obtener todas las plantillas de horario (Schedule) para ese día
        schedules = Schedule.objects.filter(day=day_code)
        
        slots = []
        for schedule in schedules:
            # Contar reservas activas para este schedule en la fecha solicitada
            booking_count = Booking.objects.filter(
                schedule=schedule, 
                class_date=requested_date,
                status='active'
            ).exclude(attendance_status='cancelled').count()

            available = booking_count < schedule.capacity
            
            # Convertir el campo time_slot (e.g. '05:00') en un datetime combinando con requested_date
            start_time = datetime.combine(requested_date, datetime.strptime(schedule.time_slot, "%H:%M").time())
            end_time = start_time + timedelta(hours=1)  # Cada slot dura 1 hora
            
            slot = {
                "schedule_id": schedule.id,
                "class_type": schedule.class_type.name if schedule.class_type else None,
                "is_individual": schedule.is_individual,
                "capacity": schedule.capacity,
                "booked": booking_count,
                "coach":schedule.coach.first_name + " " + schedule.coach.last_name,
                "available": available,
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
            slots.append(slot)
        
        response_data = {
            "date": requested_date.isoformat(),
            "slots": sorted(slots, key=lambda x: x["start"])  # ⬅️ ORDENA POR start
        }
        return Response(response_data)

class MembershipViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Membership.objects.all()
    serializer_class = MembershipSerializer


class PlanIntentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]  # Puedes cambiar esto si solo admin puede ver todo
    queryset = PlanIntent.objects.all()
    serializer_class = PlanIntentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_confirmed', 'client']  # <- aquí
    

    def get_queryset(self):
        # Si se quiere filtrar solo por cliente actual (por token, por ejemplo)
        return PlanIntent.objects.all()

    @action(detail=False, methods=['get'], url_path='by-client/(?P<client_id>[^/.]+)')
    def by_client(self, request, client_id=None):
        intents = PlanIntent.objects.filter(client_id=client_id).order_by('-selected_at')
        serializer = self.get_serializer(intents, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='potenciales')
    def clientes_potenciales(self, request):
        from accounts.models import Client
        from accounts.serializers import ClientSerializer

        response_data = []

        # 1) Clientes con clase de prueba pendiente (trial_used=False)
        trial_clients = Client.objects.filter(trial_used=False)

        for client in trial_clients:
            plan_intent = PlanIntent.objects.filter(client=client, is_confirmed=False).order_by('-selected_at').first()
            response_data.append({
                "client": ClientSerializer(client).data,
                "plan_intent": PlanIntentSerializer(plan_intent).data if plan_intent else None
            })

        # 2) Clientes que ya usaron su clase de prueba pero tienen plan no confirmado
        with_trial_used = Client.objects.filter(trial_used=True)
        for client in with_trial_used:
            plan_intent = PlanIntent.objects.filter(client=client, is_confirmed=False).order_by('-selected_at').first()
            if plan_intent:
                response_data.append({
                    "client": ClientSerializer(client).data,
                    "plan_intent": PlanIntentSerializer(plan_intent).data
                })


        return Response(response_data)
    
class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by('-date_paid')
    serializer_class = PaymentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['client']

    def create(self, request, *args, **kwargs):
        from .models import PromotionInstance  # Evitar ciclos

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client = serializer.validated_data['client']
        client_id = client.id
        membership = serializer.validated_data['membership']
        payment_method = request.data.get("payment_method", None)
        amount = serializer.validated_data['amount']
        date_paid = serializer.validated_data.get("date_paid", timezone.now())

        today = date_paid.date()
        selected_promotion = None

        promo_instance = PromotionInstance.objects.filter(
            clients=client,
            promotion__membership=membership,
            promotion__start_date__lte=today,
            promotion__end_date__gte=today
        ).order_by('-created_at').first()

        if promo_instance:
            selected_promotion = promo_instance.promotion

        valid_until = today if membership.classes_per_month == 0 else today + timedelta(days=30)

        payment = Payment.objects.create(
            client_id=client_id,
            membership=membership,
            amount=amount,
            date_paid=date_paid,
            valid_until=valid_until,
            promotion=selected_promotion,
            promotion_instance=promo_instance,
            payment_method=payment_method
        )

        if payment.valid_until >= today:
            client.status = 'A'
            client.save(update_fields=['status'])

        try:
            plan_intent = PlanIntent.objects.filter(
                client_id=client_id,
                membership_id=membership.id,
                is_confirmed=False
            ).latest('selected_at')
            plan_intent.is_confirmed = True
            plan_intent.save()
        except PlanIntent.DoesNotExist:
            pass

        year = payment.date_paid.year
        month = payment.date_paid.month
        monthly, _ = MonthlyRevenue.objects.get_or_create(year=year, month=month)
        monthly.total_amount = F('total_amount') + payment.amount
        monthly.payment_count = F('payment_count') + 1
        monthly.save()

        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        amount = instance.amount
        date_paid = instance.date_paid
        client = instance.client

        self.perform_destroy(instance)

        year = date_paid.year
        month = date_paid.month

        try:
            monthly = MonthlyRevenue.objects.get(year=year, month=month)
            monthly.total_amount = F('total_amount') - amount
            monthly.payment_count = F('payment_count') - 1
            monthly.save()
        except MonthlyRevenue.DoesNotExist:
            pass

        if not Payment.objects.filter(client=client, valid_until__gte=timezone.now().date()).exists():
            client.status = 'I'
            client.save(update_fields=['status'])

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='en-gracia')
    def clientes_en_gracia(self, request):
        today = timezone.now().date()
        response = []

        pagos_en_gracia = Payment.objects.filter(
            valid_until__lt=today,
            valid_until__gte=today - timedelta(days=7)
        ).select_related('client', 'membership')

        vistos = set()

        for pago in pagos_en_gracia:
            client_id = pago.client.id
            if client_id in vistos:
                continue
            vistos.add(client_id)

            grace_ends = pago.valid_until + timedelta(days=7)

            response.append({
                "client": ClientSerializer(pago.client).data,
                "membership": pago.membership.name,
                "last_payment_date": pago.date_paid.date(),
                "valid_until": pago.valid_until,
                "grace_ends": grace_ends,
                "can_renew_at_previous_price": True
            })

        return Response(response)

    @action(detail=True, methods=['put'], url_path='extend-vigencia')
    def extend_vigencia(self, request, pk=None):
        payment = self.get_object()
        today = timezone.now().date()

        if payment.valid_until >= today:
            return Response({"detail": "El pago todavía está vigente. No es necesario extender."}, status=400)

        new_valid_until = today
        added_days = 0

        while added_days < 6:
            new_valid_until += timedelta(days=1)
            if new_valid_until.weekday() != 6:
                added_days += 1

        payment.valid_until = new_valid_until
        payment.save(update_fields=["valid_until"])

        return Response({"message": "Vigencia extendida exitosamente."})

class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().order_by('-date_sold')
    serializer_class = VentaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['client']
    ordering_fields = ['date_sold', 'total_amount']
    ordering = ['-date_sold']

    def perform_create(self, serializer):
        venta = serializer.save()
        date = venta.date_sold.date()
        year, month = date.year, date.month

        monthly, _ = MonthlyRevenue.objects.get_or_create(year=year, month=month)
        monthly.total_amount = F('total_amount') + venta.total_amount
        monthly.venta_total = F('venta_total') + venta.total_amount
        monthly.venta_count = F('venta_count') + 1
        monthly.save()

    def perform_destroy(self, instance):
        date = instance.date_sold.date()
        amount = instance.total_amount
        year, month = date.year, date.month
        super().perform_destroy(instance)

        try:
            monthly = MonthlyRevenue.objects.get(year=year, month=month)
            monthly.total_amount = F('total_amount') - amount
            monthly.venta_total = F('venta_total') - amount
            monthly.venta_count = F('venta_count') - 1
            monthly.save()
        except MonthlyRevenue.DoesNotExist:
            pass

class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.select_related('coach', 'class_type').all()
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.AllowAny]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['day', 'coach']
    ordering_fields = ['day', 'time_slot']
    ordering = ['day', 'time_slot']

    @action(detail=False, methods=['get'], url_path='today')
    def get_today_classes(self, request):
        coach_id = request.query_params.get('coach_id')
        today = datetime.now().date()
        day_code = today.strftime('%a').upper()[:3]

        if coach_id:
            schedules = Schedule.objects.filter(day=day_code, coach_id=coach_id).order_by('time_slot')
            print("if")
        else:
            schedules = Schedule.objects.filter(day=day_code, coach=request.user).order_by('time_slot')
            print("else")

        serializer = ScheduleWithBookingsSerializer(
            schedules,
            many=True,
            context={'request': request, 'today': today}
        )
        return Response(serializer.data)

class MonthlyRevenueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MonthlyRevenue.objects.all()
    serializer_class = MonthlyRevenueSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['year', 'month']
    ordering_fields = ['year', 'month']
    ordering = ['-year', '-month']

    @action(detail=False, methods=['post'], url_path='recalculate')
    def recalculate(self, request):
        year = request.data.get('year')
        month = request.data.get('month')
        if not year or not month:
            return Response({"error": "Se requiere 'year' y 'month'."}, status=400)

        try:
            result = recalculate_monthly_revenue(int(year), int(month))
            return Response({
                "message": "Resumen mensual recalculado exitosamente.",
                "data": result
            })
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        
    @action(detail=False, methods=['post'], url_path='recalculate-all')
    def recalculate_all(self, request):
        try:
            result = recalculate_all_monthly_revenue()
            return Response({
                "message": "Todos los resúmenes mensuales recalculados exitosamente.",
                "data": result
            })
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        
    @action(detail=False, methods=['get'], url_path='total')
    def total_revenue(self, request):
        from django.db.models import Sum
        total = MonthlyRevenue.objects.aggregate(total=Sum('total_amount'))['total'] or 0
        return Response({"total_revenue": float(total)})
    
    
@api_view(['GET'])
def get_today_payments_total(request):
    today = localtime(now()).date()
    payments = Payment.objects.filter(date_paid__date=today)
    total = sum(p.amount for p in payments)
    return Response({
        "date": today,
        "total": round(total, 2),
        "count": payments.count()
        })

@api_view(['GET'])
def summary_by_class_type(request):
    from .models import Booking

    bookings = Booking.objects.select_related("schedule__class_type").all()
    counter = Counter()

    for b in bookings:
        if b.schedule and b.schedule.class_type:
            name = b.schedule.class_type.name
            counter[name] += 1

    data = [{"class_type": k, "count": v} for k, v in counter.items()]
    return Response(data)

@api_view(['GET'])
def     attendance_summary(request):
    from .models import Booking
    from django.utils.timezone import now
    from datetime import timedelta

    today = now().date()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)

    bookings = Booking.objects.filter(
        class_date__range=[start_week, end_week],
        attendance_status='attended'
    )

    summary = Counter(b.class_date.strftime('%A') for b in bookings)
    return Response(summary)

class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all().order_by('-start_date')
    serializer_class = PromotionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['membership', 'start_date', 'end_date']

class PromotionInstanceViewSet(viewsets.ModelViewSet):
    queryset = PromotionInstance.objects.all().order_by('-created_at')
    serializer_class = PromotionInstanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['promotion', 'created_at']

    @action(detail=True, methods=['post'], url_path='confirm-payment')
    def confirm_payment(self, request, pk=None):
        instance = self.get_object()
        client_id = request.data.get('client_id')

        if not client_id:
            return Response({"detail": "Falta el ID del cliente."}, status=400)

        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return Response({"detail": "Cliente no encontrado."}, status=404)

        today = timezone.now().date()
        promotion = instance.promotion
        membership = promotion.membership
        amount = promotion.price
        valid_until = today + timedelta(days=30)

        # Crear el pago vinculado a esta instancia
        payment = Payment.objects.create(
            client=client,
            membership=membership,
            promotion=promotion,
            promotion_instance=instance,
            amount=amount,
            date_paid=timezone.now(),
            valid_until=valid_until
        )

        # Activar cliente si aplica
        if valid_until >= today and client.status != "A":
            client.status = "A"
            client.save(update_fields=["status"])

        # Confirmar plan intent si aplica (reutiliza tu lógica actual)
        try:
            plan_intent = PlanIntent.objects.filter(
                client=client,
                membership=membership,
                is_confirmed=False
            ).latest('selected_at')
            plan_intent.is_confirmed = True
            plan_intent.save()
        except PlanIntent.DoesNotExist:
            pass

        # Recalcular ingresos mensuales
        year = payment.date_paid.year
        month = payment.date_paid.month
        revenue, _ = MonthlyRevenue.objects.get_or_create(year=year, month=month)
        revenue.total_amount = F('total_amount') + payment.amount
        revenue.payment_count = F('payment_count') + 1
        revenue.save()

        # Correo opcional
        try:
            send_subscription_confirmation_email(payment)
        except Exception as e:
            print(f"Error al enviar correo: {e}")

        return Response(PaymentSerializer(payment).data, status=201)