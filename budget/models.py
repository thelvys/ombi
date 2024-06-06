import datetime
today = datetime.datetime.now()
year = today.strftime("%Y")
from django.db import models
from djmoney.models.fields import MoneyField

from groups.models import Department, Category
from requisitions.models import Requisition  # Importez le modèle Requisition


from django.db import models
from django.core.validators import MinValueValidator
from groups.models import Department, Category, CURRENCY_CHOICES

class Budget(models.Model):
    class Semaine(models.TextChoices):  # Utilisation de TextChoices pour un code plus propre
        SEMAINE1 = 'S1', 'Semaine 1'
        SEMAINE2 = 'S2', 'Semaine 2'
        SEMAINE3 = 'S3', 'Semaine 3'
        SEMAINE4 = 'S4', 'Semaine 4'
        SEMAINE5 = 'S5', 'Semaine 5'

    class Mois(models.IntegerChoices):  # Utilisation de IntegerChoices pour les numéros de mois
        JAN = 1, 'JAN'
        FEV = 2, 'FEV'
        MAR = 3, 'MAR'
        AVR = 4, 'AVR'
        MAY = 5, 'MAY'
        JUN = 6, 'JUN'
        JUL = 7, 'JUL'
        AUG = 8, 'AUG'
        SEP = 9, 'SEP'
        OCT = 10, 'OCT'
        NOV = 11, 'NOV'
        DEC = 12, 'DEC'


    bud_cat_name = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='budgets')
    bud_dep_name = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='budgets')
    week_per = models.CharField(max_length=2, choices=Semaine.choices, default=Semaine.SEMAINE1)
    month_per = models.PositiveSmallIntegerField(choices=Mois.choices, default=Mois.JAN)
    year_per = models.PositiveSmallIntegerField(default=today.year)  
    bud_amount = MoneyField(max_digits=19, decimal_places=2, default_currency='USD')  # Utilisation de MoneyField
    #currency = models.CharField(max_length=40, choices=CURRENCY_CHOICES, default='USD')
    #currency_saved = models.CharField(max_length=40, choices=CURRENCY_CHOICES, default='CDF')
    bud_rate = models.DecimalField(max_digits=11, decimal_places=4, default=1, validators=[MinValueValidator(0)])  # Permettre plus de précision et un taux non négatif
    #bud_amount_converted = models.DecimalField(max_digits=19, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['bud_cat_name', 'bud_dep_name', 'week_per', 'month_per', 'year_per']
        ordering = ['-year_per', '-month_per', '-week_per']  # Ajouter un ordre par défaut

    def save(self, *args, **kwargs):
        # Calculer le montant converti uniquement si bud_amount ou bud_rate change
        if self.pk is None or self.bud_amount != Budget.objects.get(pk=self.pk).bud_amount or self.bud_rate != Budget.objects.get(pk=self.pk).bud_rate:
            self.bud_amount_converted = self.bud_amount * self.bud_rate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bud_cat_name}, {self.bud_dep_name}, {self.get_week_per_display()}, {self.get_month_per_display()}, {self.year_per}"

