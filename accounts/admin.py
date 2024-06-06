from django.contrib import admin
from .models import CustomUser, Profile
from .forms import CustomUserCreationForm, CustomUserChangeForm

class CustomUserAdmin(admin.ModelAdmin):
    """Interface d'administration pour le modèle CustomUser."""
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = ('email', 'is_staff', 'is_admin')
    list_filter = ('is_staff', 'is_admin')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_admin')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password', 'password2')
        }),
    )
    search_fields = ('email',)
    ordering = ('email',)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Profile)
