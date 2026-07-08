from bson import ObjectId
from database import get_db
from services.notification_service import NotificationService

async def create_user_notification(
    tenant_id: ObjectId,
    branch_id: ObjectId,
    user_id: ObjectId,
    title: str,
    message: str,
    notification_type: str = "info"
):
    """Orchestrates in-app, SMS, WhatsApp, and push notifications for a user/patient."""
    try:
        db = get_db()
        phone_number = None
        expo_push_token = None

        # Resolve patient contact details
        patient = await db.patients.find_one({"_id": ObjectId(user_id)})
        if patient:
            phone_number = patient.get("phone")
            expo_push_token = patient.get("expo_push_token")
        else:
            # Fallback to check users collection for staff
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                phone_number = user.get("phone")
                expo_push_token = user.get("expo_push_token")

        # Dispatch via multi-channel notification service
        await NotificationService.dispatch(
            tenant_id=ObjectId(tenant_id),
            branch_id=ObjectId(branch_id),
            user_id=ObjectId(user_id),
            title=title,
            message=message,
            notification_type=notification_type,
            phone_number=phone_number,
            expo_push_token=expo_push_token
        )
    except Exception as e:
        print(f"Error in create_user_notification: {e}")
