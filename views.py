from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UserProfile, Product
import requests
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import os
from shopify_project import settings
from datetime import datetime
from dateutil.parser import parse
from django.core.paginator import Paginator
from django.http import HttpResponse
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import json
import traceback
import logging
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max



def get_credentials(request):
    """Load credentials from the database and refresh them if necessary."""
    user_profile = UserProfile.objects.get(user=request.user)
    creds = None

    if user_profile.google_token and user_profile.refresh_token and user_profile.token_expiry:
        creds = Credentials(
            token=user_profile.google_token,
            refresh_token=user_profile.refresh_token,
            token_uri=settings.GOOGLE_TOKEN_URI,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET
        )

        # Check if the credentials are expired and refresh them if needed
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Update the stored tokens
                user_profile.google_token = creds.token
                user_profile.refresh_token = creds.refresh_token
                user_profile.token_expiry = creds.expiry
                user_profile.save()
            except RefreshError as e:
                print(f"Error refreshing token: {e}")
                creds = None

    return creds


def home(request):
    return render(request, 'home.html')


def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            user_profile = UserProfile.objects.get(user=user)
            
            if user_profile.shopify_shop_name and user_profile.access_token:
                if validate_shopify_credentials(user_profile.shopify_shop_name, user_profile.access_token):
                    if user_profile.google_sheet_id:
                        return redirect('fetch_data')
                    else:
                        return redirect('google_connect')
                else:
                    messages.error(request, 'Stored Shopify details are invalid. Please enter valid details.')
            return redirect('welcome')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            login(request, user)
            return redirect('welcome')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})


@login_required
def user_logout(request):
    logout(request)
    return redirect('home')


def validate_shopify_credentials(shop_name, access_token):
    url = f"https://{shop_name}.myshopify.com/admin/api/2024-07/products.json"
    headers = {
        'X-Shopify-Access-Token': access_token,
        'Content-Type': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers)
        return response.status_code == 200
    except requests.RequestException:
        return False


@login_required
def welcome(request):
    if request.method == 'POST':
        shopify_shop_name = request.POST.get('shopify_shop_name')
        access_token = request.POST.get('access_token')

        if validate_shopify_credentials(shopify_shop_name, access_token):
            user_profile = UserProfile.objects.get(user=request.user)
            user_profile.shopify_shop_name = shopify_shop_name
            user_profile.access_token = access_token
            user_profile.save()
            messages.success(request, 'Data is valid and saved successfully.')
            return redirect('google_connect')
        else:
            messages.error(request, 'Please enter valid Shopify details.')

    return render(request, 'welcome.html')


@login_required
def google_connect(request):
    user_profile = UserProfile.objects.get(user=request.user)

    if request.method == 'POST':
        spreadsheet_name = request.POST.get('spreadsheet_name')

        creds = get_credentials(request)  # Pass the request object here
        if not creds or not creds.valid:
            return redirect('google_auth')

        service = build('sheets', 'v4', credentials=creds)

        if not user_profile.google_sheet_id:
            spreadsheet = {
                'properties': {
                    'title': spreadsheet_name
                }
            }

            try:
                spreadsheet = service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
                spreadsheet_id = spreadsheet.get('spreadsheetId')

                user_profile.google_sheet_id = spreadsheet_id
                user_profile.save()

                column_headers = ['Product ID', 'Title', 'Description', 'Vendor', 'Product Type', 'Price', 'SKU', 'Weight', 'Image', 'Updated At']

                body = {
                    'requests': [
                        {
                            'updateCells': {
                                'start': {
                                    'sheetId': 0,
                                    'rowIndex': 0,
                                    'columnIndex': 0
                                },
                                'rows': [
                                    {
                                        'values': [{'userEnteredValue': {'stringValue': header}} for header in column_headers]
                                    }
                                ],
                                'fields': 'userEnteredValue'
                            }
                        }
                    ]
                }

                service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

                messages.success(request, 'Google Sheet created and connected successfully!')
            except Exception as e:
                error_message = f'An error occurred: {str(e)}'
                print(error_message)
                return render(request, 'google_connect.html', {'error_message': error_message})
        else:
            messages.success(request, 'Google Sheet already connected.')

        return redirect('fetch_data')

    return render(request, 'google_connect.html')


def google_auth(request):
    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "project_id": settings.GOOGLE_PROJECT_ID,
                "auth_uri": settings.GOOGLE_AUTH_URI,
                "token_uri": settings.GOOGLE_TOKEN_URI,
                "auth_provider_x509_cert_url": settings.GOOGLE_AUTH_PROVIDER_CERT_URL,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": settings.GOOGLE_REDIRECT_URIS,
                "javascript_origins": settings.GOOGLE_JAVASCRIPT_ORIGINS,
            }
        },
        scopes=settings.GOOGLE_SHEETS_SCOPES
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    request.session['state'] = state
    return redirect(authorization_url)

