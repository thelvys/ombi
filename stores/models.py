import uuid
from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError 
from djmoney.models.fields import MoneyField


from groups.models import Category, ExchangeRate


class Supplier(models.Model):
    """Fournisseur de produits."""
    name = models.CharField(max_length=255, verbose_name="Nom")
    country = models.CharField(max_length=255, verbose_name="Pays")
    code = models.CharField(max_length=190, unique=True, verbose_name="Code")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    modified_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        ordering = ["-modified_at"]
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    """Emplacement de stockage des produits."""
    name = models.CharField(max_length=255, verbose_name="Nom")
    address = models.TextField(verbose_name="Adresse")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Responsable")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    modified_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        verbose_name = "Entrepôt"
        verbose_name_plural = "Entrepôts"

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    """Unité de mesure pour les articles."""
    name = models.CharField(max_length=50, unique=True, verbose_name="Nom")
    abbreviation = models.CharField(max_length=10, unique=True, verbose_name="Abréviation")

    class Meta:
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class Item(models.Model):
    """Produit stocké."""
    name = models.CharField(max_length=255, verbose_name="Nom")
    specification = models.CharField(max_length=255, verbose_name="Spécification")
    code = models.CharField(max_length=190, unique=True, verbose_name="Code")
    Category = models.ForeignKey(Category, on_delete=models.CASCADE)
    supplier = models.ManyToManyField(Supplier, verbose_name="Fournisseurs")
    unit_of_measure = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, verbose_name="Unité de mesure")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    modified_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        ordering = ["-modified_at"]
        verbose_name = "Article"
        verbose_name_plural = "Articles"

    def __str__(self):
        return self.name


class ItemUnit(models.Model):
    """Association entre un article et une unité de mesure, avec un facteur de conversion."""
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="units")
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE)
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=5, verbose_name="Facteur de conversion")
    is_base_unit = models.BooleanField(default=False, verbose_name="Unité de base")
    base_unit_quantity = models.DecimalField(max_digits=10, decimal_places=5, null=True, blank=True, verbose_name="Quantité dans l'unité de base")

    class Meta:
        unique_together = ('item', 'unit')
        verbose_name = "Unité d'article"
        verbose_name_plural = "Unités d'articles"

    def __str__(self):
        return f"{self.item} en {self.unit} (facteur: {self.conversion_factor})"
    
    def save(self, *args, **kwargs):
        # Vérifier si c'est l'unité de base
        if self.is_base_unit:
            self.base_unit_quantity = 1  # L'unité de base a un facteur de conversion de 1 par rapport à elle-même
        elif self.base_unit_quantity is None:
            # Calculer la quantité dans l'unité de base si ce n'est pas l'unité de base
            base_unit = self.item.units.get(is_base_unit=True)
            self.base_unit_quantity = self.conversion_factor * base_unit.conversion_factor

        super().save(*args, **kwargs)



class Stock(models.Model):
    """Quantité d'un produit dans un entrepôt."""
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name="Entrepôt")
    item_unit = models.ForeignKey(ItemUnit, on_delete=models.CASCADE, verbose_name="Article et unité")
    quantity = models.PositiveIntegerField(default=0, verbose_name="Quantité")

    class Meta:
        unique_together = ('warehouse', 'item_unit')
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"

    def __str__(self):
        return f"{self.quantity} {self.item_unit.unit} de {self.item_unit.item} dans {self.warehouse}"


