# accounts/models.py
from django.utils import timezone
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission


class CustomUser(AbstractUser):
    # No es necesario definir is_staff, ya que viene de AbstractUser.
    # Personalizamos los campos groups y user_permissions para evitar conflictos.
    groups = models.ManyToManyField(
        Group,
        related_name="customuser_set",
        blank=True,
        help_text="Los grupos a los que pertenece este usuario.",
        verbose_name="groups",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="customuser_set",
        blank=True,
        help_text="Permisos específicos para este usuario.",
        verbose_name="user permissions",
    )

    is_enabled = models.BooleanField(
        default=True,
        help_text="Indica si el usuario está habilitado para acceder al sistema.",
    )

    def save(self, *args, **kwargs):
        # Si is_enabled es False, forzamos is_active a False para desactivar el acceso.
        if not self.is_enabled:
            self.is_active = False
        else:
            # Opcional: Si se reactiva el usuario, aseguramos que is_active sea True.
            self.is_active = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class Client(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    dpi = models.CharField(
        max_length=15,
        unique=False,
        null=True,
        blank=True,
        help_text="DPI único para validar uso de clase gratuita",
    )
    SEX_CHOICES = [
        ("M", "Masculino"),
        ("F", "Femenino"),
        ("O", "Otro"),
    ]
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    source = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="¿Cómo nos conociste? Ej: Instagram, Recomendación, Facebook...",
    )
    STATUS_CHOICES = [
        ("A", "Activo"),
        ("I", "Inactivo"),
    ]
    status = models.CharField(
        max_length=1,
        choices=STATUS_CHOICES,
        default="I",
        help_text="A = Activo, I = Inactivo",
    )
    current_membership = models.ForeignKey(
        'studio.Membership',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Membresía asignada manualmente al cliente"
    )
    trial_used = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dpi"],
                name="unique_dpi_not_null",
                condition=~models.Q(dpi__isnull=True)
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def active_membership(self):

        from studio.models import Payment

        latest_payment = (
            Payment.objects.filter(client=self).order_by("-date_paid").first()
        )
        if latest_payment and latest_payment.valid_until >= timezone.now().date():
            return latest_payment.membership
        return None
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
