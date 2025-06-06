from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from studio.models import Schedule, ClassType

User = get_user_model()

class Command(BaseCommand):
    help = "Popula la tabla Schedule con todos los slots válidos (sin domingos, sábados limitados) asignando coach y clase."

    def handle(self, *args, **options):
        # Obtener o crear el ClassType "Pilates Reformer"
        pilates_reformer, _ = ClassType.objects.get_or_create(
            name="Pilates Reformer",
            defaults={"description": "Clase de Pilates Reformer"}
        )
        self.stdout.write("Clase 'Pilates Reformer' lista.")

        # Obtener los coaches
        coach_jvelasco = User.objects.get(username='jvelasco')
        coach_xrivera = User.objects.get(username='xrivera')
        coach_jsamayoa = User.objects.get(username='jsamayoa')

        created_count = 0

        for day_code, day_name in Schedule.DAY_CHOICES:
            if day_code == 'SUN':
                self.stdout.write(f"⛔ Domingo omitido.")
                continue  # No crear horarios para domingo

            for time_code, time_display in Schedule.TIME_SLOTS:
                hour = int(time_code.split(':')[0])

                # Sábados: solo horarios de 07:00 a 10:00
                if day_code == 'SAT' and (hour < 7 or hour > 10):
                    continue

                # Coach según franja horaria
                if 5 <= hour <= 8:
                    coach = coach_jvelasco
                elif 9 <= hour <= 12:
                    coach = coach_xrivera
                elif 16 <= hour <= 19:
                    coach = coach_jsamayoa
                else:
                    coach = None

                if coach:
                    schedule, created = Schedule.objects.get_or_create(
                        day=day_code,
                        time_slot=time_code,
                        defaults={
                            'class_type': pilates_reformer,
                            'is_individual': False,
                            'capacity': 9,
                            'coach': coach,
                        }
                    )
                    if created:
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"✅ Creado: {day_name} {time_display} con {coach.username}"
                        ))
                    else:
                        self.stdout.write(f"➡️ Ya existe: {day_name} {time_display} con {schedule.coach.username}")
                else:
                    self.stdout.write(f"⚠️ Omitido: {day_name} {time_display} (sin coach asignado)")

        self.stdout.write(self.style.SUCCESS(f"🎉 Total de nuevos schedules creados: {created_count}"))