class Order(models.Model):
    """Commande de produits auprès d'un fournisseur."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_order = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, verbose_name="Utilisateur")
    order_num = models.CharField(max_length=190, unique=True, verbose_name="Numéro de commande")
    invoice_num = models.CharField(max_length=190, unique=True, verbose_name="Numéro de facture")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="orders", verbose_name="Fournisseur")
    amount = MoneyField(max_digits=19, decimal_places=2, default_currency="USD", verbose_name="Montant")
    amount_converted = MoneyField(
        max_digits=19,
        decimal_places=2,
        default_currency="CDF",
        blank=True,
        null=True,
        verbose_name="Montant converti",
    )
    shipping_cost = MoneyField(max_digits=19, decimal_places=2, default_currency="USD", verbose_name="Frais de port")
    taxes = MoneyField(max_digits=19, decimal_places=2, default_currency="USD", verbose_name="Taxes")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    modified_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        ordering = ["-modified_at"]
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"

    def __str__(self):
        return self.order_num

    def save(self, *args, **kwargs):
        if self.amount.currency != self.currency_saved:
            try:
                exchange_rate = ExchangeRate.objects.get(
                    source_currency=self.amount.currency,
                    target_currency=self.currency_saved
                ).rate
            except ExchangeRate.DoesNotExist:
                raise ValueError(f"Aucun taux de change trouvé pour {self.amount.currency} -> {self.currency_saved}")

            self.amount_converted = self.amount.convert_to(self.currency_saved, exchange_rate)
        else:
            self.amount_converted = self.amount

        super().save(*args, **kwargs)

    @property
    def get_amount_converted(self):
        """Retourne le montant converti sous forme d'objet Money ou le montant original."""
        return self.amount_converted or self.amount
    
    @property
    def total_cost(self):
        """Calcule le coût total de la commande (articles + frais de port + taxes)."""
        item_cost = Money(0, self.amount.currency)
        for item in self.items.all():
            item_cost += item.total_price
        return item_cost + self.shipping_cost + self.taxes
    

    def get_absolute_url(self):
        return reverse("order:detail", args=[str(self.id)])


class OrderItem(models.Model):
    """Ligne d'une commande, détaille les articles commandés."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name="Commande")
    item_unit = models.ForeignKey(ItemUnit, on_delete=models.CASCADE, verbose_name="Article et unité")
    quantity = models.DecimalField(max_digits=19, decimal_places=2, verbose_name="Quantité")
    unit_price = MoneyField(max_digits=14, decimal_places=2, default_currency='USD', verbose_name="Prix unitaire")

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"

    def __str__(self):
        return f"{self.quantity} {self.item_unit.unit} de {self.item_unit.item} pour {self.order}"

    @property
    def total_price(self):
        """Calcule le prix total de la ligne de commande."""
        return self.quantity * self.unit_price



class Carrier(models.Model):
    """Entreprise ou personne qui assure le transport des marchandises."""
    name = models.CharField(max_length=255, verbose_name="Nom")
    contact_person = models.CharField(max_length=255, blank=True, verbose_name="Personne de contact")
    phone_number = models.CharField(max_length=20, blank=True, verbose_name="Numéro de téléphone")
    email = models.EmailField(blank=True, verbose_name="Adresse e-mail")

    class Meta:
        verbose_name = "Transporteur"
        verbose_name_plural = "Transporteurs"

    def __str__(self):
        return self.name




class TransportMode(models.Model):
    """Mode de transport (avion, bateau, véhicule)."""
    name = models.CharField(max_length=50, unique=True, verbose_name="Nom")
    license_plate = models.CharField(max_length=20, unique=True, verbose_name="Plaque d'immatriculation")
    model_type = models.CharField(max_length=50, verbose_name="Type de véhicule")
    carrier = models.ForeignKey(Carrier, on_delete=models.CASCADE, verbose_name="Transporteur")

    class Meta:
        verbose_name = "Mode de transport"
        verbose_name_plural = "Modes de transport"

    def __str__(self):
        return self.name


class Shipment(models.Model):
    """Expédition de produits depuis un entrepôt."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='shipments', verbose_name="Commande") 
    transport_mode = models.ForeignKey(TransportMode, on_delete=models.PROTECT, verbose_name="Mode de transport")
    origin_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='outgoing_shipments', verbose_name="Entrepôt d'origine")
    destination_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='incoming_shipments', verbose_name="Entrepôt de destination")
    shipped_at = models.DateTimeField(null=True, blank=True, verbose_name="Date d'expédition")
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT, verbose_name="Transporteur")
    tracking_number = models.CharField(max_length=100, blank=True, verbose_name="Numéro de suivi")

    class Meta:
        verbose_name = "Expédition"
        verbose_name_plural = "Expéditions"

    def __str__(self):
        return f"Expédition n°{self.id} de la commande {self.order} depuis {self.warehouse}"


