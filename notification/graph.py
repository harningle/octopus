#!/usr/local/bin/python3.10
# -*- coding: utf-8 -*-

from configparser import SectionProxy

from azure.identity import DeviceCodeCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.chat_message import ChatMessage
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.models.user import User
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import \
    SendMailPostRequestBody
from msgraph.generated.users.item.teamwork.installed_apps.item.chat.chat_request_builder import \
    ChatRequestBuilder
from msgraph.generated.users.item.user_item_request_builder import UserItemRequestBuilder


class Graph:
    settings: SectionProxy
    device_code_credential: DeviceCodeCredential
    user_client: GraphServiceClient

    def __init__(self, config: SectionProxy):
        self.settings = config
        client_id = self.settings['clientId']
        tenant_id = self.settings['tenantId']
        graph_scopes = self.settings['graphUserScopes'].split(' ')

        self.device_code_credential = DeviceCodeCredential(client_id, tenant_id=tenant_id)
        self.user_client = GraphServiceClient(self.device_code_credential, graph_scopes)

    async def get_user(self) -> User:
        # Only need email address of the user
        query_params = UserItemRequestBuilder.UserItemRequestBuilderGetQueryParameters(
            select=['mail']
        )
        request_config = UserItemRequestBuilder.UserItemRequestBuilderGetRequestConfiguration(
            query_parameters=query_params
        )
        user = await self.user_client.me.get(request_configuration=request_config)
        return user

    async def get_chat(self, user_email: str, recipient: str) -> str | None:
        """
        Get chat ID with a specific recipient. Currently only support recipient with an email
        address. I.e., chat with a phone number is not supported.

        :param user_email: Your Microsoft account email used to login
        :param recipient: Chat recipient's email, e.g. "john.smith@gamil.com". If you have multiple
                          chats with the same recipient, the first one will be returned
        :return: chat ID or None if not found
        """

        # Go through all chats
        chats = await self.user_client.users.by_user_id(user_email).chats.get()
        for chat in chats.value:

            # Get all members in a chat
            query_params = ChatRequestBuilder.ChatRequestBuilderGetQueryParameters(
                expand=['members'],
            )
            request_configuration = ChatRequestBuilder.ChatRequestBuilderGetRequestConfiguration(
                query_parameters=query_params,
            )
            members = await self.user_client.chats.by_chat_id(chat.id).get(request_configuration)

            # Search for the recipient in all members
            for member in members.members:
                if member.email.lower() == recipient.lower():
                    return chat.id
        return None

    async def send_chat_message(self, chat_id: str, message: str) -> ChatMessage:
        """Send a plain text message to a chat

        :param chat_id: Chat ID
        :param message: Text message
        """

        request_body = ChatMessage(body=ItemBody(content=message))
        return await self.user_client.chats.by_chat_id(chat_id).messages.post(body=request_body)

    async def send_email(self, recipient: str, subject: str, text: str):
        """Send email to recipient(s)

        :param subject: Subject
        :param text: Main text, in HTML format
        :param recipient: Recipient's email address(es), separated by white spaces
        """

        # Parse recipient(s)
        recipients = recipient.split(' ')
        recipients = [Recipient(email_address=EmailAddress(address=i)) for i in recipients]

        # Send email
        request_body = SendMailPostRequestBody(
            message=Message(
                subject=subject,
                body=ItemBody(
                    content_type=BodyType.Html,
                    content=text
                ),
                to_recipients=recipients
            ),
            save_to_sent_items=True
        )
        await self.user_client.me.send_mail.post(body=request_body)
        pass
