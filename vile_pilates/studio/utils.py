from django.db.models import Sum
from .models import Payment, MonthlyRevenue
from django.db.models.functions import TruncMonth
from django.db.models import Count
from django.db import models

def recalculate_monthly_revenue(year, month):
    from .models import Payment, MonthlyRevenue, Venta

    # Pagos
    payments = Payment.objects.filter(date_paid__year=year, date_paid__month=month)
    total_payments = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    count_payments = payments.count()

    # Ventas
    ventas = Venta.objects.filter(date_sold__year=year, date_sold__month=month)
    total_ventas = ventas.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    count_ventas = ventas.count()

    total = total_payments + total_ventas

    obj, created = MonthlyRevenue.objects.update_or_create(
        year=year,
        month=month,
        defaults={
            'total_amount': total,
            'payment_count': count_payments,
            'venta_total': total_ventas,
            'venta_count': count_ventas
        }
    )

    return {
        "year": year,
        "month": month,
        "total": total,
        "from_payments": total_payments,
        "from_sales": total_ventas,
        "payments_count": count_payments,
        "ventas_count": count_ventas
    }

def recalculate_all_monthly_revenue():
    from .models import Payment, Venta, MonthlyRevenue

    from django.db.models.functions import ExtractYear, ExtractMonth

    # Agrupar pagos
    payment_data = (
        Payment.objects
        .annotate(year=ExtractYear('date_paid'), month=ExtractMonth('date_paid'))
        .values('year', 'month')
        .annotate(total=Sum('amount'), count=Count('id'))
    )

    # Agrupar ventas
    venta_data = (
        Venta.objects
        .annotate(year=ExtractYear('date_sold'), month=ExtractMonth('date_sold'))
        .values('year', 'month')
        .annotate(total=Sum('total_amount'), count=Count('id'))
    )

    # Convertir a diccionarios accesibles
    pagos_map = {(d['year'], d['month']): d for d in payment_data}
    ventas_map = {(d['year'], d['month']): d for d in venta_data}

    # Combinar claves
    all_keys = set(pagos_map.keys()).union(set(ventas_map.keys()))

    results = []

    for (year, month) in sorted(all_keys, reverse=True):
        pagos = pagos_map.get((year, month), {'total': 0, 'count': 0})
        ventas = ventas_map.get((year, month), {'total': 0, 'count': 0})

        total = (pagos['total'] or 0) + (ventas['total'] or 0)

        MonthlyRevenue.objects.update_or_create(
            year=year,
            month=month,
            defaults={
                'total_amount': total,
                'payment_count': pagos['count'],
                'venta_total': ventas['total'] or 0,
                'venta_count': ventas['count']
            }
        )

        results.append({
            "year": year,
            "month": month,
            "total_amount": total,
            "payment_count": pagos['count'],
            "venta_total": ventas['total'] or 0,
            "venta_count": ventas['count']
        })

    # Resetear meses antiguos sin datos
    existing = MonthlyRevenue.objects.all()
    for entry in existing:
        if (entry.year, entry.month) not in all_keys:
            entry.total_amount = 0
            entry.payment_count = 0
            entry.venta_total = 0
            entry.venta_count = 0
            entry.save()
            results.append({
                "year": entry.year,
                "month": entry.month,
                "total_amount": 0,
                "payment_count": 0,
                "venta_total": 0,
                "venta_count": 0
            })

    return results

from decimal import Decimal
from datetime import datetime, timedelta
import pandas as pd, unicodedata

from django.db import transaction
from django.utils import timezone

from studio.models import Membership, Payment
from accounts.models import Client


