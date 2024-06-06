import uuid
from django.utils import timezone
from river.models import Workflow, State, TransitionApproval
from river.models.fields import StateField
from river.signals import transition_approval_start, transition_approval_done
from django.dispatch import receiver
from django.core.mail import send_mail
from django.db import models
from django.urls import reverse
from django.conf import settings  # Importez settings directement depuis django.conf
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from river.models import Workflow, State, TransitionApproval
from river.models.fields import StateField

from groups.models import Department, Category
from stores.models import Item


class RequisitionApprovalWorkflow(Workflow):
    initial_state = State(label='Brouillon')
    shared = State(label='Partagée')  # Nouvel état pour la requête partagée
    submitted = State(label='Soumise')
    approved = State(label='Approuvée')
    rejected = State(label='Rejetée')

    initial_state.add_transition(
        TransitionApproval(
            shared,
            sources=['requester'],
            conditions=[lambda r, u: r.requester == u],  # Seule la personne qui a créé la requête peut la partager
        )
    )

    shared.add_transition(
        TransitionApproval(
            submitted,
            sources=['requester'],
            conditions=[lambda r, u: r.requester == u],  # Seule la personne qui a créé la requête peut la soumettre
        )
    )

    def get_next_approver(requisition, user):
        """Fonction pour trouver le prochain approbateur dans la hiérarchie."""
        current_approver = user
        while current_approver:
            next_approver = current_approver.reports_to
            if next_approver and next_approver.has_perm('requisition.can_approve'):
                return next_approver
            current_approver = next_approver
        return None

    submitted.add_transition(
        TransitionApproval(
            approved,
            sources=[get_next_approver],
        )
    )
    submitted.add_transition(
        TransitionApproval(
            rejected,
            sources=[get_next_approver],
        )
    )

    @receiver(transition_approval_start)
    def on_approval_start(sender, instance, transition_approval, **kwargs):
        """Envoie une notification au prochain approbateur."""
        next_approver = transition_approval.get_available_approvers(instance).first()
        if next_approver:
            send_mail(
                'Nouvelle demande à approuver',
                f'La demande {instance} nécessite votre approbation.',
                'from@example.com',  # Remplacez par votre adresse e-mail réelle
                [next_approver.email],
                fail_silently=False,
            )

    @receiver(transition_approval_done)
    def on_approval_done(sender, instance, transition_approval, **kwargs):
        """Envoie une notification au demandeur en cas d'approbation ou de rejet."""
        if transition_approval.destination_state.label == 'Approuvée':
            subject = 'Demande approuvée'
            message = f'Votre demande {instance} a été approuvée.'
        elif transition_approval.destination_state.label == 'Rejetée':
            subject = 'Demande rejetée'
            message = f'Votre demande {instance} a été rejetée.'
        else:
            return  # Pas de notification pour les autres transitions

        send_mail(
            subject,
            message,
            'from@example.com',  # Remplacez par votre adresse e-mail réelle
            [instance.requester.email],
            fail_silently=False,
        )


class Requisition(models.Model):
    """Modèle représentant une demande de fonds."""

    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_SUBMITTED, "Soumise"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, verbose_name="Demandeur")
    narration = models.CharField(max_length=250, verbose_name="Description")
    amount = MoneyField(max_digits=19, decimal_places=2, default_currency='USD', verbose_name="Montant (USD)")
    exchange_rate = models.DecimalField(max_digits=11, decimal_places=4, default=1, verbose_name="Taux de change") 
    amount_converted = MoneyField(max_digits=19, decimal_places=2, default_currency='CDF', verbose_name="Montant converti (CDF)", blank=True, null=True)
    cost_center = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, verbose_name="Centre de coût") 
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, verbose_name="Categorie") 
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT, verbose_name="Statut")
    state = StateField(workflow=RequisitionApprovalWorkflow)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    modified_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        ordering = ('-modified_at',)
        constraints = [
            models.UniqueConstraint(fields=['requester', 'narration'], name='unique_request_per_user') 
        ]
        verbose_name = "Demande de fonds"
        verbose_name_plural = "Demandes de fonds"

    def __str__(self):
        return self.narration

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_SUBMITTED and not self.amount_converted:
            self.amount_converted = self.amount * self.exchange_rate
        
        # Initialisation de l'état lors de la création de la requête
        if self.pk is None:
            self.state = self.state.workflow.initial_state

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("requisition:detail", args=[str(self.id)])
    

