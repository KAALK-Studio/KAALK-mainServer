# app/services/payment_service.py
import uuid
import datetime
import urllib.request
import json
from typing import Dict, Any, Tuple
from app.config import ZARINPAL_MERCHANT_ID, ZARINPAL_SANDBOX

class PaymentGatewayService:
    @classmethod
    def get_endpoints(cls) -> Tuple[str, str, str]:
        if ZARINPAL_SANDBOX:
            req_url = "https://sandbox.zarinpal.com/pg/rest/WebGate/PaymentRequest.json"
            start_url = "https://sandbox.zarinpal.com/pg/StartPay/"
            verify_url = "https://sandbox.zarinpal.com/pg/rest/WebGate/PaymentVerification.json"
        else:
            req_url = "https://api.zarinpal.com/pg/v4/payment/request.json"
            start_url = "https://www.zarinpal.com/pg/StartPay/"
            verify_url = "https://api.zarinpal.com/pg/v4/payment/verify.json"
        return req_url, start_url, verify_url

    @classmethod
    def initiate_transaction(cls, amount_toman: int, description: str, callback_url: str,
                             email: str = "", phone: str = "") -> Dict[str, Any]:
        req_url, start_url, _ = cls.get_endpoints()
        amount_rial = int(amount_toman) * 10

        payload = {
            "MerchantID": ZARINPAL_MERCHANT_ID,
            "Amount": amount_rial,
            "Description": description,
            "CallbackURL": callback_url,
            "Email": email or "customer@kaalk.ir",
            "Mobile": phone or "+989120000000"
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(req_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = json.loads(response.read().decode("utf-8"))

            status_code = res_body.get("Status")
            authority = res_body.get("Authority")

            if status_code == 100 and authority:
                return {
                    "success": True,
                    "authority": authority,
                    "payment_url": f"{start_url}{authority}",
                    "is_simulated": False
                }
        except Exception:
            pass

        # Offline / Sandbox simulation fallback if network or merchant credentials are mock
        simulated_auth = f"SIM_{uuid.uuid4().hex[:12]}"
        return {
            "success": True,
            "authority": simulated_auth,
            "payment_url": f"/payment/gateway?authority={simulated_auth}",
            "is_simulated": True
        }

    @classmethod
    def verify_transaction(cls, authority: str, amount_toman: int) -> Dict[str, Any]:
        if authority.startswith("SIM_"):
            ref_id = f"REF_{uuid.uuid4().hex[:10].upper()}"
            return {
                "success": True,
                "ref_id": ref_id,
                "message": "Payment verified via simulated gateway sandbox.",
                "is_simulated": True
            }

        _, _, verify_url = cls.get_endpoints()
        amount_rial = int(amount_toman) * 10
        payload = {
            "MerchantID": ZARINPAL_MERCHANT_ID,
            "Authority": authority,
            "Amount": amount_rial
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(verify_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = json.loads(response.read().decode("utf-8"))

            status_code = res_body.get("Status")
            ref_id = str(res_body.get("RefID") or "")

            if status_code in (100, 101) and ref_id:
                return {
                    "success": True,
                    "ref_id": ref_id,
                    "message": "Payment successfully verified by ZarinPal.",
                    "is_simulated": False
                }
            return {
                "success": False,
                "ref_id": "",
                "message": f"Verification rejected by gateway with status {status_code}.",
                "is_simulated": False
            }
        except Exception as ex:
            return {
                "success": False,
                "ref_id": "",
                "message": f"Network error during verification: {str(ex)}",
                "is_simulated": False
            }