def oauth2callback(request):
    state = request.session.get('state')
    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "project_id": settings.GOOGLE_PROJECT_ID,
                "auth_uri": settings.GOOGLE_AUTH_URI,
                "token_uri": settings.GOOGLE_TOKEN_URI,
                "auth_provider_x509_cert_url": settings.GOOGLE_AUTH_PROVIDER_CERT_URL,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": settings.GOOGLE_REDIRECT_URIS,
                "javascript_origins": settings.GOOGLE_JAVASCRIPT_ORIGINS,
            }
        },
        scopes=settings.GOOGLE_SHEETS_SCOPES,
        state=state
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    try:
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials

        # Save credentials to the database
        user_profile = UserProfile.objects.get(user=request.user)
        user_profile.google_token = credentials.token
        user_profile.refresh_token = credentials.refresh_token
        user_profile.token_expiry = credentials.expiry
        user_profile.save()

    except Exception as e:
        error_message = f"Error during OAuth2 callback: {str(e)}"
        print(error_message)
        traceback.print_exc()
        return HttpResponse(error_message, status=500)

    return redirect('fetch_data')


@login_required
def fetch_data(request):
    user_profile = UserProfile.objects.get(user=request.user)

    if not user_profile.shopify_shop_name or not user_profile.access_token:
        return redirect('welcome')

    url = f"https://{user_profile.shopify_shop_name}.myshopify.com/admin/api/2024-07/products.json"
    headers = {
        'X-Shopify-Access-Token': user_profile.access_token,
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        products = data.get('products', [])

        for product in products:
            shopify_product_id = product.get('id')
            updated_at = parse(product.get('updated_at'))
            defaults = {
                'title': product.get('title'),
                'body_html': product.get('body_html'),
                'vendor': product.get('vendor'),
                'product_type': product.get('product_type'),
                'price': product['variants'][0]['price'] if product['variants'] else None,
                'sku': product['variants'][0]['sku'] if product['variants'] else None,
                'weight': product['variants'][0]['weight'] if product['variants'] else None,
                'image': product.get('images')[0].get('src') if product.get('images') else None,
                'updated_at': updated_at,
            }

            # Update or create the product
            product_record, created = Product.objects.update_or_create(
                user_profile=user_profile,
                shopify_product_id=shopify_product_id,
                defaults=defaults
            )

            if not created:
                if product_record.updated_at != updated_at:
                    product_record.status = 'pending'
                    product_record.save()
                else:
                    product_record.status = 'sync'
                    product_record.save()

        # Fetch products for the current user and handle sorting
        sort_by = request.GET.get('sort', 'shopify_product_id')
        valid_sort_fields = ['shopify_product_id', 'title', 'body_html', 'vendor', 'product_type', 'price', 'sku', 'weight', 'image', 'updated_at', 'status']
        if sort_by not in valid_sort_fields:
            sort_by = 'shopify_product_id'  # Default to 'shopify_product_id'

        # Query and sorting
        products_queryset = Product.objects.filter(user_profile=user_profile).order_by(sort_by)

        # Pagination
        paginator = Paginator(products_queryset, 5)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        return render(request, 'fetch_data.html', {'page_obj': page_obj})
    else:
        return render(request, 'fetch_data.html', {'error': 'Failed to fetch data from Shopify.'})



@login_required
def disconnect(request):
    user_profile = UserProfile.objects.get(user=request.user)
    user_profile.shopify_shop_name = None
    user_profile.access_token = None
    user_profile.google_sheet_id = None
    user_profile.save()
    
    messages.success(request, 'Disconnected successfully.')
    return redirect('welcome')


@login_required
def fetch_more(request):
    user_profile = UserProfile.objects.get(user=request.user)
    
    if not user_profile.shopify_shop_name or not user_profile.access_token:
        return redirect('welcome')

    headers = {
        'X-Shopify-Access-Token': user_profile.access_token,
        'Content-Type': 'application/json'
    }

    limit = 5
    params = {
        'limit': limit,
        'order': 'created_at asc'
    }

    if user_profile.last_fetched_at:
        params['created_at_min'] = user_profile.last_fetched_at.isoformat()

    url = f"https://{user_profile.shopify_shop_name}.myshopify.com/admin/api/2024-07/products.json"

    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        products_data = data.get('products', [])

        if products_data:
            for product in products_data:
                product_id = product.get('id')
                updated_at = parse(product.get('updated_at'))

                product_record, created = Product.objects.update_or_create(
                    shopify_product_id=product_id,
                    user_profile=user_profile,
                    defaults={
                        'title': product.get('title'),
                        'body_html': product.get('body_html'),
                        'vendor': product.get('vendor'),
                        'product_type': product.get('product_type'),
                        'price': product['variants'][0]['price'] if product['variants'] else None,
                        'sku': product['variants'][0]['sku'] if product['variants'] else None,
                        'weight': product['variants'][0]['weight'] if product['variants'] else None,
                        'image': product.get('images')[0].get('src') if product.get('images') else None,
                        'updated_at': updated_at,
                    }
                )

            last_fetched_product = products_data[-1]
            user_profile.last_fetched_at = parse(last_fetched_product.get('created_at'))
            user_profile.save()

            messages.success(request, f'{len(products_data)} products fetched and saved successfully.')
        else:
            messages.info(request, 'No new products to fetch.')

        return redirect('fetch_data')
    else:
        return render(request, 'fetch_data.html', {'error': 'Failed to fetch data from Shopify.'})


@login_required
def google_disconnect(request):
    user_profile = UserProfile.objects.get(user=request.user)
    
    # Clear Google Sheet ID
    user_profile.google_sheet_id = None
    
    # Optionally, clear any other Google-related credentials if needed
    token_path = settings.GOOGLE_TOKEN_PATH
    if os.path.exists(token_path):
        os.remove(token_path)
    
    user_profile.save()
    
    messages.success(request, 'Disconnected from Google successfully.')
    return redirect('home')




logger = logging.getLogger(__name__)



class CustomJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

@login_required
def save_to_google_sheet(request):
    print("Entering save_to_google_sheet function.")
    
    user_profile = UserProfile.objects.get(user=request.user)
    print(f"UserProfile fetched: {user_profile}")

    sheet_id = user_profile.google_sheet_id
    print(f"Google Sheet ID: {sheet_id}")

    if not sheet_id:
        messages.error(request, "Google Sheet ID not found.")
        print("Google Sheet ID not found, redirecting to fetch_data.")
        return redirect('fetch_data')

    creds = get_credentials(request)
    print(f"Google credentials: {creds}")

    if not creds or not creds.valid:
        messages.error(request, "Invalid Google credentials.")
        print("Invalid Google credentials, redirecting to fetch_data.")
        return redirect('fetch_data')

    service = build('sheets', 'v4', credentials=creds)
    print("Google Sheets service built successfully.")

    # Get the last processed shopify_product_id
    last_product_id = user_profile.last_product_id
    print(f"UserProfile last_product_id: {last_product_id}")

    if last_product_id:
        products = Product.objects.filter(
            user_profile=user_profile,
            status='pending',
            shopify_product_id__gt=last_product_id
        ).order_by('shopify_product_id')[:5]
    else:
        products = Product.objects.filter(
            user_profile=user_profile,
            status='pending'
        ).order_by('shopify_product_id')[:5]

    print(f"Number of products to process: {products.count()}")
    
    if not products:
        messages.info(request, "No pending products to save.")
        print("No pending products to save, redirecting to fetch_data.")
        return redirect('fetch_data')

    values = []

    for product in products:
        print(f"Processing product with Shopify Product ID: {product.shopify_product_id}")
        values.append([
            product.shopify_product_id,
            product.title,
            product.body_html,
            product.vendor,
            product.product_type,
            str(product.price),
            product.sku,
            str(product.weight) if product.weight else '',
            product.image,
            product.updated_at.isoformat()
        ])

    print(f"Values to append: {values}")

    body = {
        'values': values
    }

    try:
        # Get the last row in the sheet to determine where to append new data
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="Sheet1!A:A"  # Only checking column A to determine the last filled row
        ).execute()
        last_row = len(result.get('values', [])) + 1  # Adding 1 to get the first empty row

        print(f"Appending data starting from row: {last_row}")

        # Append data to Google Sheets starting at the determined row
        range_to_append = f'Sheet1!A{last_row}'
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=range_to_append,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()

        print(f"Google Sheets API result: {result}")

        # Update product statuses to 'sync'
        product_ids = [product.shopify_product_id for product in products]
        print(f"Product IDs to update status to 'sync': {product_ids}")

        if product_ids:
            for product_id in product_ids:
                updated_count = Product.objects.filter(
                    user_profile=user_profile,
                    shopify_product_id=product_id
                ).update(status='sync')
                print(f"Number of products updated to 'sync' for ID {product_id}: {updated_count}")

            if updated_count != len(product_ids):
                print(f"Warning: Number of products updated to 'sync' does not match the number of products processed.")
            
        # Update last_product_id in UserProfile
        max_product_id = max(product_ids)  # Get the max from the current batch
        print(f"Updating UserProfile last_product_id to: {max_product_id}")
        user_profile.last_product_id = max_product_id
        user_profile.save()

        messages.success(request, f'{result.get("updates", {}).get("updatedCells", 0)} cells updated successfully.')
        return redirect('fetch_data')

    except Exception as e:
        print(f"An error occurred: {str(e)}")

        # Ensure product_ids is defined in the exception block
        product_ids = [product.shopify_product_id for product in products] if 'product_ids' not in locals() else product_ids

        # Mark products as failed if there's an error
        Product.objects.filter(
            user_profile=user_profile,
            shopify_product_id__in=product_ids
        ).update(status='failed')

        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('fetch_data')
