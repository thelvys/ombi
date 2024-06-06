from django.db import models
from django.db.models import Sum, Q, F, Value, ExpressionWrapper, Case, When
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError
from djmoney.models.fields import MoneyField
from treebeard.mp_tree import MP_Node

from config import settings
from groups.models import ExchangeRate, CURRENCY_CHOICES
from cashflow.models import AccountTransfer, Payment  # Assurez-vous que ces modèles existent


class Account(MP_Node):
    """Plan comptable basé sur l'OHADA, avec prise en charge de plusieurs devises."""
    class_number = models.IntegerField(choices=[(i, i) for i in range(1, 10)], verbose_name="Classe")
    code = models.CharField(max_length=20, unique=True, verbose_name="Code du compte")
    name = models.CharField(max_length=100, verbose_name="Nom du compte")
    account_type = models.CharField(
        max_length=20,
        choices=[
            ('asset', 'Actif'),
            ('liability', 'Passif'),
            ('equity', 'Capitaux propres'),
            ('income', 'Revenus'),
            ('expense', 'Dépenses'),
        ],
        verbose_name="Type de compte"
    )
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='CDF', verbose_name="Devise")

    node_order_by = ['class_number', 'code']

    class Meta:
        verbose_name = "Compte"
        verbose_name_plural = "Plan comptable"

    def __str__(self):
        return f"{self.code} - {self.name} ({self.currency})"


class Period(models.Model):
    """Période comptable (exercice)."""
    name = models.CharField(max_length=50, verbose_name="Nom de l'exercice")
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(verbose_name="Date de fin")
    is_closed = models.BooleanField(default=False, verbose_name="Clôturé")

    class Meta:
        verbose_name = "Période comptable"
        verbose_name_plural = "Périodes comptables"

    def __str__(self):
        return self.name

    def close_period(self):
        """Clôture la période comptable."""
        if self.is_closed:
            raise ValidationError("La période est déjà clôturée.")
        self.is_closed = True
        self.save()
        # ... (Logique supplémentaire pour la clôture, comme le calcul des soldes de fin de période)


class Journal(models.Model):
    """Journal comptable (ex: Ventes, Achats, Banque, etc.)."""
    name = models.CharField(max_length=100, verbose_name="Nom du journal")
    code = models.CharField(max_length=10, unique=True, verbose_name="Code du journal")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='CDF', verbose_name="Devise")  # Ajout de la devise du journal

    class Meta:
        verbose_name = "Journal"
        verbose_name_plural = "Journaux"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """Transaction financière (vente, achat, paiement, etc.)."""
    date = models.DateField(verbose_name="Date")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, verbose_name="Journal")
    reference = models.CharField(max_length=50, blank=True, verbose_name="Référence")
    description = models.CharField(max_length=255, verbose_name="Description")
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Paiement")
    account_transfer = models.ForeignKey(AccountTransfer, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Transfert de compte")
    exchange_rate = models.DecimalField(max_digits=11, decimal_places=4, null=True, blank=True, verbose_name="Taux de change")

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"

    def __str__(self):
        return f"{self.date} - {self.description}"

    def clean(self):
        """Validation : la somme des débits doit être égale à la somme des crédits."""
        debit_sum = self.items.filter(is_debit=True).aggregate(Sum('amount'))['amount__sum'] or Money(0, self.journal.currency)
        credit_sum = self.items.filter(is_debit=False).aggregate(Sum('amount'))['amount__sum'] or Money(0, self.journal.currency)
        if debit_sum != credit_sum:
            raise ValidationError("La somme des débits doit être égale à la somme des crédits.")

    def save(self, *args, **kwargs):
        if not self.exchange_rate:  # Si le taux n'est pas spécifié
            try:
                self.exchange_rate = ExchangeRate.objects.filter(
                    source_currency=self.journal.currency,
                    target_currency='CDF'  # Devise de référence pour la conversion
                ).latest('date').rate
            except ExchangeRate.DoesNotExist:
                raise ValidationError("Aucun taux de change par défaut trouvé pour la devise du journal.")
        super().save(*args, **kwargs)


class TransactionItem(models.Model):
    """Ligne d'une transaction (débit/crédit)."""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='items', verbose_name="Transaction")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Compte")
    amount = MoneyField(max_digits=19, decimal_places=2, default_currency='CDF', verbose_name="Montant")
    is_debit = models.BooleanField(verbose_name="Débit")

    def __str__(self):
        return f"{self.account} - {self.amount} ({'Débit' if self.is_debit else 'Crédit'})"

    def save(self, *args, **kwargs):
        # Utilise le taux de change de la transaction si disponible, sinon le taux par défaut
        exchange_rate = self.transaction.exchange_rate if self.transaction.exchange_rate else ExchangeRate.objects.get(
            source_currency=self.amount.currency,
            target_currency=self.account.currency
        ).rate

        self.amount = self.amount.convert_to(self.account.currency, exchange_rate)
        super().save(*args, **kwargs)


def generate_trial_balance(period, currency='CDF'):
    """Génère une balance de vérification pour une période donnée."""
    accounts = Account.objects.all()
    trial_balance = []
    for account in accounts:
        debit_sum = TransactionItem.objects.filter(
            transaction__date__range=(period.start_date, period.end_date),
            account=account,
            is_debit=True
        ).aggregate(Sum('amount'))['amount__sum'] or Money(0, account.currency)

        credit_sum = TransactionItem.objects.filter(
            transaction__date__range=(period.start_date, period.end_date),
            account=account,
            is_debit=False
        ).aggregate(Sum('amount'))['amount__sum'] or Money(0, account.currency)

        balance = debit_sum - credit_sum

        # Conversion en devise choisie
        if currency != account.currency:
            try:
                exchange_rate = ExchangeRate.objects.get(
                    source_currency=account.currency,
                    target_currency=currency
                ).rate
                debit_sum = debit_sum.convert_to(currency, exchange_rate)
                credit_sum = credit_sum.convert_to(currency, exchange_rate)
                balance = balance.convert_to(currency, exchange_rate)
            except ExchangeRate.DoesNotExist:
                raise ValueError(f"Aucun taux de change trouvé pour {account.currency} -> {currency}")

        trial_balance.append({
            'account': account,
            'debit': debit_sum,
            'credit': credit_sum,
            'balance': balance,
        })
    return trial_balance


