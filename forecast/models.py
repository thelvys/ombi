from django.db import models
from djmoney.models.fields import MoneyField
from budget.models import BudgetPeriod
from cashflow.models import CashAccount

class CashFlowForecast(models.Model):
    """Prévisions de flux de trésorerie pour une période et un compte."""
    cash_account = models.ForeignKey(CashAccount, on_delete=models.CASCADE, verbose_name="Compte")
    period = models.ForeignKey(BudgetPeriod, on_delete=models.CASCADE, verbose_name="Période")
    inflow = MoneyField(max_digits=19, decimal_places=2, default_currency='CDF', verbose_name="Entrées prévues")
    outflow = MoneyField(max_digits=19, decimal_places=2, default_currency='CDF', verbose_name="Sorties prévues")

    class Meta:
        unique_together = ('cash_account', 'period')
        verbose_name = "Prévision de trésorerie"
        verbose_name_plural = "Prévisions de trésorerie"

    def __str__(self):
        return f"Prévisions pour {self.cash_account} en {self.period}"

class ForecastItem(models.Model):
    """Ligne de prévision, détaillant un type d'entrée ou de sortie."""
    forecast = models.ForeignKey(CashFlowForecast, on_delete=models.CASCADE, related_name='items', verbose_name="Prévision")
    category = models.CharField(max_length=100, verbose_name="Catégorie")  # Ex: Ventes, Salaires, Loyer, etc.
    amount = MoneyField(max_digits=19, decimal_places=2, default_currency='CDF', verbose_name="Montant")
    is_inflow = models.BooleanField(default=True, verbose_name="Entrée")  # True pour entrée, False pour sortie

    def __str__(self):
        return f"{self.category} - {self.amount} ({'Entrée' if self.is_inflow else 'Sortie'})"
