from __future__ import annotations
import time

BUYER_EVIDENCE_TYPES={"BUYER_ELIGIBILITY","KYC_AML_ELIGIBILITY","MARKET_PARTICIPANT_ELIGIBILITY"}
COLLATERAL_EVIDENCE_TYPES={"ORDER_COLLATERAL_RESERVATION","ORDER_FUNDS_RESERVATION"}
SETTLEMENT_EVIDENCE_TYPES={"PAYMENT_SETTLEMENT_CONFIRMATION","TRADE_SETTLEMENT_CONFIRMATION"}
def _now(): return int(time.time()*1000)

class DataMarketComplianceGate:
    """Cryptographic external-evidence gate; never a substitute for legal classification."""
    def __init__(self,external_authority_verifier):
        if external_authority_verifier is None: raise ValueError("external_authority_verifier is required")
        self.verifier=external_authority_verifier
    def _verify(self,evidence:dict,*,expected_subject:str,allowed:set[str])->dict:
        package=dict(evidence or {})
        if not package: raise PermissionError("external compliance evidence required")
        verifier=self.verifier
        if hasattr(verifier,"verify"):
            ok=verifier.verify(package,expected_subject=expected_subject,allowed_evidence_types=allowed)
        else: ok=bool(verifier(package))
        if ok is not True: raise PermissionError("external compliance evidence failed cryptographic verification")
        return {"package":package,"payload":dict(package.get("payload") or {}),"authority_ref":package.get("external_authority_ref")}

    def verify_buyer(self,evidence:dict,*,buyer_entity_id:str,requirements:dict,purpose:str|None=None)->dict:
        checked=self._verify(evidence,expected_subject=buyer_entity_id,allowed=BUYER_EVIDENCE_TYPES); payload=checked["payload"]
        if payload.get("eligible") is not True: raise PermissionError("buyer eligibility attestation does not authorize participation")
        expiry=payload.get("expires_at_ms")
        if expiry is not None and int(expiry)<=_now(): raise PermissionError("buyer eligibility attestation expired")
        required_jur=str((requirements or {}).get("jurisdiction") or "").upper(); attested_jur=str(payload.get("jurisdiction") or "").upper()
        if required_jur and required_jur!=attested_jur: raise PermissionError("buyer jurisdiction requirement not satisfied")
        allowed_purposes={str(x).upper() for x in payload.get("purposes") or []}; requested=str(purpose or "").upper()
        if allowed_purposes and requested and requested not in allowed_purposes: raise PermissionError("buyer attestation does not cover requested purpose")
        return {"verified":True,"kind":"BUYER_ELIGIBILITY","authority_ref":checked["authority_ref"],
                "payload":payload,"evidence":checked["package"]}

    def verify_collateral(self,evidence:dict,*,buyer_entity_id:str,amount_minor:int,currency:str)->dict:
        checked=self._verify(evidence,expected_subject=buyer_entity_id,allowed=COLLATERAL_EVIDENCE_TYPES); payload=checked["payload"]
        amount=int(amount_minor); unit=str(currency or "").upper()
        if str(payload.get("currency") or "").upper()!=unit: raise PermissionError("collateral currency mismatch")
        if int(payload.get("reserved_amount_minor",-1))<amount: raise PermissionError("collateral reservation below maximum order notional")
        expiry=payload.get("expires_at_ms")
        if expiry is not None and int(expiry)<=_now(): raise PermissionError("collateral reservation expired")
        return {"verified":True,"kind":"ORDER_COLLATERAL","authority_ref":checked["authority_ref"],
                "payload":payload,"evidence":checked["package"]}

    def verify_settlement(self,evidence:dict,*,trade:dict)->dict:
        checked=self._verify(evidence,expected_subject=str(trade["seller_entity_id"]),allowed=SETTLEMENT_EVIDENCE_TYPES); payload=checked["payload"]
        expected_amount=int(trade["quantity"])*int(trade["price_minor"])
        pairs={"trade_id":str(trade["trade_id"]),"buyer_entity_id":str(trade["buyer_entity_id"]),
               "seller_entity_id":str(trade["seller_entity_id"]),"currency":str(trade["currency"]).upper()}
        for key,expected in pairs.items():
            if str(payload.get(key) or "").upper()!=str(expected).upper(): raise PermissionError(f"external settlement {key} mismatch")
        if int(payload.get("amount_minor",-1))!=expected_amount: raise PermissionError("external settlement amount mismatch")
        if payload.get("final") is not True: raise PermissionError("external settlement is not final")
        settlement_ref=str(payload.get("settlement_ref") or checked["authority_ref"] or "").strip()
        if not settlement_ref: raise PermissionError("external settlement reference required")
        return {"verified":True,"kind":"TRADE_SETTLEMENT","settlement_ref":settlement_ref,
                "authority_ref":checked["authority_ref"],"payload":payload,"evidence":checked["package"]}

    def status(self)->dict:
        return {"ready":True,"schema":"entity-data-market-compliance-gate-v1","legal_classification_performed":False,
                "cryptographic_external_evidence_required":True,"buyer_eligibility":True,
                "collateral_reservation":True,"external_settlement":True}
