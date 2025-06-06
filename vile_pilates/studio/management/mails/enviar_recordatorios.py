from django.core.management.base import BaseCommand
from studio.models import Payment
from studio.management.mails.mails import send_renewal_reminder_email
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Envía correos de recordatorio a clientes cuyas membresías vencen pronto'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        target_date = hoy + timedelta(days=7)

        pagos = Payment.objects.filter(valid_until=target_date).select_related('client', 'membership')

        enviados = 0
        for pago in pagos:
            # Validar que no haya un pago más reciente con vigencia mayor
            tiene_renovacion = Payment.objects.filter(
                client=pago.client,
                date_paid__gt=pago.date_paid,
                valid_until__gt=pago.valid_until
            ).exists()

            if tiene_renovacion:
                continue  # ya renovó

            try:
                response = send_renewal_reminder_email(pago.client, pago)
                if response.status_code == 200:
                    enviados += 1
            except Exception as e:
                self.stderr.write(f"Error enviando a {pago.client.email}: {str(e)}")

        self.stdout.write(self.style.SUCCESS(f"Correos enviados: {enviados}"))
