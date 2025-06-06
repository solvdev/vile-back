from accounts.models import Client
from studio.models import Booking
from django.utils import timezone
from collections import defaultdict

def get_clients_with_consecutive_no_shows(limit=3):
    """
    Devuelve clientes que tienen al menos 'limit' inasistencias seguidas.
    """
    today = timezone.now().date()
    result = []

    for client in Client.objects.all():
        recent_bookings = Booking.objects.filter(
            client=client,
            class_date__lt=today,
            status='active'
        ).order_by('-class_date')[:limit]

        if recent_bookings.count() < limit:
            continue

        # Verificamos si las últimas N reservas son no_show
        if all(b.attendance_status == 'no_show' for b in recent_bookings):
            result.append(client)

    return result
