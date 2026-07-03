import httpx
from config import settings
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from fastapi.encoders import jsonable_encoder

class InventoryBridgeClient:
    def __init__(self):
        self.base_url = settings.INVENTORY_API_BASE_URL.rstrip('/')
        self.headers = {
            "x-api-key": settings.INVENTORY_BRIDGE_API_KEY
        }

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        max_retries = 3
        last_exception = None
        
        # Merge headers
        headers = kwargs.pop("headers", {})
        headers.update(self.headers)
        
        # Track start time
        start_time = datetime.utcnow()
        response_data = None
        status_code = None
        error_msg = None
        success = False
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    if method.upper() == "GET":
                        res = await client.get(url, headers=headers, timeout=5.0, **kwargs)
                    elif method.upper() == "POST":
                        res = await client.post(url, headers=headers, timeout=5.0, **kwargs)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    
                    status_code = res.status_code
                    if res.status_code == 200:
                        success = True
                        try:
                            response_data = res.json()
                        except:
                            response_data = res.text
                        # Successful request -> write sync log and return response
                        await self._write_sync_log(url, method, kwargs, status_code, response_data, None, True, start_time)
                        return res
                    else:
                        error_msg = f"HTTP {res.status_code}: {res.text}"
            except Exception as e:
                last_exception = e
                error_msg = str(e)
            
            # Backoff before retrying
            await asyncio.sleep(0.5 * (attempt + 1))
            
        # Failed request -> write sync log
        await self._write_sync_log(url, method, kwargs, status_code, response_data, error_msg, False, start_time)
            
        if not success:
            if last_exception:
                raise last_exception
            raise Exception(error_msg or "Unknown error in inventory bridge call")

    async def _write_sync_log(self, url: str, method: str, kwargs: dict, status_code: Optional[int], response_data: Any, error_msg: Optional[str], success: bool, start_time: datetime):
        try:
            from database import get_inventory_sync_logs_collection
            col = get_inventory_sync_logs_collection()
            if col is not None:
                req_params = kwargs.get("params")
                req_json = kwargs.get("json")
                
                await col.insert_one({
                    "url": url,
                    "method": method,
                    "request_params": jsonable_encoder(req_params) if req_params else None,
                    "request_payload": jsonable_encoder(req_json) if req_json else None,
                    "status_code": status_code,
                    "response_data": jsonable_encoder(response_data) if response_data is not None else None,
                    "error_message": error_msg,
                    "success": success,
                    "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                    "timestamp": datetime.utcnow()
                })
        except Exception as log_err:
            print(f"Warning: Failed to log inventory sync: {log_err}")

    async def search_items(self, query: str) -> List[Dict[str, Any]]:
        try:
            res = await self._request("GET", "/api/inventory/items/search", params={"q": query})
            return res.json()
        except Exception as e:
            print(f"Error calling search_items in inventory bridge: {e}")
            return []

    async def get_item_details(self, item_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = await self._request("GET", f"/api/inventory/items/{item_id}")
            return res.json()
        except Exception as e:
            print(f"Error calling get_item_details in inventory bridge: {e}")
            return None

    async def check_stock(self, item_id: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            params = {"item_id": item_id}
            if branch_id:
                params["branch_id"] = branch_id
            res = await self._request("GET", "/api/inventory/stock/check", params=params)
            return res.json()
        except Exception as e:
            print(f"Error calling check_stock in inventory bridge: {e}")
            return {"available_stock": 0, "total_batch_stock": 0, "reserved_stock": 0}

    async def get_batches(self, item_id: str) -> List[Dict[str, Any]]:
        try:
            res = await self._request("GET", "/api/inventory/batches", params={"item_id": item_id})
            return res.json()
        except Exception as e:
            print(f"Error calling get_batches in inventory bridge: {e}")
            return []

    async def reserve_stock(self, medicine_id: str, quantity: int, warehouse_id: str, reference_id: str) -> Dict[str, Any]:
        payload = {
            "medicine_id": medicine_id,
            "quantity": quantity,
            "warehouse_id": warehouse_id,
            "reference_id": reference_id
        }
        try:
            res = await self._request("POST", "/api/inventory/stock/reserve", json=payload)
            return res.json()
        except Exception as e:
            raise Exception(f"Unable to connect to inventory service: {e}")

    async def deduct_stock(self, medicine_id: str, quantity: int, warehouse_id: str, reference_id: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "medicine_id": medicine_id,
            "quantity": quantity,
            "warehouse_id": warehouse_id,
            "reference_id": reference_id
        }
        if batch_id:
            payload["batch_id"] = batch_id
        try:
            res = await self._request("POST", "/api/inventory/stock/deduct", json=payload)
            return res.json()
        except Exception as e:
            raise Exception(f"Unable to connect to inventory service: {e}")

    async def release_stock(self, reference_id: str) -> Dict[str, Any]:
        payload = {
            "reference_id": reference_id
        }
        try:
            res = await self._request("POST", "/api/inventory/stock/release", json=payload)
            return res.json()
        except Exception as e:
            raise Exception(f"Unable to connect to inventory service: {e}")

inventory_bridge = InventoryBridgeClient()
