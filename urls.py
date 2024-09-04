# product/urls.py
from django.urls import path
from .views import home, user_login, user_logout, register, welcome, fetch_data, disconnect, fetch_more, google_auth, oauth2callback, google_connect,google_disconnect,save_to_google_sheet

urlpatterns = [
    path('', home, name='home'),
    path('login/', user_login, name='login'),
    path('logout/', user_logout, name='logout'),
    path('register/', register, name='register'),
    path('welcome/', welcome, name='welcome'),
    path('fetch_data/', fetch_data, name='fetch_data'),
    path('disconnect/', disconnect, name='disconnect'),
    path('fetch_more/', fetch_more, name='fetch_more'),
    path('google_auth/', google_auth, name='google_auth'),
    path('oauth2callback/', oauth2callback, name='oauth2callback'),
    path('google_connect/', google_connect, name='google_connect'),
    path('google_disconnect/', google_disconnect, name='google_disconnect'),
    path('save-to-google-sheet/', save_to_google_sheet, name='save_to_google_sheet'),
]
