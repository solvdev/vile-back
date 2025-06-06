from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from studio.models import Payment
from studio.management.mails.mails import send_renewal_reminder_email, send_subscription_expired_email
from django.utils import timezone
from datetime import timedelta


def run_reminder_task():
    hoy = timezone.now().date()
    target_date = hoy + timedelta(days=2)

    pagos = Payment.objects.filter(valid_until=target_date).select_related('client', 'membership')

    for pago in pagos:
        # Validar que no haya una renovación más reciente
        if Payment.objects.filter(client=pago.client, date_paid__gt=pago.date_paid, valid_until__gt=pago.valid_until).exists():
            continue
        try:
            send_renewal_reminder_email(pago.client, pago)
        except Exception as e:
            print(f"Error al enviar recordatorio a {pago.client.email}: {e}")

def run_expired_subscription_task():
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)

    expired_payments = Payment.objects.filter(valid_until=yesterday)

    for payment in expired_payments:
        # Confirmar que no haya renovado después de ese pago
        has_renewed = Payment.objects.filter(
            client=payment.client,
            date_paid__gt=payment.date_paid,
            valid_until__gt=payment.valid_until
        ).exists()

        if not has_renewed:
            try:
                send_subscription_expired_email(payment.client, payment)
                print(f"✔️ Correo de vencimiento enviado a {payment.client.email}")
            except Exception as e:
                print(f"❌ Error enviando correo de vencimiento: {e}")


def start():
    scheduler = BackgroundScheduler(timezone=timezone.get_current_timezone())
    scheduler.add_jobstore(DjangoJobStore(), "default")

    scheduler.add_job(
        run_reminder_task,
        trigger="cron",
        hour=8,
        minute=0,
        id="recordatorio_renovacion",
        replace_existing=True,
    )

    scheduler.add_job(
        run_expired_subscription_task,
        trigger="cron",
        hour=9,
        minute=0,
        id="aviso_vencimiento",
        replace_existing=True,
    )

    print("🔁 Tareas programadas: recordatorio_renovacion, aviso_vencimiento")
    scheduler.start()
