from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from core.models import AssinaturaDigital, Cliente


class Moto(models.Model):
    placa = models.CharField(max_length=8, unique=True)
    modelo = models.CharField(max_length=120)
    em_manutencao = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.placa} · {self.modelo}'


class Aluguel(AssinaturaDigital):
    moto = models.ForeignKey(Moto, on_delete=models.PROTECT, related_name='alugueis')
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    inicio = models.DateField()
    fim = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    periodicidade = models.CharField(max_length=8, choices=[('semanal', 'Semanal'), ('mensal', 'Mensal')])
    primeiro_vencimento = models.DateField()
    observacoes = models.TextField(blank=True)


class CobrancaAluguel(models.Model):
    aluguel = models.ForeignKey(Aluguel, on_delete=models.PROTECT, related_name='cobrancas')
    vencimento = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    transferida_para = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='cobrancas_transferidas')
    pago_em = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['aluguel', 'vencimento'], name='aluguel_vencimento_unico')]


class LoteAnimal(models.Model):
    identificacao = models.CharField(max_length=120, unique=True)
    especie = models.CharField(max_length=80)
    quantidade = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    data_aquisicao = models.DateField()
    valor_compra = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    encerrado = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)


class Movimento(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = 'entrada', 'Entrada'
        SAIDA = 'saida', 'Saída'

    descricao = models.CharField(max_length=255)
    categoria = models.CharField(max_length=32, choices=[
        ('alimentacao', 'Alimentação'), ('medicamentos', 'Medicamentos'),
        ('veterinario', 'Veterinário'), ('manejo', 'Manejo'), ('compra_animais', 'Compra de animais'),
        ('venda_animais', 'Venda de animais'), ('emprestimos', 'Empréstimos'),
        ('motos', 'Aluguel de motos'), ('animais', 'Criação de animais'), ('manutencao', 'Manutenção'),
        ('multa', 'Multa'), ('aluguel', 'Aluguel recebido'), ('outros', 'Outros'),
    ])
    tipo = models.CharField(max_length=7, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    data = models.DateField()
    moto = models.ForeignKey(Moto, on_delete=models.PROTECT, null=True, blank=True, related_name='movimentos')
    lote = models.ForeignKey(LoteAnimal, on_delete=models.PROTECT, null=True, blank=True, related_name='movimentos')
    cobranca = models.OneToOneField(CobrancaAluguel, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-data', '-id']