class RequisitionShare(models.Model):
    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name='shares', verbose_name="Demande")
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Partagé avec")
    can_approve = models.BooleanField(default=False, verbose_name="Peut approuver")

    class Meta:
        unique_together = ('requisition', 'shared_with')
        verbose_name = "Partage de demande"
        verbose_name_plural = "Partages de demande"

    def __str__(self):
        return f"Demande {self.requisition} partagée avec {self.shared_with}"
    
    def get_available_approvals(self):
        """Retourne les approbations disponibles pour cet utilisateur sur cette requête."""
        return self.requisition.get_available_approvals(self.shared_with)
    




class RequisitionDetails(models.Model):
    """Détaille les éléments d'une demande de fonds."""

    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name='items', verbose_name="Demande")
    description = models.CharField(max_length=255, verbose_name="Description")
    quantity = models.PositiveIntegerField(verbose_name="Quantité")  # Rendre la quantité obligatoire
    unit_price = MoneyField(max_digits=14, decimal_places=2, default_currency='CDF', verbose_name="Prix unitaire")
    total_price = MoneyField(max_digits=19, decimal_places=2, default_currency='CDF', verbose_name="Prix total", editable=False)  
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Article (optionnel)")

    class Meta:
        verbose_name = "Détail de la demande"
        verbose_name_plural = "Détails de la demande"

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        # Calcul automatique du prix total 
        self.total_price = self.quantity * self.unit_price 
        super().save(*args, **kwargs)

class Attachment(models.Model):
    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name='attachments', verbose_name="Demande")
    # Vous pouvez éventuellement ajouter une relation avec RequisitionDetails si nécessaire
    file = models.FileField(upload_to='requisition_attachments/', verbose_name="Fichier")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Date d'ajout")

    class Meta:
        verbose_name = "Pièce jointe"
        verbose_name_plural = "Pièces jointes"

    def __str__(self):
        return f"Pièce jointe pour la demande {self.requisition.id}"
    


"""
class Review(models.Model):
    REVIEW_PENDING = 'pending'
    REVIEW_APPROVED = 'approved'
    REVIEW_REJECTED = 'rejected'
    REVIEW_CHOICES = [
        (REVIEW_PENDING, 'En attente'),
        (REVIEW_APPROVED, 'Approuvée'),
        (REVIEW_REJECTED, 'Rejetée'),
    ]

    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name='reviews', verbose_name="Demande")
    requisition_share = models.ForeignKey(RequisitionShare, on_delete=models.CASCADE, related_name='reviews', verbose_name="Part de la demande")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Réviseur")
    level = models.PositiveIntegerField(verbose_name="Niveau d'approbation")  # Ajout du champ level
    status = models.CharField(max_length=10, choices=REVIEW_CHOICES, default=REVIEW_PENDING, verbose_name="Statut")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Date d'approbation")
    comments = models.TextField(blank=True, verbose_name="Commentaires")

    class Meta:
        unique_together = ('requisition_share', 'level')  # Assurez-vous qu'il n'y a qu'une seule review par niveau pour chaque requisition
        ordering = ['level']
        verbose_name = "Revue"
        verbose_name_plural = "Revues"

    def __str__(self):
        return f"Revue de {self.reviewer} pour {self.requisition} (Niveau {self.level})"

    def save(self, *args, **kwargs):
        if self.status == self.REVIEW_APPROVED and not self.approved_at:
            self.approved_at = timezone.now()

            # Vérifier si toutes les approbations sont terminées
            if not self.requisition.reviews.filter(status=self.REVIEW_PENDING).exists():
                self.requisition.status = Requisition.STATUS_APPROVED
                self.requisition.save()

                # Notifier le demandeur de l'approbation finale
                send_mail(
                    'Demande approuvée',
                    f'Votre demande {self.requisition} a été approuvée.',
                    'from@example.com',
                    [self.requisition.requester.email],
                    fail_silently=False,
                )
            else:
                # Notifier le prochain approbateur
                next_reviewer = self.requisition_share.get_next_reviewer()
                if next_reviewer:
                    send_mail(
                        'Nouvelle demande à approuver',
                        f'La demande {self.requisition} nécessite votre approbation.',
                        'from@example.com',
                        [next_reviewer.email],
                        fail_silently=False,
                    )
        elif self.status == self.REVIEW_REJECTED:
            self.requisition.status = Requisition.STATUS_REJECTED
            self.requisition.save()

            # Notifier le demandeur du rejet
            send_mail(
                'Demande rejetée',
                f'Votre demande {self.requisition} a été rejetée.',
                'from@example.com',
                [self.requisition.requester.email],
                fail_silently=False,
            )

        super().save(*args, **kwargs)

"""