class ShipmentItem(models.Model):
    """Ligne d'un envoi, détaille les articles expédiés et leur quantité."""
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='items', verbose_name="Expédition")
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, verbose_name="Ligne de commande")
    quantity = models.PositiveIntegerField(verbose_name="Quantité expédiée")

    class Meta:
        verbose_name = "Article expédié"
        verbose_name_plural = "Articles expédiés"
        unique_together = ('shipment', 'order_item')

    def __str__(self):
        return f"{self.quantity} x {self.order_item.item} dans l'expédition {self.shipment}"
    
    def save(self, *args, **kwargs):
        """Valide la quantité expédiée."""
        if self.quantity <= 0:
            raise ValueError("La quantité expédiée doit être supérieure à zéro.")

        if self.quantity > self.order_item.quantity:
            raise ValueError("La quantité expédiée ne peut pas dépasser la quantité commandée.")

        super().save(*args, **kwargs)


class ShipmentStatusUpdate(models.Model):
    """Suivi de l'état d'une expédition."""
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="status_updates", verbose_name="Expédition")
    status = models.CharField(max_length=50, verbose_name="Statut")
    location = models.CharField(max_length=255, blank=True, verbose_name="Emplacement")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Horodatage")

    class Meta:
        verbose_name = "Mise à jour du statut d'expédition"
        verbose_name_plural = "Mises à jour du statut d'expédition"

    def __str__(self):
        return f"{self.status} - {self.shipment}"



class StockTransfer(models.Model):
    """Transfert de produits entre entrepôts, nécessitant l'approbation des responsables."""
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'En attente'),
        (STATUS_APPROVED, 'Approuvé'),
        (STATUS_REJECTED, 'Rejeté'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="outgoing_transfers", verbose_name="Entrepôt source")
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="incoming_transfers", verbose_name="Entrepôt destination")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name="Article")
    quantity = models.PositiveIntegerField(verbose_name="Quantité")
    transfer_date = models.DateTimeField(auto_now_add=True, verbose_name="Date de demande")
    comments = models.TextField(blank=True, verbose_name="Commentaires")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="Statut")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Approuvé par"
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Date d'approbation")

    class Meta:
        verbose_name = "Transfert de stock"
        verbose_name_plural = "Transferts de stock"

    def __str__(self):
        return f"Transfert de {self.quantity} x {self.item} de {self.from_warehouse} vers {self.to_warehouse}"

    def clean(self):
        """Validation personnalisée du modèle."""
        if self.quantity <= 0:
            raise ValidationError("La quantité doit être supérieure à zéro.")

        if self.from_warehouse == self.to_warehouse:
            raise ValidationError("L'entrepôt source et l'entrepôt de destination ne peuvent pas être les mêmes.")

        try:
            stock = Stock.objects.get(warehouse=self.from_warehouse, item=self.item)
            if self.quantity > stock.quantity:
                raise ValidationError("La quantité à transférer dépasse le stock disponible.")
        except Stock.DoesNotExist:
            raise ValidationError(f"Aucun stock disponible pour l'article '{self.item}' dans l'entrepôt source.")

    def save(self, *args, **kwargs):
        """Logique pour mettre à jour les stocks uniquement si le transfert est approuvé."""
        if self.status == self.STATUS_APPROVED and not self.approved_at:
            self.approved_at = timezone.now()  # Enregistrez la date d'approbation

            # Mise à jour des stocks
            try:
                from_stock = Stock.objects.get(warehouse=self.from_warehouse, item=self.item)
                to_stock, created = Stock.objects.get_or_create(warehouse=self.to_warehouse, item=self.item)

                from_stock.quantity -= self.quantity
                to_stock.quantity += self.quantity

                from_stock.save()
                to_stock.save()
            except Stock.DoesNotExist:
                raise ValidationError(f"Erreur lors de la mise à jour des stocks pour l'article '{self.item}'.")

        super().save(*args, **kwargs)


