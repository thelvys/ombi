from django.db import models
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db.models.signals import post_save

from config import settings

from groups.models import Department

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None):
        if not email:
            raise ValueError("Enter email.")
        
        user = self.model(
            email = self.normalize_email(email)
        )
        user.set_password(password)
        user.save()
        return user
    
    def create_superuser(self, email, password=None):
        user = self.create_user(email=email, password=password)
        user.is_admin = True
        user.is_staff = True
        user.save()
        return user


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        unique=True,
        max_length=255,
        blank=False
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    objects = CustomUserManager()

    def has_perm(self, perm, obj=None):
        return True
    
    def has_module_perms(self, app_label):
        return True
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"



class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profiles")
    user_dep = models.ForeignKey(Department, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        unique_together = ['user','user_dep']
    
    def __str__(self):
        return self.user.full_name

Department.members = models.ManyToManyField(settings.AUTH_USER_MODEL, through=Profile, related_name='departments')


def post_save_receiver(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

post_save.connect(post_save_receiver, sender=settings.AUTH_USER_MODEL)