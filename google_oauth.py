# google_oauth.py
import os
import json
from google.oauth2.credentials import Credentials

def get_credentials():
    if os.path.exists('token.json'):
        with open('token.json', 'r') as token_file:
            token_data = json.load(token_file)
            return Credentials.from_authorized_user_info(token_data)
    return None