class Machine(models.Model):
    """Machine utilisée dans le processus de production."""
    name = models.CharField(max_length=100, verbose_name="Nom")
    code = models.CharField(max_length=50, unique=True, verbose_name="Code")
    description = models.TextField(blank=True, verbose_name="Description")

    class Meta:
        verbose_name = "Machine"
        verbose_name_plural = "Machines"

    def __str__(self):
        return f"{self.code} - {self.name}"
    

class ProductionOrder(models.Model):
    """Ordre de production d'un produit fini."""
    order_number = models.CharField(max_length=50, unique=True, verbose_name="Numéro de l'ordre")
    product = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name="Produit fini")
    quantity = models.PositiveIntegerField(verbose_name="Quantité à produire")
    start_date = models.DateField(verbose_name="Date de début")
    due_date = models.DateField(verbose_name="Date d'échéance")
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'En attente'),
            ('in_progress', 'En cours'),
            ('completed', 'Terminé'),
            ('cancelled', 'Annulé'),
        ],
        default='pending',
        verbose_name="Statut"
    )

    class Meta:
        verbose_name = "Ordre de production"
        verbose_name_plural = "Ordres de production"

    def __str__(self):
        return f"Ordre de production {self.order_number} - {self.product}"


class BillOfMaterials(models.Model):
    """Nomenclature (BOM) définissant les composants d'un produit fini."""
    product = models.OneToOneField(Item, on_delete=models.CASCADE, related_name='bill_of_materials', verbose_name="Produit fini")

    class Meta:
        verbose_name = "Nomenclature"
        verbose_name_plural = "Nomenclatures"

    def __str__(self):
        return f"BOM pour {self.product}"


class BillOfMaterialsItem(models.Model):
    """Ligne d'une nomenclature, associant un composant et sa quantité."""
    bill_of_materials = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='items', verbose_name="Nomenclature")
    component = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name="Composant")
    quantity = models.PositiveIntegerField(verbose_name="Quantité")

    class Meta:
        verbose_name = "Ligne de nomenclature"
        verbose_name_plural = "Lignes de nomenclature"

    def __str__(self):
        return f"{self.quantity} x {self.component} pour {self.bill_of_materials.product}"



class ProductionStep(models.Model):
    """Étape de production d'un produit fini."""
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, verbose_name="Ordre de production")
    description = models.CharField(max_length=255, verbose_name="Description")
    machine = models.ForeignKey(Machine, on_delete=models.PROTECT, verbose_name="Machine")  # Nouvelle relation
    estimated_time = models.DurationField(verbose_name="Temps estimé")
    completed = models.BooleanField(default=False, verbose_name="Terminé")

    class Meta:
        verbose_name = "Étape de production"
        verbose_name_plural = "Étapes de production"

    def __str__(self):
        return f"{self.description} (sur {self.machine})"
    

class StockThreshold(models.Model):
    """Seuil de stock pour un article."""
    item = models.OneToOneField(Item, on_delete=models.CASCADE, verbose_name="Article")
    min_quantity = models.PositiveIntegerField(verbose_name="Quantité minimale")
    alert_sent = models.BooleanField(default=False, verbose_name="Alerte envoyée")

    class Meta:
        verbose_name = "Seuil de stock"
        verbose_name_plural = "Seuils de stock"

    def __str__(self):
        return f"Seuil de stock pour {self.item} : {self.min_quantity}"