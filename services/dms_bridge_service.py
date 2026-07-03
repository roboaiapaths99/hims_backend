import httpx
import uuid
import logging
from typing import Optional, Dict, Any, Union
from config import settings

logger = logging.getLogger(__name__)

class DMSBridgeClient:
    def __init__(self):
        self.base_url = settings.DMS_API_BASE_URL.rstrip('/')
        self.timeout = float(settings.DMS_REQUEST_TIMEOUT_SECONDS)

    async def _request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> httpx.Response:
        if not settings.DMS_INTEGRATION_ENABLED:
            raise Exception("DMS Integration is disabled in configuration settings.")
            
        url = f"{self.base_url}{path}"
        req_headers = {
            "x-bridge-api-key": settings.DMS_BRIDGE_API_KEY,
            "x-source-system": "HIMS",
            "x-request-id": str(uuid.uuid4())
        }
        if headers:
            req_headers.update(headers)

        req_timeout = timeout if timeout is not None else self.timeout

        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                return await client.get(url, headers=req_headers, timeout=req_timeout, **kwargs)
            elif method.upper() == "POST":
                return await client.post(url, headers=req_headers, timeout=req_timeout, **kwargs)
            elif method.upper() == "PUT":
                return await client.put(url, headers=req_headers, timeout=req_timeout, **kwargs)
            elif method.upper() == "DELETE":
                return await client.delete(url, headers=req_headers, timeout=req_timeout, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

    async def check_health(self) -> Dict[str, Any]:
        """Call DMS health check endpoint"""
        try:
            res = await self._request("GET", "/bridge/health")
            if res.status_code == 200:
                return {
                    "success": True,
                    "reachable": True,
                    "data": res.json()
                }
            else:
                return {
                    "success": False,
                    "reachable": True,
                    "status_code": res.status_code,
                    "error": f"HTTP {res.status_code}: {res.text}"
                }
        except Exception as e:
            logger.error(f"DMS bridge health check failed: {e}")
            return {
                "success": False,
                "reachable": False,
                "error": str(e)
            }

    async def upsert_patient(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sync patient demographics to DMS"""
        try:
            res = await self._request("POST", "/bridge/patients/upsert", json=payload)
            if res.status_code in (200, 201):
                return {"success": True, "data": res.json()}
            else:
                logger.error(f"DMS patient upsert returned code {res.status_code}: {res.text}")
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.error(f"DMS patient upsert failed to connect: {e}")
            return {"success": False, "error": str(e)}

    async def upload_document(self, files: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Proxy document upload to DMS"""
        try:
            res = await self._request("POST", "/bridge/documents/upload", files=files, data=data)
            if res.status_code in (200, 201, 202):
                return {"success": True, "data": res.json()}
            else:
                logger.error(f"DMS upload proxy returned code {res.status_code}: {res.text}")
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.error(f"DMS upload proxy failed to connect: {e}")
            return {"success": False, "error": str(e)}

    async def get_preview_token(self, document_id: str, tenant_id: str, branch_id: str) -> Dict[str, Any]:
        """Request short-lived preview token or signed URL for document from DMS"""
        try:
            params = {"tenant_id": tenant_id, "branch_id": branch_id}
            res = await self._request("GET", f"/bridge/documents/{document_id}/preview-token", params=params)
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                logger.error(f"DMS preview token returned code {res.status_code}: {res.text}")
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.error(f"DMS preview token failed to connect: {e}")
            return {"success": False, "error": str(e)}

    async def verify_document(self, document_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Verify patient link or document properties in DMS"""
        try:
            res = await self._request("PUT", f"/bridge/documents/{document_id}/verify", json=payload)
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def reject_document(self, document_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Reject document in DMS"""
        try:
            res = await self._request("PUT", f"/bridge/documents/{document_id}/reject", json=payload)
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def reprocess_document(self, document_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Force reprocessing of document in DMS"""
        try:
            res = await self._request("POST", f"/bridge/documents/{document_id}/reprocess", json=payload)
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_patient_summary(self, hims_patient_id: str) -> Dict[str, Any]:
        """Fetch patient clinical summary from DMS"""
        try:
            res = await self._request("GET", f"/bridge/patients/{hims_patient_id}/summary")
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_patient_timeline(self, hims_patient_id: str) -> Dict[str, Any]:
        """Fetch patient timeline entries from DMS"""
        try:
            res = await self._request("GET", f"/bridge/patients/{hims_patient_id}/timeline")
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_patient_documents(self, hims_patient_id: str) -> Dict[str, Any]:
        """Fetch patient document metadata list from DMS"""
        try:
            res = await self._request("GET", f"/bridge/patients/{hims_patient_id}/documents")
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def search_similar_cases(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a clinical context similarity search in DMS"""
        try:
            res = await self._request("POST", "/bridge/similar-cases/search", json=payload)
            if res.status_code == 200:
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def upsert_clinical_record(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sync a finalized HIMS visit clinical record to DMS"""
        try:
            res = await self._request("POST", "/bridge/clinical-records/upsert", json=payload)
            if res.status_code in (200, 201):
                return {"success": True, "data": res.json()}
            else:
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

dms_bridge = DMSBridgeClient()
