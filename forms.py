from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile

class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')

class ShopifyDetailsForm(forms.Form):
    shopify_shop_name = forms.CharField(label='Shopify Shop Name', max_length=255)
    access_token = forms.CharField(label='Access Token', max_length=255, widget=forms.PasswordInput)
