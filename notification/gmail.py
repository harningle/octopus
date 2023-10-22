#!/usr/local/bin/python3.10
# -*- coding: utf-8 -*-
import base64
import configparser
import os

from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow


def gmail_send(recipient: str, subject: str, body: str):
    """Create a draft email

    :param recipient: Recipient email address, separated by white space if multiple
    :param subject: Email subject
    :param body: Email body
    """

    # If we have completed the auth flow before
    scopes = ['https://www.googleapis.com/auth/gmail.compose']
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', scopes)

    # If no valid credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Init. Gmail API
    service = build('gmail', 'v1', credentials=creds)
    message = EmailMessage()
    message['To'] = recipient.replace(' ', ',')
    config = configparser.ConfigParser()
    config.read('config.cfg')
    message['From'] = config['notification']['email_sender']
    message['Subject'] = subject

    # Allow for HTML
    message.add_header('Content-Type', 'text/html')
    message.set_payload(body)
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    # Send
    service.users().messages().send(
        userId='me',
        body={'raw': encoded_message}
    ).execute()
    pass
