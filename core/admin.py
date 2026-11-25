from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html

from .models import Cliente, ContaPagar, Contrato, MensagemEnviada, Parcela


admin.site.site_header = 'Gestão de Operações — Administração'
admin.site.site_title = 'Gestão de Operações'
admin.site.index_title = 'Gerenciamento do sistema'


class ContratoClienteInline(admin.TabularInline):
    model = Contrato
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ('id', 'tipo', 'produto', 'valor_contrato', 'qtd_parcelas', 'status', 'data_inicio')
    readonly_fields = fields
    ordering = ('-data_inicio', '-id')
    verbose_name_plural = 'Contratos deste cliente'

    @admin.display(description='Valor')
    def valor_contrato(self, contrato):
        return contrato.valor_venda or contrato.valor_principal or '—'

    def has_add_permission(self, request, obj=None):
        return False


class ParcelaContratoInline(admin.TabularInline):
    model = Parcela
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ('numero', 'tipo', 'valor', 'data_vencimento', 'status', 'data_pagamento', 'forma_pagamento', 'valor_pago')
    readonly_fields = fields
    ordering = ('numero', 'data_vencimento')
    verbose_name_plural = 'Parcelas deste contrato'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nome', 'telefone', 'cpf', 'quantidade_contratos', 'criado_em')
    search_fields = ('nome', 'telefone', 'cpf', 'endereco')
    list_filter = ('criado_em',)
    date_hierarchy = 'criado_em'
    ordering = ('nome',)
    inlines = (ContratoClienteInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_contratos=Count('contratos'))

    @admin.display(description='Contratos', ordering='total_contratos')
    def quantidade_contratos(self, cliente):
        return cliente.total_contratos


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente_link', 'tipo', 'produto', 'valor_contrato', 'qtd_parcelas', 'parcelas_count', 'status', 'data_inicio')
    list_display_links = ('id', 'tipo', 'produto')
    search_fields = ('=id', 'cliente__nome', 'cliente__telefone', 'cliente__cpf', 'produto', 'observacoes')
    list_filter = ('tipo', 'status', 'origem', 'periodicidade', 'teve_entrada', 'data_inicio')
    autocomplete_fields = ('cliente',)
    date_hierarchy = 'data_inicio'
    ordering = ('-data_inicio', '-id')
    list_select_related = ('cliente',)
    inlines = (ParcelaContratoInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_parcelas=Count('parcelas'))

    @admin.display(description='Cliente', ordering='cliente__nome')
    def cliente_link(self, contrato):
        url = reverse('admin:core_cliente_change', args=(contrato.cliente_id,))
        return format_html('<a href="{}">{}</a>', url, contrato.cliente.nome)

    @admin.display(description='Valor')
    def valor_contrato(self, contrato):
        return contrato.valor_venda or contrato.valor_principal or '—'

    @admin.display(description='Parcelas', ordering='total_parcelas')
    def parcelas_count(self, contrato):
        return contrato.total_parcelas


@admin.register(Parcela)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente_link', 'contrato_link', 'numero', 'tipo', 'valor', 'data_vencimento', 'status', 'data_pagamento', 'forma_pagamento')
    list_display_links = ('id', 'numero')
    search_fields = ('=id', '=contrato__id', 'contrato__cliente__nome', 'contrato__cliente__telefone', 'contrato__cliente__cpf', 'contrato__produto')
    list_filter = ('status', 'tipo', 'forma_pagamento', 'contrato__tipo', 'data_vencimento', 'data_pagamento')
    autocomplete_fields = ('contrato',)
    date_hierarchy = 'data_vencimento'
    ordering = ('-data_vencimento', '-id')
    list_select_related = ('contrato', 'contrato__cliente')

    @admin.display(description='Cliente', ordering='contrato__cliente__nome')
    def cliente_link(self, parcela):
        cliente = parcela.contrato.cliente
        url = reverse('admin:core_cliente_change', args=(cliente.pk,))
        return format_html('<a href="{}">{}</a>', url, cliente.nome)

    @admin.display(description='Contrato', ordering='contrato_id')
    def contrato_link(self, parcela):
        contrato = parcela.contrato
        url = reverse('admin:core_contrato_change', args=(contrato.pk,))
        descricao = contrato.produto or contrato.get_tipo_display()
        return format_html('<a href="{}">#{} — {}</a>', url, contrato.pk, descricao)


@admin.register(MensagemEnviada)
class MensagemEnviadaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'parcela', 'tipo', 'canal', 'enviado_em')
    search_fields = ('cliente__nome', 'cliente__telefone', '=parcela__id')
    list_filter = ('tipo', 'canal', 'enviado_em')
    autocomplete_fields = ('cliente', 'parcela')
    date_hierarchy = 'enviado_em'
    list_select_related = ('cliente', 'parcela')


@admin.register(ContaPagar)
class ContaPagarAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'dia_vencimento', 'ativa', 'encerrada_em', 'criado_em')
    search_fields = ('descricao',)
    list_filter = ('ativa', 'dia_vencimento', 'encerrada_em')
    ordering = ('-ativa', 'dia_vencimento', 'descricao')