# Modèles pour les rapports OHADA
class OHADAIncomeStatement(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    # ... (Champs pour les revenus, les dépenses et le résultat net)

class OHADABalanceSheet(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    # ... (Champs pour l'actif, le passif et les capitaux propres)

# Modèles pour les rapports US GAAP
class USGAAPIncomeStatement(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    # ... (Champs pour les revenus, les dépenses et le résultat net)

class USGAAPBalanceSheet(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    # ... (Champs pour l'actif, le passif et les capitaux propres)




def generate_income_statement(period, accounting_standard='ohada', currency='CDF'):
    """Génère un compte de résultat selon la norme comptable et la devise choisies."""
    if accounting_standard == 'ohada':
        income_accounts = Account.get_tree(Q(account_type='income') | Q(class_number=7)).values('pk')  # OHADA : classe 7 pour les produits
        expense_accounts = Account.get_tree(Q(account_type='expense') | Q(class_number=6)).values('pk')  # OHADA : classe 6 pour les charges
    elif accounting_standard == 'us_gaap':
        income_accounts = Account.get_tree(account_type='income').values('pk')
        expense_accounts = Account.get_tree(account_type='expense').values('pk')
    else:
        raise ValueError("Norme comptable invalide")

    revenues = TransactionItem.objects.filter(
        transaction__date__range=(period.start_date, period.end_date),
        account__in=income_accounts,
        is_debit=False  # Les revenus sont crédités
    ).values('account__name', 'account__code').annotate(
        total=Coalesce(Sum('amount'), Value(0), output_field=MoneyField())
    )

    depenses = TransactionItem.objects.filter(
        transaction__date__range=(period.start_date, period.end_date),
        account__in=expense_accounts,
        is_debit=True  # Les dépenses sont débitées
    ).values('account__name', 'account__code').annotate(
        total=Coalesce(Sum('amount'), Value(0), output_field=MoneyField())
    )

    resultat_net = sum(r['total'] for r in revenues) - sum(d['total'] for d in depenses)

    # Conversion en devise choisie
    for item in revenues:
        item['total'] = item['total'].convert_to(currency)
    for item in depenses:
        item['total'] = item['total'].convert_to(currency)
    resultat_net = resultat_net.convert_to(currency)

    if accounting_standard == 'ohada':
        # Enregistrement des données dans OHADAIncomeStatement
        OHADAIncomeStatement.objects.create(period=period, **{
            'revenues': revenues,
            'depenses': depenses,
            'resultat_net': resultat_net,
        })
    elif accounting_standard == 'us_gaap':
        # Enregistrement des données dans USGAAPIncomeStatement
        USGAAPIncomeStatement.objects.create(period=period, **{
            'revenues': revenues,
            'depenses': depenses,
            'resultat_net': resultat_net,
        })

    return {
        'revenues': revenues,
        'depenses': depenses,
        'resultat_net': resultat_net,
    }


def generate_balance_sheet(period, accounting_standard='ohada', currency='CDF'):
    """Génère un bilan selon la norme comptable et la devise choisies."""
    if accounting_standard == 'ohada':
        asset_accounts = Account.get_tree(account_type='asset').values('pk')
        liability_accounts = Account.get_tree(account_type='liability').values('pk')
        equity_accounts = Account.get_tree(account_type='equity').values('pk')
    elif accounting_standard == 'us_gaap':
        # ... (Logique de filtrage des comptes pour US GAAP)
        pass
    else:
        raise ValueError("Norme comptable invalide")

    actif = TransactionItem.objects.filter(
        Q(transaction__date__lte=period.end_date) | Q(account__in=asset_accounts),
        is_debit=True  # Les actifs sont débités
    ).values('account__name', 'account__code').annotate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F('amount') * Case(When(transaction__date__gt=period.end_date, then=Value(-1)), default=Value(1)),
                    output_field=MoneyField()
                )
            ),
            Value(0),
            output_field=MoneyField()
        )
    )

    passif = TransactionItem.objects.filter(
        Q(transaction__date__lte=period.end_date) | Q(account__in=liability_accounts | equity_accounts),
        is_debit=False  # Le passif et les capitaux propres sont crédités
    ).values('account__name', 'account__code').annotate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F('amount') * Case(When(transaction__date__gt=period.end_date, then=Value(1)), default=Value(-1)),
                    output_field=MoneyField()
                )
            ),
            Value(0),
            output_field=MoneyField()
        )
    )

    # Conversion en devise choisie
    for item in actif:
        item['total'] = item['total'].convert_to(currency)
    for item in passif:
        item['total'] = item['total'].convert_to(currency)

    if accounting_standard == 'ohada':
        # Enregistrement des données dans OHADABalanceSheet
        OHADABalanceSheet.objects.create(period=period, **{
            'actif': actif,
            'passif': passif,
        })
    elif accounting_standard == 'us_gaap':
        # Enregistrement des données dans USGAAPBalanceSheet
        USGAAPBalanceSheet.objects.create(period=period, **{
            'actif': actif,
            'passif': passif,
        })

    return {
        'actif': actif,
        'passif': passif,
    }