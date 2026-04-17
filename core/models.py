from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_MEMBER, "Member"),
        (ROLE_VIEWER, "Viewer"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="organization_memberships",
        on_delete=models.CASCADE,
    )
    organization = models.ForeignKey(
        Organization,
        related_name="memberships",
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "organization")
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} - {self.organization} ({self.role})"


class GatewayIOT(models.Model):
    AUTH_METHOD_USER_PASSWORD = "user_password"
    AUTH_METHOD_API_KEY = "api_key"
    AUTH_METHOD_CHOICES = [
        (AUTH_METHOD_USER_PASSWORD, "Usuario e senha"),
        (AUTH_METHOD_API_KEY, "API Key"),
    ]

    name = models.CharField(max_length=255)
    url = models.URLField()
    auth_method = models.CharField(max_length=32, choices=AUTH_METHOD_CHOICES, default=AUTH_METHOD_USER_PASSWORD)
    username = models.CharField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=255, blank=True, null=True)
    api_key = models.CharField(max_length=512, blank=True, null=True)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def clean(self):
        if self.auth_method == self.AUTH_METHOD_USER_PASSWORD:
            if not self.username or not self.password:
                raise ValidationError("Usuario e senha sao obrigatorios para auth por login.")
        elif self.auth_method == self.AUTH_METHOD_API_KEY:
            if not self.api_key:
                raise ValidationError("API Key e obrigatoria para auth por ApiKey.")
        else:
            raise ValidationError("Metodo de autenticacao invalido.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name