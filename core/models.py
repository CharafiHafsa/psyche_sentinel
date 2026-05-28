from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

# 1. We create a manager that knows how to create users with emails instead of usernames
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password) # This hashes the password securely!
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

# 2. We define the actual User model
class CustomUser(AbstractUser):
    username = models.CharField(max_length=150, unique=True, null=True,blank=True)
    email = models.EmailField(unique=True) # Ensure no duplicate emails

    # Tell Django to use the email field for logging in
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] 

    objects = CustomUserManager()

    def __str__(self):
        return self.email or "Admin"
    

class LDAPConfiguration(models.Model):
    server_ip = models.CharField(max_length=255, help_text="Adress IP du Domain ou du AD server")
    port = models.IntegerField(default=389, help_text="389 pour LDAP, 636 pour LDAPS")
    bind_dn = models.CharField(max_length=255, help_text="e.g., CN=Admin,OU=IT,DC=entreprise,DC=com")
    bind_password=models.CharField(max_length=255)

    base_ou = models.CharField(max_length=255, help_text="La structure du OU por la reherche")
    is_configured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"LDAP Config: {self.server_ip}"
    
class Employee(models.Model):
    sam_account_name = models.CharField(max_length=150, unique=True, help_text="Windwos Username")
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    department = models.CharField(max_length=150, blank=True, null=True)

    hrn_score = models.IntegerField(default=0, help_text="Human Risk Number")
    drill_progress = models.IntegerField(default=0, help_text="Percentage of drills completed")
    last_event = models.CharField(max_length=255, default="No events recorded")
    status = models.CharField(max_length=50, default="Clear") # Clear, Watch, Monitor, Alert

    def __str__(self):
        return self.full_name
    

class AdminConsentLog(models.Model):
    """Immutable audit trail for legal directory extraction authorization."""
    admin = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    consent_given = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consent by {self.admin.email} at {self.timestamp}"
    
    