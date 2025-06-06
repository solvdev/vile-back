from datetime import timedelta
from mailjet_rest import Client
from django.conf import settings
from django.utils import timezone
from babel.dates import format_date
from ...models import Booking
from decimal import Decimal


EXTRA_RECIPIENTS = (
    {"Email": "administracion@vilestudio.com", "Name": "Administración Vilé"},
    # puedes añadir más dicts aquí si quieres varios correos
)

def send_booking_confirmation_email(booking):
    client_obj = booking.client
    schedule = booking.schedule
    client_email = client_obj.email
    client_name = f"{client_obj.first_name} {client_obj.last_name}"
    class_date = booking.class_date
    schedule_str = schedule.get_time_slot_display()
    formatted_date = format_date(class_date, format="full", locale="es")
    class_type = schedule.class_type.name if schedule.class_type else "Pilates"

    logo_url = "https://vile-pilates.s3.us-east-2.amazonaws.com/imgs/vile.png"

    extra_info = ""
    today = timezone.now().date()

    if client_obj.active_membership:
        plan = client_obj.active_membership
        from studio.utils import count_valid_monthly_bookings

        bookings_this_month = count_valid_monthly_bookings(client_obj)

        remaining = plan.classes_per_month - bookings_this_month
        extra_info = (
            f"<p>Actualmente tienes el plan <strong>{plan.name}</strong>.<br>"
            f"Te quedan <strong>{remaining}</strong> clase(s) disponibles este mes.</p>"
        )

    elif not client_obj.trial_used:
        extra_info = "<p><strong>Esta es tu clase gratuita de prueba.</strong></p>"

    elif not client_obj.active_membership and client_obj.trial_used is True:
        extra_info = (
            "<p><strong>Debes activar tu plan.</strong></p>"
            "<p>Para poder seguir asistiendo a tus clases, por favor cancela el monto correspondiente a tu plan seleccionado.</p>"
            "<p>Si ya realizaste el pago, <strong>escríbenos por WhatsApp al <b>+502 4396 3470</b></strong> para que podamos verificarlo y activar tu plan correctamente.</p>"
        )

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f8f6f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: white; padding: 30px; border-radius: 10px;">
            <div style="text-align: center;">
                <img src="{logo_url}" alt="Vilé Pilates" style="width: 150px; margin-bottom: 20px;">
            </div>
            <h2 style="text-align: center; color: #4c5840;">¡Clase Confirmada! 💪</h2>
            <p>Hola <strong>{client_name}</strong>,</p>
            <p>Tu clase de <strong>{class_type}</strong> ha sido reservada exitosamente para el:</p>
            <p style="font-size: 18px; text-align: center; color: #4c5840;">
                <strong>{formatted_date}</strong> a las <strong>{schedule_str}</strong>
            </p>
            <p style="text-align: center;">📍 C.C. Plaza San Lucas, San Lucas Sacatepéquez</p>
            <p>Recuerda llegar con al menos 5-10 minutos de anticipación para prepararte con calma.</p>
            {extra_info}
            <hr />
            <p style="font-size: 13px; color: gray;">Este es un mensaje automático. No respondas a este correo.</p>
            <p style="font-size: 13px; color: gray;">© {timezone.now().year} Vilé Pilates Studio</p>
        </div>
    </div>
    """

    mailjet = Client(
        auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1"
    )
    data = {
        "Messages": [
            {
                "From": {
                    "Email": "no-reply@vilepilates.com",
                    "Name": "Vilé Pilates Studio",
                },
                "To": [{"Email": client_email, "Name": client_name}],
                "Bcc": EXTRA_RECIPIENTS,
                "Subject": "✨ Confirmación de tu clase en Vilé Pilates Studio ✨",
                "HTMLPart": html_content,
            }
        ]
    }

    result = mailjet.send.create(data=data)
    return result.status_code, result.json()



def send_subscription_confirmation_email(payment):
    client = payment.client
    membership = payment.membership
    valid_until = format_date(payment.valid_until, format="long", locale="es")
    client_name = f"{client.first_name} {client.last_name}"
    email = client.email
    logo_url = "https://vile-pilates.s3.us-east-2.amazonaws.com/imgs/vile.png"

    es_individual = membership.classes_per_month == 0

    asunto = (
        "🎉 ¡Disfruta tu clase individual en Vilé!"
        if es_individual
        else "🎉 ¡Gracias por suscribirte a Vilé Pilates Studio!"
    )

    mensaje_principal = (
        f"""
        <p>Hola <strong>{client_name}</strong>,</p>
        <p>Has adquirido una clase individual del plan <strong>{membership.name}</strong>.</p>
        <p>¡Esperamos que la disfrutes al máximo! 💪</p>
        """
        if es_individual
        else f"""
        <p>Hola <strong>{client_name}</strong>,</p>
        <p>Gracias por suscribirte al plan <strong>{membership.name}</strong>.</p>
        <p>Tu suscripción es válida hasta el <strong>{valid_until}</strong>.</p>
        """
    )

    mailjet = Client(
        auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1"
    )
    data = {
        "Messages": [
            {
                "From": {
                    "Email": "no-reply@vilepilates.com",
                    "Name": "Vilé Pilates Studio",
                },
                "To": [{"Email": email, "Name": client_name}],
                "Subject": asunto,
                "HTMLPart": f"""
                <div style="font-family: Arial, sans-serif; background-color: #f8f6f4; padding: 20px;">
                    <div style="max-width: 600px; margin: auto; background-color: white; padding: 30px; border-radius: 10px;">
                        <div style="text-align: center;">
                            <img src="{logo_url}" alt="Vilé Pilates" style="width: 150px; margin-bottom: 20px;">
                        </div>
                        <h2 style="text-align: center; color: #4c5840;">{asunto}</h2>
                        {mensaje_principal}
                        <p style="text-align: center;">📍 C.C. Plaza San Lucas, San Lucas Sacatepéquez</p>
                        <p>Recuerda llegar con al menos 5-10 minutos de anticipación para prepararte con calma.</p>
                        <hr />
                        <p style="font-size: 13px; color: gray;">Este es un mensaje automático. No respondas a este correo.</p>
                        <p style="font-size: 13px; color: gray;">© {timezone.now().year} Vilé Pilates Studio</p>
                    </div>
                </div>
                """,
            }
        ]
    }

    return mailjet.send.create(data=data)


from mailjet_rest import Client
from django.conf import settings
from django.utils import timezone
from babel.dates import format_date
from datetime import timedelta, datetime

from decimal import Decimal
from mailjet_rest import Client
from django.conf import settings
from django.utils import timezone
from babel.dates import format_date
from datetime import timedelta

def send_individual_booking_pending_email(booking):
    client = booking.client
    schedule = booking.schedule
    price = booking.membership.price if booking.membership else Decimal("90")
    price = price.quantize(Decimal("0.00"))
    total = price * Decimal("0.4")
    total = total.quantize(Decimal("0.00"))
    payment_deadline = booking.class_date - timedelta(days=1)
    payment_deadline_str = format_date(payment_deadline, format="full", locale="es")
    client_email = client.email
    client_name = f"{client.first_name} {client.last_name}"
    class_date = booking.class_date
    schedule_str = schedule.get_time_slot_display()
    formatted_date = format_date(class_date, format="full", locale="es")
    class_type = schedule.class_type.name if schedule.class_type else "Pilates"
    logo_url = "https://vile-pilates.s3.us-east-2.amazonaws.com/imgs/vile.png"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f8f6f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: white; padding: 30px; border-radius: 10px;">
            <div style="text-align: center;">
                <img src="{logo_url}" alt="Vilé Pilates" style="width: 150px; margin-bottom: 20px;">
            </div>
            <h2 style="text-align: center; color: #4c5840;">Reserva Pendiente</h2>
            <p>Hola <strong>{client_name}</strong>,</p>
            <p>Tu clase de <strong>{class_type}</strong> ha sido reservada para el:</p>
            <p style="font-size: 18px; text-align: center; color: #4c5840;">
                <strong>{formatted_date}</strong> a las <strong>{schedule_str}</strong>
            </p>
            <p style="text-align: center;">📍 C.C. Plaza San Lucas, San Lucas Sacatepéquez</p>
            <p>La reserva se encuentra pendiente de confirmación. Para confirmar tu reserva de clase individual, por favor realiza un depósito del Q40.00 como anticipo y envia foto del comprobante a nuestro WhatsApp al <b>+502 4396 3470</b></p>

            <hr />
            <h3 style="color: #4c5840;">Detalles de pago</h3>
            <table style="width: 100%; font-size: 15px; margin-bottom: 20px;">
                <tr>
                    <td style="padding: 8px 0;">Costo total:</td>
                    <td style="text-align: right;"><b>Q{price}</b></td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">Anticipo (40%):</td>
                    <td style="text-align: right;"><b>Q{total}</b></td>
                </tr>
                <tr><td colspan="2"><hr /></td></tr>
                <tr>
                    <td style="padding: 8px 0;">Banco:</td>
                    <td style="text-align: right;">Banco Industrial</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">Cuenta:</td>
                    <td style="text-align: right;">AHORRO GTQ-6336240</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">Referencia:</td>
                    <td style="text-align: right;"><b>{client_name}</b></td>
                </tr>
            </table>

            <p>Tu número de reservación es: <strong>{booking.id}</strong></p>
            <p>Gracias por elegir Vilé Pilates Studio. Una vez realizado el depósito, tu clase se confirmará. Tienes hasta el <strong>{payment_deadline_str}</strong> para realizar tu pago.</p>
            <hr />
            <p style="font-size: 13px; color: gray;">Este es un mensaje automático. No respondas a este correo.</p>
            <p style="font-size: 13px; color: gray;">© {timezone.now().year} Vilé Pilates Studio</p>
        </div>
    </div>
    """

    mailjet = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1")
    data = {
        "Messages": [
            {
                "From": {"Email": "no-reply@vilepilates.com", "Name": "Vilé Pilates Studio"},
                "To": [{"Email": client_email, "Name": client_name}],
                "Subject": "Tu reserva está pendiente de pago – Realiza el depósito del 40%",
                "HTMLPart": html_content,
            }
        ]
    }

    result = mailjet.send.create(data=data)
    return result.status_code, result.json()

