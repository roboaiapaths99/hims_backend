"""
IPD Daily Bed Charge Accumulator

This service runs daily (via scheduled task or cron) to automatically add
bed charges for all currently-admitted IPD patients based on their room's
daily tariff rate.

Usage:
    Called from the /api/ipd/admin/accumulate-bed-charges endpoint
    or via a background scheduler.
"""

from bson import ObjectId
from datetime import datetime, timedelta

from database import (
    get_ipd_admissions_collection,
    get_ipd_charges_collection,
    get_rooms_collection
)


async def accumulate_daily_bed_charges() -> dict:
    """
    For every currently-admitted patient, add a daily bed charge 
    based on their room's tariff rate.
    
    Returns:
        Summary dict with counts of processed admissions and charges posted.
    """
    admissions_col = get_ipd_admissions_collection()
    charges_col = get_ipd_charges_collection()
    rooms_col = get_rooms_collection()
    
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    
    # Find all active admissions
    active_admissions = await admissions_col.find(
        {"status": "admitted"}
    ).to_list(None)
    
    processed = 0
    skipped = 0
    errors = 0
    
    for admission in active_admissions:
        try:
            admission_id = admission["_id"]
            room_id = admission.get("room_id")
            
            if not room_id:
                skipped += 1
                continue
            
            # Check if bed charge was already posted today for this admission
            existing_today = await charges_col.find_one({
                "admission_id": admission_id,
                "charge_type": "bed_charge",
                "date": {"$gte": today_start, "$lt": today_start + timedelta(days=1)}
            })
            
            if existing_today:
                skipped += 1
                continue  # Already charged today, skip
            
            # Look up room tariff
            room = await rooms_col.find_one({"_id": room_id})
            if not room:
                skipped += 1
                continue
            
            daily_rate = room.get("daily_rate", 0.0)
            if daily_rate <= 0:
                hourly_rate = room.get("hourly_rate", 0.0)
                daily_rate = hourly_rate * 24
                
            if daily_rate <= 0:
                skipped += 1
                continue
            
            room_type = room.get("room_type", "General")
            room_number = room.get("room_number", "?")
            
            # Post the daily bed charge
            charge_doc = {
                "tenant_id": admission.get("tenant_id"),
                "branch_id": admission.get("branch_id"),
                "admission_id": admission_id,
                "charge_type": "bed_charge",
                "description": f"Daily bed charge - {room_type} Room {room_number}",
                "amount": daily_rate,
                "gst_rate": 0.0,
                "date": now,
                "auto_generated": True,
                "created_at": now,
                "created_by": "system_scheduler"
            }
            
            await charges_col.insert_one(charge_doc)
            processed += 1
            
        except Exception as e:
            errors += 1
            print(f"[BED-CHARGE] Error processing admission {admission.get('_id')}: {e}")
    
    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "total_admissions": len(active_admissions),
        "run_at": now.isoformat()
    }
