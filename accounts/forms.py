from django import forms
from .models import CustomUser, Profile

class CustomUserCreationForm(forms.ModelForm):
    """Formulaire pour la création d'un utilisateur personnalisé."""
    class Meta:
        model = CustomUser
        fields = ('email', 'password')  # Assurez-vous d'ajouter les champs nécessaires

class CustomUserChangeForm(forms.ModelForm):
    """Formulaire pour la modification d'un utilisateur personnalisé."""
    class Meta:
        model = CustomUser
        fields = ('email', 'is_active', 'is_staff', 'is_admin')


class ProfileForm(forms.ModelForm):
    """Formulaire pour la création/modification d'un profil."""
    class Meta:
        model = Profile
        fields = '__all__'
