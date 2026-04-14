from django.contrib import admin
from django.contrib import messages
from django import forms
from .models import GatewayIOT
from .api import check_gateway_access


class GatewayAdminForm(forms.ModelForm):
    class Meta:
        model = GatewayIOT
        fields = '__all__'
        widgets = {
            'password': forms.PasswordInput(render_value=True),
            'api_key': forms.PasswordInput(render_value=True),
        }

@admin.register(GatewayIOT)
class GatewayAdmin(admin.ModelAdmin):
    form = GatewayAdminForm
    list_display = ('name', 'url', 'auth_method', 'username')
    actions = ('check_gateway_access_action',)
    actions_on_top = True
    actions_on_bottom = True

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