def send_membership_cancellation_email(client):
    client_name = f"{client.first_name} {client.last_name}"
    email = client.email
    logo_url = "https://vile-pilates.s3.us-east-2.amazonaws.com/imgs/vile.png"

    # Obtener la última membresía activa del cliente (por historial de pagos)
    last_payment = client.payment_set.order_by('-date_paid').first()
    membership_name = last_payment.membership.name if last_payment and last_payment.membership else "Sin membresía registrada"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f8f6f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: white; padding: 30px; border-radius: 10px;">
            <div style="text-align: center;">
                <img src="{logo_url}" alt="Vilé Pilates" style="width: 150px; margin-bottom: 20px;">
            </div>
            <h2 style="text-align: center; color: #b12f2f;">Membresía Cancelada</h2>
            <p>Hola <strong>{client_name}</strong>,</p>
            <p>Queremos informarte que tu membresía <strong>{membership_name}</strong> ha sido cancelada.</p>
            <p>Esto puede deberse a una solicitud tuya, a un vencimiento del plan, o a una actualización de tu perfil por parte del equipo administrativo.</p>
            <p>Si consideras que esto fue un error o deseas reactivarla, escríbenos por WhatsApp al <strong>+502 4396 3470</strong>.</p>
            <p style="text-align: center;">📍 C.C. Plaza San Lucas, San Lucas Sacatepéquez</p>
            <hr />
            <p style="font-size: 13px; color: gray;">Este es un mensaje automático. No respondas a este correo.</p>
            <p style="font-size: 13px; color: gray;">© {timezone.now().year} Vilé Pilates Studio</p>
        </div>
    </div>
    """

    mailjet = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1")
    data = {
        "Messages": [
            {
                "From": {"Email": "no-reply@vilepilates.com", "Name": "Vilé Pilates Studio"},
                "To": [{"Email": email, "Name": client_name}],
                "Subject": "🚫 Cancelación de tu membresía en Vilé Pilates",
                "HTMLPart": html_content,
            }
        ]
    }

    return mailjet.send.create(data=data)

def send_renewal_reminder_email(client, payment):
    client_name = f"{client.first_name} {client.last_name}"
    email = client.email
    plan_name = payment.membership.name
    valid_until = format_date(payment.valid_until, format="long", locale="es")
    logo_url = "https://vile-pilates.s3.us-east-2.amazonaws.com/imgs/vile.png"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f8f6f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: white; padding: 30px; border-radius: 10px;">
            <div style="text-align: center;">
                <img src="{logo_url}" alt="Vilé Pilates" style="width: 150px; margin-bottom: 20px;">
            </div>
            <h2 style="text-align: center; color: #4c5840;">⏳ ¡Tu membresía está por vencer!</h2>
            <p>Hola <strong>{client_name}</strong>,</p>
            <p>Tu plan <strong>{plan_name}</strong> vencerá el <strong>{valid_until}</strong>.</p>
            <p>Si deseas seguir disfrutando de tus clases en Vilé Pilates Studio, por favor renueva tu plan antes de la fecha de vencimiento.</p>
            <p>Al renovar dentro de los 7 días siguientes, podrás mantener el mismo precio actual.</p>
            <p style="text-align: center;">📍 C.C. Plaza San Lucas, San Lucas Sacatepéquez</p>
            <hr />
            <p style="font-size: 13px; color: gray;">Este es un mensaje automático. No respondas a este correo.</p>
            <p style="font-size: 13px; color: gray;">© {timezone.now().year} Vilé Pilates Studio</p>
        </div>
    </div>
    """

    mailjet = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1")
    data = {
        "Messages": [
            {
                "From": {"Email": "no-reply@vilepilates.com", "Name": "Vilé Pilates Studio"},
                "To": [{"Email": email, "Name": client_name}],
                "Subject": "⏰ Tu membresía está por vencer – puedes renovar con el mismo precio",
                "HTMLPart": html_content,
            }
        ]
    }

    return mailjet.send.create(data=data)

