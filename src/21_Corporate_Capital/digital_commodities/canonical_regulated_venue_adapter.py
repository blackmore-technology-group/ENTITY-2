from __future__ import annotations
import hashlib, json, time

def _now(): return int(time.time()*1000)
def _canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()

class AuthorizedVenueAdapter:
    """Fail-closed bridge to an externally authorized venue; ENTITY does not become the venue."""
    def __init__(self,identity,external_authority_verifier,*,submit_callback=None,cancel_callback=None,local_controller_check=None):
        if external_authority_verifier is None: raise ValueError("external_authority_verifier is required")
        self.identity=identity; self.verifier=external_authority_verifier
        self.submit_callback=submit_callback; self.cancel_callback=cancel_callback
        self.local_controller_check=local_controller_check or self._default_local
    def _default_local(self,entity_id):
        try: self.identity.load_manifest(entity_id); return True
        except Exception: return False
    def _require_local(self,entity_id):
        if not self.local_controller_check(entity_id): raise PermissionError("local delegated operator authority required")
    def _authorization(self,evidence,operator_entity_id,venue_id,jurisdiction):
        package=dict(evidence or {})
        ok=self.verifier.verify(package,expected_subject=operator_entity_id,allowed_evidence_types={"VENUE_OPERATION_AUTHORIZATION"})
        if ok is not True: raise PermissionError("venue authorization evidence failed verification")
        payload=dict(package.get("payload") or {})
        if str(payload.get("venue_id") or "")!=str(venue_id): raise PermissionError("venue authorization ID mismatch")
        if str(payload.get("jurisdiction") or "").upper()!=str(jurisdiction).upper(): raise PermissionError("venue authorization jurisdiction mismatch")
        if payload.get("active") is not True: raise PermissionError("venue authorization is not active")
        expiry=payload.get("expires_at_ms")
        if expiry is not None and int(expiry)<=_now(): raise PermissionError("venue authorization expired")
        return package
    def submit_order(self,operator_entity_id,venue_id,jurisdiction,order_envelope,authorization_evidence):
        self._require_local(operator_entity_id); auth=self._authorization(authorization_evidence,operator_entity_id,venue_id,jurisdiction)
        if self.submit_callback is None: raise RuntimeError("external venue provider is not configured")
        response=dict(self.submit_callback(dict(order_envelope)) or {})
        if not str(response.get("provider_order_ref") or "").strip(): raise RuntimeError("provider order reference required")
        receipt={"schema":"entity-external-venue-submission-v1","operator_entity_id":operator_entity_id,
                 "venue_id":str(venue_id),"jurisdiction":str(jurisdiction).upper(),
                 "provider_order_ref":str(response["provider_order_ref"]),"provider_status":str(response.get("status") or "UNKNOWN").upper(),
                 "order_sha256":hashlib.sha256(_canon(order_envelope)).hexdigest(),
                 "authorization_ref":auth.get("external_authority_ref"),"submitted_at_ms":_now(),
                 "entity_is_not_the_external_venue":True,"provider_submission_is_not_settlement":True}
        receipt["signature"]=self.identity.sign(operator_entity_id,receipt)
        return receipt

    def cancel_order(self,operator_entity_id,venue_id,jurisdiction,provider_order_ref,authorization_evidence):
        self._require_local(operator_entity_id); auth=self._authorization(authorization_evidence,operator_entity_id,venue_id,jurisdiction)
        if self.cancel_callback is None: raise RuntimeError("external venue provider cancellation is not configured")
        response=dict(self.cancel_callback(str(provider_order_ref)) or {})
        receipt={"schema":"entity-external-venue-cancel-v1","operator_entity_id":operator_entity_id,
                 "venue_id":str(venue_id),"provider_order_ref":str(provider_order_ref),
                 "provider_status":str(response.get("status") or "UNKNOWN").upper(),
                 "authorization_ref":auth.get("external_authority_ref"),"recorded_at_ms":_now(),
                 "provider_cancellation_attested":True}
        receipt["signature"]=self.identity.sign(operator_entity_id,receipt); return receipt

    def status(self):
        return {"ready":True,"schema":"entity-authorized-venue-adapter-v1",
                "provider_configured":self.submit_callback is not None,"fail_closed_without_authorization":True,
                "entity_is_not_broker_exchange_or_transfer_agent":True}
