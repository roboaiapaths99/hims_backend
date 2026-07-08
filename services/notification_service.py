from database import get_notifications_collection, get_notifications_logs_collection
from bson import ObjectId
from datetime import datetime
from config import settings
import httpx
import logging

logger = logging.getLogger("hmis.notifications")

class NotificationService:
    @staticmethod
    async def send_sms_via_metareach(phone_number: str, text: str, template_id: str = None, tenant_id: ObjectId = None, branch_id: ObjectId = None) -> bool:
        """Send an SMS via MetaReach API gateway and log status."""
        # Clean phone
        cleaned_phone = "".join(filter(str.isdigit, phone_number))
        if len(cleaned_phone) == 10:
            cleaned_phone = "91" + cleaned_phone

        status = "failed"
        response_text = ""
        error_msg = None

        # Dev bypass logging
        if settings.DEV_FAKE_SMS:
            print("\n" + "="*80)
            print(f"[DEV_FAKE_SMS] SMS Verification to {cleaned_phone}:")
            print(f"Message: {text}")
            print("="*80 + "\n", flush=True)
            status = "sent"
            response_text = "DEV_FAKE_SMS_SUCCESS"
        elif not settings.METAREACH_ENABLED:
            error_msg = "MetaReach SMS is disabled"
        elif not settings.METAREACH_API_KEY or not settings.METAREACH_API_BASE_URL:
            error_msg = "SMS gateway credentials or URL not configured"
        else:
            try:
                import urllib.parse
                encoded_message = urllib.parse.quote(text)
                
                # Construct query parameters
                url = (
                    f"{settings.METAREACH_API_BASE_URL}"
                    f"?apikey={settings.METAREACH_API_KEY}"
                    f"&senderid={settings.METAREACH_SENDER_ID}"
                    f"&number={cleaned_phone}"
                    f"&message={encoded_message}"
                    f"&format=json"
                )
                
                tid = template_id or settings.METAREACH_TEMPLATE_ID
                if tid:
                    url += f"&templateid={tid}"
                
                async with httpx.AsyncClient() as client:
                    res = await client.get(url, timeout=10.0)
                    response_text = res.text
                    if res.status_code == 200:
                        try:
                            res_json = res.json()
                            # Check for success status or code from DLT/MetaReach response
                            if res_json.get("status") == "Success" or res_json.get("code") == "011":
                                status = "sent"
                                logger.info(f"MetaReach SMS sent to {cleaned_phone} successfully.")
                            else:
                                error_msg = res_json.get("description") or f"Error Code: {res_json.get('code')}"
                        except Exception as json_err:
                            # Fallback check if response has code or success in raw text
                            if "Success" in response_text or "011" in response_text:
                                status = "sent"
                                logger.info(f"MetaReach SMS sent to {cleaned_phone} successfully (raw match).")
                            else:
                                error_msg = f"Failed to parse JSON response: {response_text}"
                    else:
                        error_msg = f"HTTP {res.status_code}: {res.text}"
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error dispatching MetaReach SMS: {e}")

        # Store to log collection
        try:
            logs_col = get_notifications_logs_collection()
            log_doc = {
                "tenant_id": tenant_id,
                "branch_id": branch_id,
                "recipient": phone_number,
                "channel": "sms",
                "template": template_id or settings.METAREACH_TEMPLATE_ID or "default",
                "status": status,
                "provider_response": response_text,
                "error": error_msg,
                "created_at": datetime.utcnow()
            }
            await logs_col.insert_one(log_doc)
        except Exception as le:
            logger.error(f"Failed to save SMS log: {le}")

        return status == "sent"

    @staticmethod
    async def create_in_app_notification(
        tenant_id: ObjectId,
        branch_id: ObjectId,
        user_id: ObjectId,
        title: str,
        message: str,
        notification_type: str = "info" # info, success, warning, error
    ) -> str:
        """Create and store an in-app notification for a specific user/staff member."""
        col = get_notifications_collection()
        
        # Ensure ObjectId conversion
        t_oid = ObjectId(tenant_id) if isinstance(tenant_id, (str, ObjectId)) else tenant_id
        b_oid = ObjectId(branch_id) if isinstance(branch_id, (str, ObjectId)) else branch_id
        u_oid = ObjectId(user_id) if isinstance(user_id, (str, ObjectId)) else user_id
        
        notification_doc = {
            "tenant_id": t_oid,
            "branch_id": b_oid,
            "user_id": u_oid,
            "title": title,
            "message": message,
            "type": notification_type,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        res = await col.insert_one(notification_doc)
        return str(res.inserted_id)

    @staticmethod
    async def send_whatsapp_notification(phone_number: str, text: str) -> bool:
        """Send a WhatsApp notification using configured URL and Token."""
        if not settings.WHATSAPP_API_URL or not settings.WHATSAPP_API_TOKEN:
            logger.info("WhatsApp configuration missing. Skipping dispatch.")
            return False
            
        try:
            # Clean phone number (keep digits only)
            cleaned_phone = "".join(filter(str.isdigit, phone_number))
            if len(cleaned_phone) == 10:
                cleaned_phone = "91" + cleaned_phone
                
            headers = {
                "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": cleaned_phone,
                "type": "text",
                "text": {"body": text}
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(settings.WHATSAPP_API_URL, json=payload, headers=headers, timeout=5.0)
                if res.status_code in [200, 201, 202]:
                    logger.info(f"WhatsApp sent to {cleaned_phone} successfully.")
                    return True
                else:
                    logger.warning(f"WhatsApp dispatch to {cleaned_phone} failed: {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Error dispatching WhatsApp to {phone_number}: {e}")
            return False

    @staticmethod
    async def send_expo_push_notification(expo_push_token: str, title: str, body: str, data: dict = None) -> bool:
        """Send a mobile push notification using Expo Push API."""
        if not expo_push_token:
            return False
            
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            if settings.EXPO_ACCESS_TOKEN:
                headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"
                
            payload = {
                "to": expo_push_token,
                "title": title,
                "body": body,
                "sound": "default"
            }
            if data:
                payload["data"] = data
                
            async with httpx.AsyncClient() as client:
                res = await client.post("https://exp.host/--/api/v2/push/send", json=payload, headers=headers, timeout=5.0)
                if res.status_code == 200:
                    logger.info(f"Expo push notification successfully queued.")
                    return True
                else:
                    logger.warning(f"Expo push request failed: {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Error dispatching Expo Push notification: {e}")
            return False

    @classmethod
    async def dispatch(
        cls,
        tenant_id: ObjectId,
        branch_id: ObjectId,
        user_id: ObjectId,
        title: str,
        message: str,
        notification_type: str = "info",
        phone_number: str = None,
        expo_push_token: str = None
    ):
        """Orchestrate multi-channel dispatch, failing gracefully."""
        # 1. In-App Notification (Primary audit record)
        try:
            await cls.create_in_app_notification(tenant_id, branch_id, user_id, title, message, notification_type)
        except Exception as e:
            logger.error(f"In-App Notification storage failure: {e}")
            
        # 2. WhatsApp Notification
        if phone_number:
            try:
                await cls.send_whatsapp_notification(phone_number, f"*{title}*\n{message}")
            except Exception as e:
                logger.error(f"WhatsApp dispatch wrapper error: {e}")
                
        # 2a. SMS via MetaReach Gateway
        if phone_number:
            try:
                await cls.send_sms_via_metareach(
                    phone_number=phone_number,
                    text=f"{title}: {message}",
                    tenant_id=tenant_id,
                    branch_id=branch_id
                )
            except Exception as e:
                logger.error(f"MetaReach SMS dispatch wrapper error: {e}")
                
        # 3. Mobile App Push Notification
        if expo_push_token:
            try:
                await cls.send_expo_push_notification(expo_push_token, title, message)
            except Exception as e:
                logger.error(f"Expo Push notification wrapper error: {e}")

        # 4. WebSocket Broadcast to active user sessions
        try:
            from services.websocket_service import RealtimeNotificationService
            await RealtimeNotificationService.emit_to_user(
                user_id=str(user_id),
                event_name="notification.received",
                payload={
                    "title": title,
                    "message": message,
                    "type": notification_type,
                    "created_at": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"WebSocket notification broadcast failure: {e}")