def send_subscription_expired_email(client, payment):
    client_name = f"{client.first_name} {client.last_name}"
    email = client.email
    plan_name = payment.membership.name
    logo_url = "https://vile-pilates.s3.us-east-2.amazonaws.com/imgs/vile.png"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f8f6f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: white; padding: 30px; border-radius: 10px;">
            <div style="text-align: center;">
                <img src="{logo_url}" alt="Vilé Pilates" style="width: 150px; margin-bottom: 20px;">
            </div>
            <h2 style="text-align: center; color: #b12f2f;">Tu membresía ha vencido</h2>
            <p>Hola <strong>{client_name}</strong>,</p>
            <p>Tu plan <strong>{plan_name}</strong> ha vencido recientemente.</p>
            <p>Te invitamos a renovar tu membresía para seguir disfrutando de tus clases en Vilé Pilates Studio.</p>
            <p>Estamos aquí para apoyarte en tu camino de bienestar ✨.</p>
            <p style="text-align: center;">📍 C.C. Plaza San Lucas, San Lucas Sacatepéquez</p>
            <hr />
            <p style="font-size: 13px; color: gray;">Este es un mensaje automático. No respondas a este correo.</p>
            <p style="font-size: 13px; color: gray;">© {timezone.now().year} Vilé Pilates Studio</p>
        </div>
    </div>
    """

    mailjet = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1")
    data = {
        "Messages": [
            {
                "From": {"Email": "no-reply@vilepilates.com", "Name": "Vilé Pilates Studio"},
                "To": [{"Email": email, "Name": client_name}],
                "Subject": "📢 Tu membresía ha vencido – ¡Te esperamos de vuelta!",
                "HTMLPart": html_content,
            }
        ]
    }

    return mailjet.send.create(data=data)

