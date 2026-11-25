from decimal import Decimal
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

class AssinaturaDigital(models.Model):
    """Estado da assinatura eletrônica (Autentique) do instrumento contratual."""
    class StatusAssinatura(models.TextChoices):
        NAO_ENVIADO = '', 'Não enviado'; PENDENTE = 'pendente', 'Aguardando assinatura'; ASSINADO = 'assinado', 'Assinado'; RECUSADO = 'recusado', 'Recusado'
    assinatura_id = models.CharField(max_length=80, blank=True)
    assinatura_status = models.CharField(max_length=12, choices=StatusAssinatura.choices, blank=True, default='')
    assinatura_enviada_em = models.DateTimeField(null=True, blank=True)
    assinatura_concluida_em = models.DateTimeField(null=True, blank=True)
    assinatura_link_empresa = models.URLField(blank=True)
    assinatura_sandbox = models.BooleanField(default=False)

    class Meta:
        abstract = True


class Cliente(models.Model):
    nome = models.CharField(max_length=160)
    telefone = models.CharField(max_length=20)
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.nome

class Contrato(AssinaturaDigital):
    class Origem(models.TextChoices):
        NOVO='novo','Novo'; IMPORTADO='importado','Importado em andamento'
    class Tipo(models.TextChoices):
        VENDA='venda','Venda'; TRADICIONAL='emprestimo_tradicional','Empréstimo tradicional'; JUROS='emprestimo_somente_juros','Empréstimo somente juros'
    class Status(models.TextChoices):
        ATIVO='ativo','Ativo'; ATRASADO='atrasado','Atrasado'; QUITADO='quitado','Quitado'; RENEGOCIADO='renegociado','Renegociado'; CANCELADO='cancelado','Cancelado'
    class DiaSemana(models.TextChoices):
        SEGUNDA='segunda','Segunda-feira'; TERCA='terca','Terça-feira'; QUARTA='quarta','Quarta-feira'; QUINTA='quinta','Quinta-feira'; SEXTA='sexta','Sexta-feira'; SABADO='sabado','Sábado'; DOMINGO='domingo','Domingo'
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='contratos')
    origem = models.CharField(max_length=12, choices=Origem.choices, default=Origem.NOVO)
    tipo = models.CharField(max_length=32, choices=Tipo.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ATIVO)
    data_inicio = models.DateField()
    produto = models.CharField(max_length=160, blank=True)
    valor_produto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_venda = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    teve_entrada = models.BooleanField(default=False)
    valor_entrada = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_principal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    taxa_juros_mensal = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    qtd_parcelas = models.PositiveIntegerField(null=True, blank=True)
    valor_parcela = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    periodicidade = models.CharField(max_length=16, default='mensal')
    data_primeira_parcela = models.DateField(null=True, blank=True)
    valor_juros_mensal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dia_vencimento = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)])
    dia_semana = models.CharField(max_length=7, choices=DiaSemana.choices, null=True, blank=True)
    data_quitacao_principal = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'{self.get_tipo_display()} #{self.pk}'

class Parcela(models.Model):
    class Tipo(models.TextChoices): PARCELA='parcela','Parcela'; JUROS='juros_mensal','Juros mensal'; QUITACAO='quitacao_principal','Quitação principal'
    class Status(models.TextChoices): PENDENTE='pendente','Pendente'; PAGA='paga','Paga'; ATRASADA='atrasada','Atrasada'
    class Forma(models.TextChoices): DINHEIRO='dinheiro','Dinheiro'; PIX='pix','PIX'; CARTAO='cartao','Cartão'
    contrato = models.ForeignKey(Contrato, on_delete=models.PROTECT, related_name='parcelas')
    tipo = models.CharField(max_length=24, choices=Tipo.choices, default=Tipo.PARCELA)
    numero = models.PositiveIntegerField(null=True, blank=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    data_vencimento = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)
    data_pagamento = models.DateField(null=True, blank=True)
    forma_pagamento = models.CharField(max_length=12, choices=Forma.choices, null=True, blank=True)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['contrato','numero'], name='parcela_numero_por_contrato')]
        ordering = ['data_vencimento', 'numero']

class MensagemEnviada(models.Model):
    class Tipo(models.TextChoices): ATRASO='lembrete_atraso','Lembrete atraso'; RESUMO='resumo_diario_dono','Resumo diário dono'
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='mensagens')
    parcela = models.ForeignKey(Parcela, on_delete=models.PROTECT, related_name='mensagens', null=True, blank=True)
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    enviado_em = models.DateTimeField(auto_now_add=True)
    canal = models.CharField(max_length=16, default='whatsapp')


class ContaPagar(models.Model):
    descricao = models.CharField(max_length=255)
    dia_vencimento = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)])
    ativa = models.BooleanField(default=True)
    encerrada_em = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ativa', 'dia_vencimento', 'descricao']

    def __str__(self):
        return f'{self.descricao} — todo dia {self.dia_vencimento}'
