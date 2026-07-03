import sys
import os
import argparse
import asyncio
from datetime import datetime

# Ensure backend directory is in path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

# Load env
from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, '.env'))

from database import connect_to_mongo, get_patients_collection, get_dms_patient_sync_collection
from services.dms_patient_sync_service import sync_patient_to_dms
from bson import ObjectId

async def run_backfill(tenant_id: str = None, force: bool = False):
    print("Initializing database connection...")
    await connect_to_mongo()
    
    patients_col = get_patients_collection()
    sync_col = get_dms_patient_sync_collection()
    
    query = {"is_deleted": {"$ne": True}}
    if tenant_id:
        try:
            query["tenant_id"] = ObjectId(tenant_id)
        except:
            print(f"Error: Invalid tenant ID format '{tenant_id}'")
            return
            
    cursor = patients_col.find(query)
    patients = await cursor.to_list(None)
    print(f"Found {len(patients)} active patients to check.")
    
    success_count = 0
    failure_count = 0
    skipped_count = 0
    
    for patient in patients:
        p_id = patient["_id"]
        
        # Check if already synced
        if not force:
            sync_rec = await sync_col.find_one({"patient_id": p_id, "sync_status": "synced"})
            if sync_rec:
                skipped_count += 1
                continue
                
        print(f"Syncing patient MRN: {patient.get('mrn')} | Name: {patient.get('first_name')} {patient.get('last_name')}...")
        try:
            res = await sync_patient_to_dms(p_id)
            if res.get("success"):
                success_count += 1
                print(f" -> SUCCESS: DMS Patient ID is {res.get('dms_patient_id')}")
            else:
                failure_count += 1
                print(f" -> FAILED: {res.get('error')}")
        except Exception as e:
            failure_count += 1
            print(f" -> ERROR during sync: {e}")
            
    print("\n" + "="*40)
    print("BACKFILL COMPLETE SUMMARY:")
    print(f"Total processed: {len(patients)}")
    print(f"Successfully synced: {success_count}")
    print(f"Failed syncs: {failure_count}")
    print(f"Skipped (already synced): {skipped_count}")
    print("="*40 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill existing HIMS patients to DMS reference database")
    parser.add_argument("--tenant-id", type=str, help="Filter by tenant ID")
    parser.add_argument("--force", action="store_true", help="Force sync even if already synced")
    args = parser.parse_args()
    
    asyncio.run(run_backfill(tenant_id=args.tenant_id, force=args.force))
