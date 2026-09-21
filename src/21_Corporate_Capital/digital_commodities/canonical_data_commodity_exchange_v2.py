from __future__ import annotations
from pathlib import Path
import hashlib, importlib.util, json, time

_BASE_PATH=Path(__file__).with_name("canonical_data_commodity_exchange.py")
_spec=importlib.util.spec_from_file_location("entity_data_exchange_v1_base",_BASE_PATH)
_base=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
DataCommodityExchangeBase=_base.DataCommodityExchange
_now=_base._now; _sha=_base._sha; _id=_base._id; _canon=_base._canon
ORDER_ACTIVE=_base.ORDER_ACTIVE

class DataCommodityExchangeV2(DataCommodityExchangeBase):
    """Protocol-2 exchange completion layer: evidence gates, federation, royalties and export."""
    def __init__(self,state_dir,identity,*,event_ledger=None,classifier=None,settlement_engine=None,
                 local_controller_check=None,compliance_gate=None):
        self.compliance_gate=compliance_gate
        super().__init__(state_dir,identity,event_ledger=event_ledger,classifier=classifier,
                         settlement_engine=settlement_engine,local_controller_check=local_controller_check)

    def _init_db(self):
        super()._init_db()
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS order_authority(order_id TEXT PRIMARY KEY,authority_mode TEXT NOT NULL,eligibility_json TEXT NOT NULL,collateral_json TEXT NOT NULL,remote_order_json TEXT NOT NULL,created_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS trade_royalties(trade_id TEXT PRIMARY KEY,allocation_id TEXT,plan_id TEXT,allocation_json TEXT NOT NULL,status TEXT NOT NULL,updated_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS external_settlements(trade_id TEXT PRIMARY KEY,settlement_ref TEXT UNIQUE NOT NULL,evidence_json TEXT NOT NULL,created_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS remote_manifests(entity_id TEXT PRIMARY KEY,manifest_json TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,imported_at_ms INTEGER NOT NULL)")
    def _require_tradeable(self,instrument,entity_id:str,side:str,purpose:str|None):
        now=_now()
        if instrument["status"]!="ACTIVE": raise PermissionError("instrument is not active")
        if instrument["expiry_at_ms"] is not None and int(instrument["expiry_at_ms"])<=now:
            raise PermissionError("instrument expired")
        if not bool(instrument["transferable"]): raise PermissionError("instrument is non-transferable")
        if side=="SELL" and entity_id!=instrument["issuer_entity_id"] and not bool(instrument["resale_allowed"]):
            raise PermissionError("secondary resale is not allowed")
        allowed=set(json.loads(instrument["permitted_purposes_json"] or "[]"))
        requested=str(purpose or "").upper().strip()
        if allowed and (not requested or requested not in allowed):
            raise PermissionError("trade purpose is outside instrument permissions")
        return dict(json.loads(instrument["buyer_requirements_json"] or "{}"))

    def _gate_order(self,instrument,entity_id:str,side:str,quantity:int,price:int,currency:str,purpose,
                    eligibility_evidence=None,collateral_evidence=None)->tuple[dict,dict]:
        requirements=dict(json.loads(instrument["buyer_requirements_json"] or "{}"))
        eligibility={}; collateral={}
        if side=="BUY" and requirements:
            if self.compliance_gate is None:
                raise PermissionError("buyer requirements need configured compliance gate")
            eligibility=self.compliance_gate.verify_buyer(dict(eligibility_evidence or {}),
                buyer_entity_id=entity_id,requirements=requirements,purpose=purpose)
        collateral_required=bool(requirements.get("collateral_required"))
        if side=="BUY" and collateral_required:
            if self.compliance_gate is None:
                raise PermissionError("collateral requirement needs configured compliance gate")
            collateral=self.compliance_gate.verify_collateral(dict(collateral_evidence or {}),
                buyer_entity_id=entity_id,amount_minor=int(quantity)*int(price),currency=currency)
        return eligibility,collateral
    def place_order(self,entity_id:str,market_id:str,instrument_id:str,*,side:str,quantity:int,
                    limit_price_minor:int,currency:str,order_nonce:str,time_in_force:str="GTC",
                    purpose:str|None=None,eligibility_evidence=None,collateral_evidence=None)->dict:
        with self._connect() as db:
            instrument=self._instrument(db,instrument_id)
        eligibility,collateral=self._gate_order(instrument,entity_id,str(side).upper(),int(quantity),
            int(limit_price_minor),str(currency).upper(),purpose,eligibility_evidence,collateral_evidence)
        result=super().place_order(entity_id,market_id,instrument_id,side=side,quantity=quantity,
            limit_price_minor=limit_price_minor,currency=currency,order_nonce=order_nonce,
            time_in_force=time_in_force,purpose=purpose)
        order_id=result["order"]["order_id"]
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO order_authority VALUES(?,?,?,?,?,?)",
                (order_id,"LOCAL_ENTITY",json.dumps(eligibility,sort_keys=True),
                 json.dumps(collateral,sort_keys=True),"{}",_now()))
        result["eligibility_verified"]=bool(eligibility) or not bool(json.loads(instrument["buyer_requirements_json"] or "{}"))
        result["collateral_verified"]=bool(collateral) or not bool(json.loads(instrument["buyer_requirements_json"] or "{}").get("collateral_required"))
        return result

    @staticmethod
    def signed_order_body(envelope:dict)->dict:
        keys=("schema","entity_id","market_id","instrument_id","side","quantity",
              "limit_price_minor","currency","time_in_force","purpose","order_nonce",
              "created_at_ms","expires_at_ms")
        return {k:envelope.get(k) for k in keys}

    def verify_signed_order(self,envelope:dict,signer_manifest:dict)->dict:
        body=self.signed_order_body(envelope); entity_id=str(body.get("entity_id") or "")
        if body.get("schema")!="entity-data-market-order-v1": raise ValueError("unsupported remote order schema")
        if str(signer_manifest.get("entity_id") or "")!=entity_id: raise PermissionError("remote signer/entity mismatch")
        if int(body.get("expires_at_ms") or 0)<=_now(): raise PermissionError("remote order expired")
        created=int(body.get("created_at_ms") or 0)
        if created<=0 or created>_now()+300000: raise PermissionError("remote order timestamp invalid")
        if not self.identity.verify_signature(signer_manifest,body,dict(envelope.get("signature") or {})):
            raise PermissionError("remote order signature invalid")
        return body
    def ingest_signed_order(self,operator_entity_id:str,envelope:dict,signer_manifest:dict,*,
                            eligibility_evidence=None,collateral_evidence=None)->dict:
        self._require_local(operator_entity_id); body=self.verify_signed_order(dict(envelope),dict(signer_manifest))
        entity_id=str(body["entity_id"]); side=str(body["side"] or "").upper(); qty=int(body["quantity"])
        price=int(body["limit_price_minor"]); unit=str(body["currency"] or "").upper(); tif=str(body["time_in_force"] or "GTC").upper()
        nonce=str(body["order_nonce"] or ""); market_id=str(body["market_id"]); instrument_id=str(body["instrument_id"])
        if side not in _base.ORDER_SIDES or qty<=0 or price<0 or tif not in _base.TIME_IN_FORCE or not nonce:
            raise ValueError("invalid remote order")
        order_id=_id("dord1"); now=_now()
        with self._lock,self._connect() as db:
            market=self._market(db,market_id)
            if market["operator_entity_id"]!=operator_entity_id: raise PermissionError("market operator authority required")
            if market["quote_currency"]!=unit: raise ValueError("order currency does not match market")
            instrument=self._instrument(db,instrument_id); self._require_tradeable(instrument,entity_id,side,body.get("purpose"))
            eligibility,collateral=self._gate_order(instrument,entity_id,side,qty,price,unit,body.get("purpose"),eligibility_evidence,collateral_evidence)
            action="LIST_DATA_RIGHT" if side=="SELL" else "TRADE_DATA_RIGHT"
            policy=self._policy(jurisdiction=str(instrument["jurisdiction"]),instrument_class=str(instrument["jurisdictional_classification"]),action=action)
            if db.execute("SELECT 1 FROM orders WHERE order_nonce=?",(nonce,)).fetchone(): raise ValueError("duplicate/replayed order_nonce")
            if side=="SELL":
                pos=db.execute("SELECT * FROM positions WHERE instrument_id=? AND holder_entity_id=?",(instrument_id,entity_id)).fetchone()
                if not pos or int(pos["available_units"])<qty: raise ValueError("insufficient available rights units")
                db.execute("UPDATE positions SET available_units=available_units-?,reserved_units=reserved_units+?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",(qty,qty,now,instrument_id,entity_id))
            payload={"order_id":order_id,"instrument_id":instrument_id,"side":side,"quantity":qty,
                     "limit_price_minor":price,"currency":unit,"time_in_force":tif,"purpose":body.get("purpose"),
                     "jurisdiction_policy":policy,"remote_entity_id":entity_id,"remote_signature":envelope.get("signature")}
            event=self._market_event(db,market_id,operator_entity_id,"REMOTE_ORDER_ACCEPTED",order_id,payload)
            db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (order_id,market_id,entity_id,instrument_id,side,"LIMIT",qty,qty,price,unit,tif,
                 body.get("purpose"),"OPEN",nonce,event["sequence"],event["event_id"],now,now))
            db.execute("INSERT OR REPLACE INTO order_authority VALUES(?,?,?,?,?,?)",
                (order_id,"REMOTE_SIGNED",json.dumps(eligibility,sort_keys=True),json.dumps(collateral,sort_keys=True),
                 json.dumps(envelope,sort_keys=True),now))
            manifest_json=json.dumps(signer_manifest,sort_keys=True,separators=(",",":"),ensure_ascii=False)
            db.execute("INSERT OR REPLACE INTO remote_manifests VALUES(?,?,?,?)",
                (entity_id,manifest_json,hashlib.sha256(manifest_json.encode()).hexdigest(),now))
            trades=self._match(db,market_id,instrument_id,order_id)
            current=db.execute("SELECT * FROM orders WHERE order_id=?",(order_id,)).fetchone()
            if tif=="IOC" and int(current["remaining_quantity"])>0:
                self._cancel_remaining(db,current,actor=operator_entity_id,reason="REMOTE_IOC_UNFILLED")
                current=db.execute("SELECT * FROM orders WHERE order_id=?",(order_id,)).fetchone()
        return {"order":dict(current),"trades":trades,"authority_mode":"REMOTE_SIGNED",
                "remote_signature_verified":True,"eligibility_verified":bool(eligibility) or not bool(json.loads(instrument["buyer_requirements_json"] or "{}")),
                "collateral_verified":bool(collateral) or not bool(json.loads(instrument["buyer_requirements_json"] or "{}").get("collateral_required"))}

    def _record_royalty(self,trade_id:str,settlement_id:str)->dict|None:
        with self._connect() as db:
            trade=self._trade(db,trade_id); instrument=self._instrument(db,trade["instrument_id"])
        plan_id=instrument["royalty_plan_id"]
        if not plan_id or self.settlement_engine is None: return None
        amount=int(trade["quantity"])*int(trade["price_minor"])
        try:
            allocation=self.settlement_engine.allocate_royalties(plan_id,settlement_id,amount,trade["currency"])
            status="ALLOCATED"
        except ValueError as exc:
            if "already allocated" not in str(exc): raise
            with self._connect() as db:
                row=db.execute("SELECT allocation_json FROM trade_royalties WHERE trade_id=?",(trade_id,)).fetchone()
            return None if not row else json.loads(row["allocation_json"])
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO trade_royalties VALUES(?,?,?,?,?,?)",
                (trade_id,allocation["allocation_id"],plan_id,json.dumps(allocation,sort_keys=True),status,_now()))
        return allocation
    def finalize_trade(self,trade_id:str,settlement_id:str)->dict:
        result=super().finalize_trade(trade_id,settlement_id)
        result["royalty_allocation"]=self._record_royalty(trade_id,settlement_id)
        return result

    def finalize_trade_external(self,operator_entity_id:str,trade_id:str,evidence:dict)->dict:
        self._require_local(operator_entity_id)
        if self.compliance_gate is None: raise RuntimeError("external settlement compliance gate is not configured")
        with self._lock,self._connect() as db:
            trade=self._trade(db,trade_id)
            if trade["status"]!="PENDING_SETTLEMENT": raise ValueError("trade is not pending settlement")
            market=self._market(db,trade["market_id"])
            if market["operator_entity_id"]!=operator_entity_id: raise PermissionError("market operator authority required")
            instrument=self._instrument(db,trade["instrument_id"])
            self._policy(jurisdiction=str(instrument["jurisdiction"]),instrument_class=str(instrument["jurisdictional_classification"]),action="SETTLE_DATA_RIGHT_TRADE")
            verified=self.compliance_gate.verify_settlement(dict(evidence or {}),trade=dict(trade))
            qty=int(trade["quantity"]); now=_now(); settlement_ref=verified["settlement_ref"]
            seller=db.execute("SELECT * FROM positions WHERE instrument_id=? AND holder_entity_id=?",(trade["instrument_id"],trade["seller_entity_id"])).fetchone()
            if not seller or int(seller["reserved_units"])<qty: raise RuntimeError("seller reserved-right invariant failed")
            db.execute("UPDATE positions SET reserved_units=reserved_units-?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",(qty,now,trade["instrument_id"],trade["seller_entity_id"]))
            db.execute("INSERT INTO positions(instrument_id,holder_entity_id,available_units,reserved_units,consumed_units,updated_at_ms) VALUES(?,?,?,?,?,?) ON CONFLICT(instrument_id,holder_entity_id) DO UPDATE SET available_units=available_units+excluded.available_units,updated_at_ms=excluded.updated_at_ms",(trade["instrument_id"],trade["buyer_entity_id"],qty,0,0,now))
            db.execute("INSERT INTO external_settlements VALUES(?,?,?,?)",(trade_id,settlement_ref,json.dumps(verified["evidence"],sort_keys=True),now))
            event=self._market_event(db,trade["market_id"],operator_entity_id,"TRADE_SETTLED_EXTERNAL",trade_id,
                {"trade_id":trade_id,"settlement_ref":settlement_ref,"quantity":qty,"rights_transferred":True,
                 "external_authority_ref":verified["authority_ref"]})
            db.execute("UPDATE trades SET status='SETTLED',settlement_id=?,settled_at_ms=? WHERE trade_id=?",(settlement_ref,now,trade_id))
        allocation=self._record_royalty(trade_id,settlement_ref)
        return {"trade_id":trade_id,"status":"SETTLED","settlement_id":settlement_ref,"quantity":qty,
                "rights_transferred":True,"external_settlement_verified":True,"royalty_allocation":allocation,
                "market_sequence":event["sequence"],"event_id":event["event_id"]}
    def create_signed_order(self,entity_id:str,market_id:str,instrument_id:str,*,side:str,quantity:int,
                            limit_price_minor:int,currency:str,order_nonce:str,time_in_force:str="GTC",
                            purpose:str|None=None,expires_at_ms:int|None=None)->dict:
        self._require_local(entity_id); now=_now(); expiry=int(expires_at_ms or (now+300000))
        if expiry<=now: raise ValueError("order envelope expiry must be in the future")
        body={"schema":"entity-data-market-order-v1","entity_id":entity_id,"market_id":market_id,
              "instrument_id":instrument_id,"side":str(side).upper(),"quantity":int(quantity),
              "limit_price_minor":int(limit_price_minor),"currency":str(currency).upper(),
              "time_in_force":str(time_in_force).upper(),"purpose":purpose,"order_nonce":str(order_nonce),
              "created_at_ms":now,"expires_at_ms":expiry}
        body["signature"]=self.identity.sign(entity_id,body)
        return body

    def _manifest_for_export(self,entity_id:str,db):
        try: return self.identity.load_manifest(entity_id)
        except Exception:
            row=db.execute("SELECT manifest_json FROM remote_manifests WHERE entity_id=?",(entity_id,)).fetchone()
            return None if not row else json.loads(row["manifest_json"])

    def export_market_package(self,market_id:str,destination:str|Path|None=None)->dict:
        with self._connect() as db:
            market=dict(self._market(db,market_id))
            orders=[dict(x) for x in db.execute("SELECT * FROM orders WHERE market_id=? ORDER BY market_sequence",(market_id,))]
            trades=[dict(x) for x in db.execute("SELECT * FROM trades WHERE market_id=? ORDER BY market_sequence",(market_id,))]
            events=[dict(x) for x in db.execute("SELECT * FROM market_events WHERE market_id=? ORDER BY sequence",(market_id,))]
            instrument_ids=sorted({str(x["instrument_id"]) for x in orders+trades})
            instruments=[dict(db.execute("SELECT * FROM instruments WHERE instrument_id=?",(iid,)).fetchone()) for iid in instrument_ids]
            commodity_ids=sorted({str(x["commodity_id"]) for x in instruments})
            commodities=[dict(db.execute("SELECT * FROM commodities WHERE commodity_id=?",(cid,)).fetchone()) for cid in commodity_ids]
            positions=[]; issuances=[]; consumptions=[]
            for iid in instrument_ids:
                positions.extend(dict(x) for x in db.execute("SELECT * FROM positions WHERE instrument_id=? ORDER BY holder_entity_id",(iid,)))
                issuances.extend(dict(x) for x in db.execute("SELECT * FROM issuances WHERE instrument_id=? ORDER BY created_at_ms",(iid,)))
                consumptions.extend(dict(x) for x in db.execute("SELECT * FROM consumptions WHERE instrument_id=? ORDER BY created_at_ms",(iid,)))
            order_ids=[x["order_id"] for x in orders]; trade_ids=[x["trade_id"] for x in trades]
            authority=[dict(x) for x in db.execute("SELECT * FROM order_authority") if x["order_id"] in order_ids]
            royalties=[dict(x) for x in db.execute("SELECT * FROM trade_royalties") if x["trade_id"] in trade_ids]
            external=[dict(x) for x in db.execute("SELECT * FROM external_settlements") if x["trade_id"] in trade_ids]
            entities={market["operator_entity_id"]}
            for row in orders: entities.add(row["entity_id"])
            for row in trades: entities.update((row["buyer_entity_id"],row["seller_entity_id"]))
            for row in instruments: entities.add(row["issuer_entity_id"])
            manifests={eid:self._manifest_for_export(eid,db) for eid in sorted(entities)}
            manifests={k:v for k,v in manifests.items() if v is not None}
        tables={"markets":[market],"commodities":commodities,"instruments":instruments,"positions":positions,
                "issuances":issuances,"orders":orders,"trades":trades,"consumptions":consumptions,
                "market_events":events,"order_authority":authority,"trade_royalties":royalties,
                "external_settlements":external}
        authority_ids=set()
        for row in authority:
            for field in ("eligibility_json","collateral_json"):
                try:
                    item=json.loads(row.get(field) or "{}")
                    aid=str((item.get("evidence") or {}).get("authority_id") or "")
                    if aid: authority_ids.add(aid)
                except Exception: pass
        for row in external:
            try:
                aid=str(json.loads(row.get("evidence_json") or "{}").get("authority_id") or "")
                if aid: authority_ids.add(aid)
            except Exception: pass
        external_trust={}
        verifier=getattr(self.compliance_gate,"verifier",None) if self.compliance_gate is not None else None
        if verifier is not None and hasattr(verifier,"authority"):
            for aid in sorted(authority_ids):
                try: external_trust[aid]=verifier.authority(aid)
                except Exception: pass
        body={"schema":"entity-data-market-package-v1","market_id":market_id,"created_at_ms":_now(),
              "operator_entity_id":market["operator_entity_id"],"head_hash":market["head_hash"],
              "sequence":int(market["sequence"]),"tables":tables,"manifests":manifests,
              "external_trust":external_trust,"provider_independent":True,"raw_data_included":False}
        body["package_sha256"]=_sha(body)
        body["signature"]=self.identity.sign(market["operator_entity_id"],{k:v for k,v in body.items() if k!="signature"})
        if destination is not None:
            path=Path(destination); path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(body,indent=2,sort_keys=True),encoding="utf-8")
        return body
    def verify_invariants(self)->dict:
        result=super().verify_invariants(); failures=list(result["failures"])
        with self._connect() as db:
            for row in db.execute("SELECT o.order_id,o.side,o.instrument_id,a.authority_mode,a.eligibility_json,a.collateral_json FROM orders o LEFT JOIN order_authority a ON a.order_id=o.order_id"):
                instrument=self._instrument(db,row["instrument_id"]); req=json.loads(instrument["buyer_requirements_json"] or "{}")
                if row["authority_mode"] is None: failures.append(f"{row['order_id']}:missing_order_authority")
                if row["side"]=="BUY" and req and not json.loads(row["eligibility_json"] or "{}"):
                    failures.append(f"{row['order_id']}:missing_buyer_eligibility")
                if row["side"]=="BUY" and req.get("collateral_required") and not json.loads(row["collateral_json"] or "{}"):
                    failures.append(f"{row['order_id']}:missing_collateral")
            for trade in db.execute("SELECT * FROM trades WHERE status='SETTLED'"):
                if trade["settlement_id"] is None: failures.append(f"{trade['trade_id']}:missing_settlement_reference")
                instrument=self._instrument(db,trade["instrument_id"])
                if instrument["royalty_plan_id"]:
                    royal=db.execute("SELECT status FROM trade_royalties WHERE trade_id=?",(trade["trade_id"],)).fetchone()
                    if not royal or royal["status"]!="ALLOCATED": failures.append(f"{trade['trade_id']}:royalty_not_allocated")
        result["failures"]=failures; result["pass"]=not failures
        result.update({"buyer_eligibility_evidence":True,"collateral_evidence":True,
                       "remote_signed_orders":True,"external_settlement_evidence":True,
                       "royalty_reconciliation":True,"provider_independent_market_export":True})
        return result

    def status(self)->dict:
        out=super().status()
        out.update({"schema":"entity-data-commodity-exchange-v2","engineering_complete":True,
                    "remote_signed_orders":True,"buyer_eligibility_gate":True,"collateral_gate":True,
                    "external_settlement_gate":True,"royalty_allocation":True,"market_export":True,
                    "regulated_live_venue_enabled":False,"legal_classification_performed":False})
        return out