def import_payments_from_excel(file_obj) -> dict:
    """
    Columnas esperadas en el Excel:
      • name          → Nombre completo (obligatorio)
      • email         → Opcional. Se usa primero para encontrar al cliente.
      • membership    → Nombre del plan (obligatorio)
      • amount        → Monto pagado (si no es numérico, se usa el precio del plan)
      • payment_date  → Fecha (o fecha-hora) del pago
    """

    # -------------------------------------------------------------------------
    def strip_accents(txt: str | None) -> str:
        if not txt:
            return ""
        return "".join(
            c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn"
        ).lower().strip()

    # ---------- leer Excel ----------
    try:
        df = pd.read_excel(file_obj)
    except Exception as e:
        return {"error": f"Error al leer el archivo: {e}"}

    required_cols = {"name", "membership", "amount", "payment_date"}
    if not required_cols.issubset(df.columns):
        return {
            "error": f"El archivo debe tener columnas: {', '.join(required_cols)}."
        }

    # ---------- catálogos ----------
    memberships = {strip_accents(m.name): m for m in Membership.objects.all()}

    all_clients = list(
        Client.objects.only("id", "first_name", "last_name", "email", "status")
    )
    clients_by_email = {c.email.lower(): c for c in all_clients if c.email}
    clients_by_name = {
        strip_accents(f"{c.first_name} {c.last_name}"): c for c in all_clients
    }

    today = timezone.now().date()
    success, failed = 0, []

    # -------------------------------------------------------------------------
    with transaction.atomic():
        for idx, row in df.iterrows():
            try:
                # -------- obtención de datos brutos --------
                name_raw = str(row.get("name", "")).strip()
                email_raw = str(row.get("email", "")).strip().lower()
                mem_raw = str(row.get("membership", "")).strip()
                amount_raw = row.get("amount")
                pay_raw = row.get("payment_date")

                # ---------- localizar cliente ----------
                client = clients_by_email.get(email_raw) if email_raw else None
                if client is None:
                    client = clients_by_name.get(strip_accents(name_raw))

                if client is None:
                    failed.append(
                        {"row": idx + 2, "error": f"Cliente no encontrado: {name_raw} / {email_raw}"}
                    )
                    continue

                # ---------- membresía ----------
                membership = memberships.get(strip_accents(mem_raw))
                if membership is None:
                    failed.append({"row": idx + 2, "error": f"Membresía no encontrada: {mem_raw}"})
                    continue

                # ---------- monto ----------
                try:
                    amount = Decimal(str(amount_raw))
                except Exception:
                    amount = membership.price

                # ---------- fecha de pago ----------
                try:
                    pay_dt = (
                        pay_raw
                        if isinstance(pay_raw, datetime)
                        else pd.to_datetime(pay_raw, dayfirst=False)
                    )
                except Exception:
                    failed.append({"row": idx + 2, "error": "Fecha de pago inválida"})
                    continue

                # ---------- vigencia ----------
                # Todos los pagos importados deben tener una vigencia de 30 días
                # a partir de la fecha de pago. Antes se asignaba la fecha del
                # mismo día cuando ``classes_per_month`` era 0 o ``None`` y eso
                # provocaba que las suscripciones caducaran inmediatamente.
                valid_until = pay_dt.date() + timedelta(days=30)

                # ---------- evitar duplicados ----------
                dup = Payment.objects.filter(
                    client=client,
                    membership=membership,
                    date_paid=pay_dt,   # incluye hora
                    amount=amount,
                ).exists()
                if dup:
                    failed.append({"row": idx + 2, "error": "Pago ya registrado"})
                    continue

                # ---------- crear pago ----------
                Payment.objects.create(
                    client=client,
                    membership=membership,
                    amount=amount,
                    date_paid=pay_dt,
                    valid_until=valid_until,
                )

                # ---------- actualizar estado del cliente ----------
                if valid_until >= today and client.status != "A":
                    client.status = "A"
                    client.save(update_fields=["status"])

                success += 1

            except Exception as exc:
                failed.append({"row": idx + 2, "error": str(exc)})

    # -------------------------------------------------------------------------
    return {
        "message": f"Pagos importados correctamente: {success}",
        "errors": failed,
    }
