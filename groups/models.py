from django.db import models
from django.utils.translation import gettext_lazy as _
from treebeard.mp_tree import MP_Node

from config import settings


class Department(MP_Node):
    name = models.CharField(_("Nom"), max_length=255, unique=True)
    description = models.TextField(_("Description"), blank=True)
    supervisor = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="departments", verbose_name=_("Superviseur"))

    node_order_by = ['name']  # Trier les départements par nom

    def __str__(self):
        return self.name


class Category(MP_Node):
    name = models.CharField(_("Nom"), max_length=255)

    node_order_by = ['name'] 

    def __str__(self):
        return self.name
    
CURRENCY_CHOICES = [
    ('USD', _('US Dollar')),
    ('EUR', _('Euro')),
    ('CDF', _('Franc Congolais')),
    # Ajoutez d'autres devises selon vos besoins
]

class ExchangeRate(models.Model):
    """Modèle pour stocker les taux de change."""
    source_currency = models.CharField(_("Devise source"), max_length=3, choices=CURRENCY_CHOICES)
    target_currency = models.CharField(_("Devise cible"), max_length=3, choices=CURRENCY_CHOICES)
    rate = models.DecimalField(_("Taux de change"), max_digits=10, decimal_places=4)
    created_at = models.DateTimeField(_("Créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Mis à jour le"), auto_now=True)  # Ajout de updated_at


    class Meta:
        unique_together = ('source_currency', 'target_currency')
        verbose_name = _("Taux de change")
        verbose_name_plural = _("Taux de change")
        constraints = [
            models.CheckConstraint(
                check=models.Q(source_currency__lt=target_currency),  # Contrainte ordre alphabétique
                name='source_lt_target'
            ),
        ]

    def __str__(self):
        return f"{self.source_currency} -> {self.target_currency} : {self.rate}"
