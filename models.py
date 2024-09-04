from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    shopify_shop_name = models.CharField(max_length=255, blank=True, null=True)
    access_token = models.CharField(max_length=255, blank=True, null=True)
    last_fetched_at = models.DateTimeField(blank=True, null=True)  # Tracks last fetched time
    google_sheet_id = models.CharField(max_length=255, blank=True, null=True)  # Stores Google Sheet ID
    last_product_id = models.CharField(max_length=255, blank=True, null=True)  # Tracks last processed product ID
    google_token = models.CharField(max_length=255, blank=True, null=True)  # Stores Google token
    refresh_token = models.CharField(max_length=255, blank=True, null=True)  # Stores refresh token
    token_expiry = models.DateTimeField(blank=True, null=True)  # Tracks token expiry

    def __str__(self):
        return self.user.username

class Product(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    shopify_product_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    body_html = models.TextField()
    vendor = models.CharField(max_length=255, blank=True, null=True)
    product_type = models.CharField(max_length=255, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=255, blank=True, null=True)
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    image = models.URLField(max_length=500, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)  # Automatically updated when model is saved
    status = models.CharField(max_length=10, default='pending')  # Status field

    class Meta:
        unique_together = ('user_profile', 'shopify_product_id')  # Ensure uniqueness within a user profile

    def __str__(self):
        return self.title
