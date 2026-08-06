from django.contrib import admin
from django.contrib import messages
from django import forms
from .models import GatewayIOT, Organization, OrganizationMembership
from .api import check_gateway_access


def _filter_by_user_organizations(queryset, request, field_name='organization'):
    user = getattr(request, 'user', None)
    if getattr(user, 'is_superuser', False):
        return queryset
    if not user or not getattr(user, 'is_authenticated', False):
        return queryset.none()
    lookup = 'memberships__user' if field_name in (None, '', 'self') else f'{field_name}__memberships__user'
    return queryset.filter(**{lookup: user}).distinct()


def _single_user_organization(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    if getattr(user, 'is_superuser', False):
        return None
    qs = Organization.objects.filter(memberships__user=user).distinct()
    return qs.first() if qs.count() == 1 else None


class GatewayAdminForm(forms.ModelForm):
    class Meta:
        model = GatewayIOT
        fields = '__all__'
        widgets = {
            'password': forms.PasswordInput(render_value=True),
            'api_key': forms.PasswordInput(render_value=True),
        }


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_by', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    inlines = [OrganizationMembershipInline]
    exclude = ('created_by',)

    def get_queryset(self, request):
        return _filter_by_user_organizations(super().get_queryset(request), request, field_name='self')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = getattr(request, 'user', None)
        super().save_model(request, obj, form, change)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('organization', 'user', 'role', 'joined_at')
    list_filter = ('organization', 'role')
    search_fields = ('organization__name', 'user__username', 'user__email')

    def get_queryset(self, request):
        return _filter_by_user_organizations(super().get_queryset(request), request)

@admin.register(GatewayIOT)
class GatewayAdmin(admin.ModelAdmin):
    form = GatewayAdminForm
    list_display = ('name', 'organization', 'created_by', 'url', 'auth_method', 'username')
    list_filter = ('organization', 'auth_method')
    actions = ('check_gateway_access_action',)
    actions_on_top = True
    actions_on_bottom = True
    exclude = ('created_by',)

    def get_queryset(self, request):
        return _filter_by_user_organizations(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.organization_id:
            obj.organization = _single_user_organization(request)
        if not obj.created_by_id:
            obj.created_by = getattr(request, 'user', None)
        super().save_model(request, obj, form, change)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions['check_gateway_access_action'] = (
            GatewayAdmin.check_gateway_access_action,
            'check_gateway_access_action',
            'Verificar acesso ao gateway',
        )
        return actions

    @admin.action(description='Verificar acesso ao gateway')
    def check_gateway_access_action(self, request, queryset):
        gateways = list(queryset)
        if not gateways:
            self.message_user(request, 'Selecione ao menos um gateway.', level=messages.WARNING)
            return

        ok_count = 0
        for gateway in gateways:
            response, status_code = check_gateway_access(None, gateway.id)
            if status_code == 200 and response.get('ok'):
                ok_count += 1
                self.message_user(
                    request,
                    f"Gateway '{gateway.name}' acessivel e autenticado.",
                    level=messages.SUCCESS,
                )
            else:
                detail = response.get('error') if isinstance(response, dict) else str(response)
                self.message_user(
                    request,
                    f"Gateway '{gateway.name}' sem acesso: {detail}",
                    level=messages.ERROR,
                )

        if ok_count == len(gateways):
            self.message_user(request, 'Todos os gateways selecionados foram validados.', level=messages.SUCCESS)