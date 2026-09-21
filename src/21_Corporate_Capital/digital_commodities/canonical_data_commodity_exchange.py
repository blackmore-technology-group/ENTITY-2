from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
import hashlib, json, secrets, sqlite3, time

ZERO_HASH = "0" * 64
RIGHTS_CLASSES = {
    "ACCESS_RIGHT", "API_QUERY_RIGHT", "AI_TRAINING_RIGHT",
    "COMMERCIAL_USE_RIGHT", "DERIVATIVE_RIGHT", "REDISTRIBUTION_RIGHT",
    "COMPUTE_RIGHT", "EXCLUSIVE_USE_RIGHT", "RESEARCH_RIGHT", "ARCHIVAL_RIGHT",
}
ORDER_SIDES = {"BUY", "SELL"}
ORDER_TYPES = {"LIMIT"}
TIME_IN_FORCE = {"GTC", "IOC"}
ORDER_ACTIVE = {"OPEN", "PARTIALLY_FILLED"}
TRADE_FINAL = {"SETTLED", "FAILED", "CANCELLED"}

def _now(): return int(time.time() * 1000)
def _id(prefix): return f"{prefix}-" + secrets.token_hex(20)
def _canon(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def _sha(value): return hashlib.sha256(value if isinstance(value, (bytes, bytearray)) else _canon(value)).hexdigest()

class DataCommodityExchange:
    """Sovereign data-right commodity registry, rights ledger and deterministic exchange."""
    def __init__(self, state_dir: str|Path, identity, *, event_ledger=None,
                 classifier=None, settlement_engine=None, local_controller_check=None):
        self.root = Path(state_dir) / "data_commodity_exchange"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "exchange.sqlite"
        self.identity = identity
        self.event_ledger = event_ledger
        self.classifier = classifier
        self.settlement_engine = settlement_engine
        self.local_controller_check = local_controller_check or self._default_local
        self._lock = RLock()
        self._init_db()

    def _default_local(self, entity_id: str) -> bool:
        try:
            self.identity.load_manifest(entity_id)
            return True
        except Exception:
            return False

    def _require_local(self, entity_id: str):
        if not self.local_controller_check(entity_id):
            raise PermissionError("operation requires locally controlled Entity")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init_db(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS markets(market_id TEXT PRIMARY KEY,operator_entity_id TEXT NOT NULL,name TEXT NOT NULL,quote_currency TEXT NOT NULL,status TEXT NOT NULL,sequence INTEGER NOT NULL,head_hash TEXT NOT NULL,created_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS commodities(commodity_id TEXT PRIMARY KEY,controller_entity_id TEXT NOT NULL,underlying_asset_id TEXT NOT NULL,commodity_type TEXT NOT NULL,unit_code TEXT NOT NULL,unit_description TEXT NOT NULL,total_units INTEGER NOT NULL,divisible INTEGER NOT NULL,fungibility TEXT NOT NULL,quality_grade TEXT NOT NULL,commercialization_authority INTEGER NOT NULL,protocol_classification TEXT NOT NULL,jurisdiction TEXT NOT NULL,authority_ref TEXT NOT NULL,metadata_json TEXT NOT NULL,status TEXT NOT NULL,created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS instruments(instrument_id TEXT PRIMARY KEY,commodity_id TEXT NOT NULL,issuer_entity_id TEXT NOT NULL,symbol TEXT NOT NULL UNIQUE,rights_class TEXT NOT NULL,authorized_units INTEGER NOT NULL,issued_units INTEGER NOT NULL,circulating_units INTEGER NOT NULL,consumed_units INTEGER NOT NULL,transferable INTEGER NOT NULL,resale_allowed INTEGER NOT NULL,divisible INTEGER NOT NULL,expiry_at_ms INTEGER,territory TEXT NOT NULL,permitted_purposes_json TEXT NOT NULL,buyer_requirements_json TEXT NOT NULL,royalty_plan_id TEXT,jurisdiction TEXT NOT NULL,jurisdictional_classification TEXT NOT NULL,status TEXT NOT NULL,created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS positions(instrument_id TEXT NOT NULL,holder_entity_id TEXT NOT NULL,available_units INTEGER NOT NULL,reserved_units INTEGER NOT NULL,consumed_units INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL,PRIMARY KEY(instrument_id,holder_entity_id))")
            db.execute("CREATE TABLE IF NOT EXISTS issuances(issuance_id TEXT PRIMARY KEY,issuance_nonce TEXT UNIQUE NOT NULL,instrument_id TEXT NOT NULL,issuer_entity_id TEXT NOT NULL,holder_entity_id TEXT NOT NULL,quantity INTEGER NOT NULL,created_at_ms INTEGER NOT NULL,signature_json TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS orders(order_id TEXT PRIMARY KEY,market_id TEXT NOT NULL,entity_id TEXT NOT NULL,instrument_id TEXT NOT NULL,side TEXT NOT NULL,order_type TEXT NOT NULL,quantity INTEGER NOT NULL,remaining_quantity INTEGER NOT NULL,limit_price_minor INTEGER NOT NULL,currency TEXT NOT NULL,time_in_force TEXT NOT NULL,purpose TEXT,status TEXT NOT NULL,order_nonce TEXT UNIQUE NOT NULL,market_sequence INTEGER NOT NULL,event_id TEXT NOT NULL,created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS trades(trade_id TEXT PRIMARY KEY,market_id TEXT NOT NULL,instrument_id TEXT NOT NULL,buy_order_id TEXT NOT NULL,sell_order_id TEXT NOT NULL,buyer_entity_id TEXT NOT NULL,seller_entity_id TEXT NOT NULL,quantity INTEGER NOT NULL,price_minor INTEGER NOT NULL,currency TEXT NOT NULL,status TEXT NOT NULL,settlement_id TEXT,market_sequence INTEGER NOT NULL,event_id TEXT NOT NULL,created_at_ms INTEGER NOT NULL,settled_at_ms INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS consumptions(consumption_id TEXT PRIMARY KEY,usage_ref TEXT UNIQUE NOT NULL,instrument_id TEXT NOT NULL,holder_entity_id TEXT NOT NULL,quantity INTEGER NOT NULL,created_at_ms INTEGER NOT NULL,signature_json TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS market_events(event_id TEXT PRIMARY KEY,market_id TEXT NOT NULL,sequence INTEGER NOT NULL,event_type TEXT NOT NULL,actor_entity_id TEXT NOT NULL,object_ref TEXT NOT NULL,payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL,prior_hash TEXT NOT NULL,event_hash TEXT NOT NULL,signature_json TEXT NOT NULL,created_at_ms INTEGER NOT NULL,UNIQUE(market_id,sequence))")
    def _policy(self, *, jurisdiction: str, instrument_class: str, action: str):
        if self.classifier is None:
            raise PermissionError("instrument classification registry is required for exchange operation")
        return self.classifier.require_evidence_operation(
            jurisdiction=jurisdiction,
            instrument_class=instrument_class,
            action=action,
        )

    def _external_event(self, actor: str, event_type: str, object_ids: list[str], payload: dict):
        if self.event_ledger is None:
            return None
        return self.event_ledger.append(
            actor, event_type, subject_ids=[actor], object_ids=object_ids,
            payload=payload, evidence_origin="DIRECT_OBSERVATION",
        )

    def _market(self, db, market_id: str):
        row = db.execute("SELECT * FROM markets WHERE market_id=?", (market_id,)).fetchone()
        if not row or row["status"] != "ACTIVE":
            raise KeyError("active market not found")
        return row

    def _market_event(self, db, market_id: str, actor: str, event_type: str,
                      object_ref: str, payload: dict) -> dict:
        market = self._market(db, market_id)
        sequence = int(market["sequence"]) + 1
        now = _now(); payload_hash = _sha(payload); prior = str(market["head_hash"])
        body = {
            "schema": "entity-data-market-event-v1",
            "market_id": market_id,
            "sequence": sequence,
            "event_type": event_type,
            "actor_entity_id": actor,
            "object_ref": object_ref,
            "payload_hash": payload_hash,
            "prior_hash": prior,
            "created_at_ms": now,
        }
        signature = self.identity.sign(actor, body)
        event_hash = _sha({"body": body, "signature": signature})
        event_id = _id("dmkev1")
        db.execute(
            "INSERT INTO market_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, market_id, sequence, event_type, actor, object_ref,
             json.dumps(payload, sort_keys=True), payload_hash, prior, event_hash,
             json.dumps(signature, sort_keys=True), now),
        )
        db.execute("UPDATE markets SET sequence=?,head_hash=? WHERE market_id=?",
                   (sequence, event_hash, market_id))
        return {"event_id": event_id, "sequence": sequence, "event_hash": event_hash,
                "prior_hash": prior, "signature": signature, "created_at_ms": now}

    def create_market(self, operator_entity_id: str, name: str, *, quote_currency: str) -> dict:
        self._require_local(operator_entity_id)
        currency = str(quote_currency or "").upper().strip()
        if not currency or not str(name or "").strip():
            raise ValueError("market name and quote_currency required")
        market_id = _id("dmkt1"); now = _now()
        with self._connect() as db:
            db.execute("INSERT INTO markets VALUES(?,?,?,?,?,?,?,?)",
                       (market_id, operator_entity_id, str(name)[:256], currency,
                        "ACTIVE", 0, ZERO_HASH, now))
        return {"market_id": market_id, "operator_entity_id": operator_entity_id,
                "name": str(name)[:256], "quote_currency": currency, "status": "ACTIVE"}

    def register_commodity(self, controller_entity_id: str, underlying_asset_id: str, *,
                           commodity_type: str, unit_code: str, unit_description: str,
                           total_units: int, divisible: bool=True, fungibility: str="PROFILED",
                           quality_grade: str="UNSPECIFIED", commercialization_authority: bool,
                           jurisdiction: str="UNSPECIFIED", authority_ref: str, metadata=None) -> dict:
        self._require_local(controller_entity_id)
        asset = str(underlying_asset_id or "").strip(); kind = str(commodity_type or "").upper().strip()
        unit = str(unit_code or "").upper().strip(); description = str(unit_description or "").strip()
        authority = str(authority_ref or "").strip(); quantity = int(total_units)
        if not asset or not kind or not unit or not description or quantity <= 0 or not authority:
            raise ValueError("asset, commodity type, unit definition, positive total_units and authority_ref required")
        cid = _id("dcom2"); now = _now(); jur = str(jurisdiction or "UNSPECIFIED").upper()
        body = {"commodity_id": cid, "controller_entity_id": controller_entity_id,
                "underlying_asset_id": asset, "commodity_type": kind, "unit_code": unit,
                "unit_description": description, "total_units": quantity,
                "divisible": bool(divisible), "fungibility": str(fungibility).upper(),
                "quality_grade": str(quality_grade).upper(), "commercialization_authority": bool(commercialization_authority),
                "protocol_classification": "DATA_COMMODITY", "jurisdiction": jur,
                "authority_ref": authority, "status": "ACTIVE", "created_at_ms": now}
        with self._connect() as db:
            db.execute("INSERT INTO commodities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (cid, controller_entity_id, asset, kind, unit, description, quantity,
                        1 if divisible else 0, body["fungibility"], body["quality_grade"],
                        1 if commercialization_authority else 0, "DATA_COMMODITY", jur,
                        authority, json.dumps(dict(metadata or {}), sort_keys=True),
                        "ACTIVE", now, now))
        body["signature"] = self.identity.sign(controller_entity_id, body)
        body["ownership_not_inferred"] = True
        body["legal_classification_not_inferred"] = True
        self._external_event(controller_entity_id, "DATA_COMMODITY_REGISTERED", [cid, asset],
                             {"commodity_id": cid, "underlying_asset_id": asset,
                              "protocol_classification": "DATA_COMMODITY", "authority_ref": authority})
        return body

    def _commodity(self, db, commodity_id: str):
        row = db.execute("SELECT * FROM commodities WHERE commodity_id=?", (commodity_id,)).fetchone()
        if not row:
            raise KeyError("data commodity not found")
        return row

    def _instrument(self, db, instrument_id: str):
        row = db.execute("SELECT * FROM instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
        if not row:
            raise KeyError("data-right instrument not found")
        return row

    def create_instrument(self, issuer_entity_id: str, commodity_id: str, *, symbol: str,
                          rights_class: str, authorized_units: int, transferable: bool=True,
                          resale_allowed: bool=True, divisible: bool=True, expiry_at_ms: int|None=None,
                          territory: str="GLOBAL", permitted_purposes=None, buyer_requirements=None,
                          royalty_plan_id: str|None=None, jurisdictional_classification: str="CLASSIFICATION_UNKNOWN") -> dict:
        self._require_local(issuer_entity_id)
        rights = str(rights_class or "").upper().strip(); sym = str(symbol or "").upper().strip()
        units = int(authorized_units)
        if rights not in RIGHTS_CLASSES:
            raise ValueError("unsupported rights_class")
        if not sym or units <= 0:
            raise ValueError("symbol and positive authorized_units required")
        if resale_allowed and not transferable:
            raise ValueError("resale requires transferable instrument")
        with self._connect() as db:
            commodity = self._commodity(db, commodity_id)
            if commodity["controller_entity_id"] != issuer_entity_id:
                raise PermissionError("initial instrument issuance requires commodity controller authority")
            if not bool(commodity["commercialization_authority"]):
                raise PermissionError("commodity lacks commercialization authority")
            if commodity["status"] != "ACTIVE":
                raise PermissionError("commodity is not active")
            jur = str(commodity["jurisdiction"])
        classification = str(jurisdictional_classification or "CLASSIFICATION_UNKNOWN").upper()
        policy = self._policy(jurisdiction=jur, instrument_class=classification, action="ISSUE_DATA_RIGHT")
        now = _now()
        if expiry_at_ms is not None and int(expiry_at_ms) <= now:
            raise ValueError("instrument expiry must be in the future")
        iid = _id("dri1")
        with self._connect() as db:
            db.execute("INSERT INTO instruments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (iid, commodity_id, issuer_entity_id, sym, rights, units, 0, 0, 0,
                        1 if transferable else 0, 1 if resale_allowed else 0, 1 if divisible else 0,
                        None if expiry_at_ms is None else int(expiry_at_ms), str(territory).upper(),
                        json.dumps(sorted({str(x).upper() for x in (permitted_purposes or [])}), sort_keys=True),
                        json.dumps(dict(buyer_requirements or {}), sort_keys=True), royalty_plan_id,
                        jur, classification, "ACTIVE", now, now))
        body = {"instrument_id": iid, "commodity_id": commodity_id,
                "issuer_entity_id": issuer_entity_id, "symbol": sym, "rights_class": rights,
                "authorized_units": units, "transferable": bool(transferable),
                "resale_allowed": bool(resale_allowed), "divisible": bool(divisible),
                "expiry_at_ms": expiry_at_ms, "territory": str(territory).upper(),
                "jurisdiction": jur, "jurisdictional_classification": classification,
                "policy": policy, "status": "ACTIVE", "created_at_ms": now}
        body["signature"] = self.identity.sign(issuer_entity_id, body)
        self._external_event(issuer_entity_id, "DATA_RIGHT_INSTRUMENT_CREATED", [commodity_id, iid],
                             {"instrument_id": iid, "rights_class": rights,
                              "jurisdictional_classification": classification})
        return body

    def issue(self, issuer_entity_id: str, instrument_id: str, holder_entity_id: str, *,
              quantity: int, issuance_nonce: str) -> dict:
        self._require_local(issuer_entity_id)
        qty = int(quantity); nonce = str(issuance_nonce or "").strip()
        if qty <= 0 or not nonce:
            raise ValueError("positive quantity and issuance_nonce required")
        now = _now(); issuance_id = _id("dissue1")
        with self._lock, self._connect() as db:
            instrument = self._instrument(db, instrument_id)
            if instrument["issuer_entity_id"] != issuer_entity_id:
                raise PermissionError("instrument issuer mismatch")
            if instrument["status"] != "ACTIVE":
                raise PermissionError("instrument is not active")
            if instrument["expiry_at_ms"] is not None and int(instrument["expiry_at_ms"]) <= now:
                raise PermissionError("instrument expired")
            self._policy(jurisdiction=str(instrument["jurisdiction"]),
                         instrument_class=str(instrument["jurisdictional_classification"]),
                         action="ISSUE_DATA_RIGHT")
            new_issued = int(instrument["issued_units"]) + qty
            if new_issued > int(instrument["authorized_units"]):
                raise ValueError("issuance exceeds authorized instrument supply")
            body = {"schema": "entity-data-right-issuance-v1", "issuance_id": issuance_id,
                    "issuance_nonce": nonce, "instrument_id": instrument_id,
                    "issuer_entity_id": issuer_entity_id, "holder_entity_id": holder_entity_id,
                    "quantity": qty, "created_at_ms": now}
            signature = self.identity.sign(issuer_entity_id, body)
            try:
                db.execute("INSERT INTO issuances VALUES(?,?,?,?,?,?,?,?)",
                           (issuance_id, nonce, instrument_id, issuer_entity_id,
                            holder_entity_id, qty, now, json.dumps(signature, sort_keys=True)))
            except sqlite3.IntegrityError as exc:
                raise ValueError("duplicate/replayed issuance_nonce") from exc
            db.execute("UPDATE instruments SET issued_units=?,circulating_units=circulating_units+?,updated_at_ms=? WHERE instrument_id=?",
                       (new_issued, qty, now, instrument_id))
            db.execute("INSERT INTO positions(instrument_id,holder_entity_id,available_units,reserved_units,consumed_units,updated_at_ms) VALUES(?,?,?,?,?,?) ON CONFLICT(instrument_id,holder_entity_id) DO UPDATE SET available_units=available_units+excluded.available_units,updated_at_ms=excluded.updated_at_ms",
                       (instrument_id, holder_entity_id, qty, 0, 0, now))
        self._external_event(issuer_entity_id, "DATA_RIGHT_ISSUED", [instrument_id, issuance_id],
                             {"issuance_id": issuance_id, "holder_entity_id": holder_entity_id,
                              "quantity": qty})
        return {**body, "signature": signature, "supply_integrity": True}

    def position(self, holder_entity_id: str, instrument_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM positions WHERE instrument_id=? AND holder_entity_id=?",
                             (instrument_id, holder_entity_id)).fetchone()
        if not row:
            return {"instrument_id": instrument_id, "holder_entity_id": holder_entity_id,
                    "available_units": 0, "reserved_units": 0, "consumed_units": 0}
        return dict(row)

    def _require_tradeable(self, instrument, entity_id: str, side: str, purpose: str|None):
        now = _now()
        if instrument["status"] != "ACTIVE":
            raise PermissionError("instrument is not active")
        if instrument["expiry_at_ms"] is not None and int(instrument["expiry_at_ms"]) <= now:
            raise PermissionError("instrument expired")
        if not bool(instrument["transferable"]):
            raise PermissionError("instrument is non-transferable")
        if side == "SELL" and entity_id != instrument["issuer_entity_id"] and not bool(instrument["resale_allowed"]):
            raise PermissionError("secondary resale is not allowed")
        allowed = set(json.loads(instrument["permitted_purposes_json"] or "[]"))
        if allowed:
            requested = str(purpose or "").upper().strip()
            if not requested or requested not in allowed:
                raise PermissionError("trade purpose is outside instrument permissions")
        requirements = dict(json.loads(instrument["buyer_requirements_json"] or "{}"))
        if side == "BUY" and requirements:
            raise PermissionError("instrument requires an external buyer-eligibility gate")

    def place_order(self, entity_id: str, market_id: str, instrument_id: str, *,
                    side: str, quantity: int, limit_price_minor: int, currency: str,
                    order_nonce: str, time_in_force: str="GTC", purpose: str|None=None) -> dict:
        self._require_local(entity_id)
        order_side = str(side or "").upper(); qty = int(quantity); price = int(limit_price_minor)
        unit = str(currency or "").upper(); tif = str(time_in_force or "GTC").upper()
        nonce = str(order_nonce or "").strip()
        if order_side not in ORDER_SIDES or qty <= 0 or price < 0 or not unit or not nonce:
            raise ValueError("invalid order")
        if tif not in TIME_IN_FORCE:
            raise ValueError("unsupported time_in_force")
        order_id = _id("dord1"); now = _now()
        with self._lock, self._connect() as db:
            market = self._market(db, market_id)
            if market["quote_currency"] != unit:
                raise ValueError("order currency does not match market quote currency")
            instrument = self._instrument(db, instrument_id)
            self._require_tradeable(instrument, entity_id, order_side, purpose)
            policy_action = "LIST_DATA_RIGHT" if order_side == "SELL" else "TRADE_DATA_RIGHT"
            policy = self._policy(jurisdiction=str(instrument["jurisdiction"]),
                                  instrument_class=str(instrument["jurisdictional_classification"]),
                                  action=policy_action)
            if db.execute("SELECT 1 FROM orders WHERE order_nonce=?", (nonce,)).fetchone():
                raise ValueError("duplicate/replayed order_nonce")
            if order_side == "SELL":
                pos = db.execute("SELECT * FROM positions WHERE instrument_id=? AND holder_entity_id=?",
                                 (instrument_id, entity_id)).fetchone()
                if not pos or int(pos["available_units"]) < qty:
                    raise ValueError("insufficient available rights units")
                db.execute("UPDATE positions SET available_units=available_units-?,reserved_units=reserved_units+?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",
                           (qty, qty, now, instrument_id, entity_id))
            payload = {"order_id": order_id, "instrument_id": instrument_id,
                       "side": order_side, "quantity": qty, "limit_price_minor": price,
                       "currency": unit, "time_in_force": tif, "purpose": purpose,
                       "jurisdiction_policy": policy}
            event = self._market_event(db, market_id, entity_id, "ORDER_OPENED", order_id, payload)
            db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (order_id, market_id, entity_id, instrument_id, order_side, "LIMIT",
                        qty, qty, price, unit, tif, purpose, "OPEN", nonce,
                        event["sequence"], event["event_id"], now, now))
            trades = self._match(db, market_id, instrument_id, order_id)
            current = db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if tif == "IOC" and int(current["remaining_quantity"]) > 0:
                self._cancel_remaining(db, current, actor=entity_id, reason="IOC_UNFILLED")
                current = db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        return {"order": dict(current), "trades": trades, "rights_reserved": order_side == "SELL"}
    def _set_fill(self, db, order_id: str, fill_qty: int):
        row = db.execute("SELECT remaining_quantity FROM orders WHERE order_id=?", (order_id,)).fetchone()
        remaining = int(row["remaining_quantity"]) - int(fill_qty)
        if remaining < 0:
            raise RuntimeError("order overfill detected")
        status = "FILLED" if remaining == 0 else "PARTIALLY_FILLED"
        db.execute("UPDATE orders SET remaining_quantity=?,status=?,updated_at_ms=? WHERE order_id=?",
                   (remaining, status, _now(), order_id))

    def _match(self, db, market_id: str, instrument_id: str, trigger_order_id: str) -> list[dict]:
        trades = []
        while True:
            trigger = db.execute("SELECT * FROM orders WHERE order_id=?", (trigger_order_id,)).fetchone()
            if not trigger or trigger["status"] not in ORDER_ACTIVE or int(trigger["remaining_quantity"]) <= 0:
                break
            if trigger["side"] == "BUY":
                counter = db.execute("SELECT * FROM orders WHERE market_id=? AND instrument_id=? AND side='SELL' AND entity_id<>? AND status IN ('OPEN','PARTIALLY_FILLED') AND remaining_quantity>0 AND limit_price_minor<=? ORDER BY limit_price_minor ASC,market_sequence ASC LIMIT 1",
                                     (market_id, instrument_id, trigger["entity_id"], int(trigger["limit_price_minor"]))).fetchone()
            else:
                counter = db.execute("SELECT * FROM orders WHERE market_id=? AND instrument_id=? AND side='BUY' AND entity_id<>? AND status IN ('OPEN','PARTIALLY_FILLED') AND remaining_quantity>0 AND limit_price_minor>=? ORDER BY limit_price_minor DESC,market_sequence ASC LIMIT 1",
                                     (market_id, instrument_id, trigger["entity_id"], int(trigger["limit_price_minor"]))).fetchone()
            if not counter:
                break
            qty = min(int(trigger["remaining_quantity"]), int(counter["remaining_quantity"]))
            price = int(counter["limit_price_minor"])
            buy = trigger if trigger["side"] == "BUY" else counter
            sell = trigger if trigger["side"] == "SELL" else counter
            trade_id = _id("dtrd1"); market = self._market(db, market_id)
            payload = {"trade_id": trade_id, "instrument_id": instrument_id,
                       "buy_order_id": buy["order_id"], "sell_order_id": sell["order_id"],
                       "buyer_entity_id": buy["entity_id"], "seller_entity_id": sell["entity_id"],
                       "quantity": qty, "price_minor": price, "currency": buy["currency"],
                       "pricing_rule": "RESTING_ORDER_PRICE", "settlement_required": True}
            event = self._market_event(db, market_id, market["operator_entity_id"],
                                       "TRADE_EXECUTED", trade_id, payload)
            now = _now()
            db.execute("INSERT INTO trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (trade_id, market_id, instrument_id, buy["order_id"], sell["order_id"],
                        buy["entity_id"], sell["entity_id"], qty, price, buy["currency"],
                        "PENDING_SETTLEMENT", None, event["sequence"], event["event_id"], now, None))
            self._set_fill(db, buy["order_id"], qty)
            self._set_fill(db, sell["order_id"], qty)
            trades.append({**payload, "status": "PENDING_SETTLEMENT",
                           "market_sequence": event["sequence"], "event_id": event["event_id"]})
        return trades

    def _cancel_remaining(self, db, order, *, actor: str, reason: str) -> dict:
        remaining = int(order["remaining_quantity"])
        if remaining <= 0:
            return {"order_id": order["order_id"], "released_units": 0}
        if order["side"] == "SELL":
            db.execute("UPDATE positions SET reserved_units=reserved_units-?,available_units=available_units+?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",
                       (remaining, remaining, _now(), order["instrument_id"], order["entity_id"]))
        payload = {"order_id": order["order_id"], "remaining_quantity": remaining,
                   "reason": str(reason)[:256]}
        event = self._market_event(db, order["market_id"], actor, "ORDER_CANCELLED",
                                   order["order_id"], payload)
        db.execute("UPDATE orders SET remaining_quantity=0,status='CANCELLED',updated_at_ms=? WHERE order_id=?",
                   (_now(), order["order_id"]))
        return {"order_id": order["order_id"], "released_units": remaining,
                "event_id": event["event_id"], "market_sequence": event["sequence"]}

    def cancel_order(self, entity_id: str, order_id: str, *, reason: str="OWNER_CANCELLED") -> dict:
        self._require_local(entity_id)
        with self._lock, self._connect() as db:
            order = db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if not order:
                raise KeyError("order not found")
            if order["entity_id"] != entity_id:
                raise PermissionError("only order owner may cancel")
            if order["status"] not in ORDER_ACTIVE:
                raise ValueError("order is not cancellable")
            return self._cancel_remaining(db, order, actor=entity_id, reason=reason)

    def _trade(self, db, trade_id: str):
        row = db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,)).fetchone()
        if not row:
            raise KeyError("trade not found")
        return row

    def finalize_trade(self, trade_id: str, settlement_id: str) -> dict:
        if self.settlement_engine is None:
            raise RuntimeError("settlement engine is not configured")
        settlement = self.settlement_engine.get(settlement_id)
        with self._lock, self._connect() as db:
            trade = self._trade(db, trade_id)
            if trade["status"] != "PENDING_SETTLEMENT":
                raise ValueError("trade is not pending settlement")
            instrument = self._instrument(db, trade["instrument_id"])
            self._policy(jurisdiction=str(instrument["jurisdiction"]),
                         instrument_class=str(instrument["jurisdictional_classification"]),
                         action="SETTLE_DATA_RIGHT_TRADE")
            expected_amount = int(trade["quantity"]) * int(trade["price_minor"])
            if settlement["state"] not in {"CONFIRMED", "RECONCILED"}:
                raise PermissionError("settlement is not final")
            if settlement["payer_entity_id"] != trade["buyer_entity_id"] or settlement["payee_entity_id"] != trade["seller_entity_id"]:
                raise PermissionError("settlement parties do not match trade")
            if int(settlement["amount_units"]) != expected_amount or settlement["currency"] != trade["currency"]:
                raise PermissionError("settlement amount/currency does not match trade")
            if settlement["obligation_ref"] != trade_id:
                raise PermissionError("settlement obligation_ref must bind exact trade")
            seller = db.execute("SELECT * FROM positions WHERE instrument_id=? AND holder_entity_id=?",
                                (trade["instrument_id"], trade["seller_entity_id"])).fetchone()
            if not seller or int(seller["reserved_units"]) < int(trade["quantity"]):
                raise RuntimeError("seller reserved-right invariant failed")
            qty = int(trade["quantity"]); now = _now()
            db.execute("UPDATE positions SET reserved_units=reserved_units-?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",
                       (qty, now, trade["instrument_id"], trade["seller_entity_id"]))
            db.execute("INSERT INTO positions(instrument_id,holder_entity_id,available_units,reserved_units,consumed_units,updated_at_ms) VALUES(?,?,?,?,?,?) ON CONFLICT(instrument_id,holder_entity_id) DO UPDATE SET available_units=available_units+excluded.available_units,updated_at_ms=excluded.updated_at_ms",
                       (trade["instrument_id"], trade["buyer_entity_id"], qty, 0, 0, now))
            market = self._market(db, trade["market_id"])
            event = self._market_event(db, trade["market_id"], market["operator_entity_id"],
                                       "TRADE_SETTLED", trade_id,
                                       {"trade_id": trade_id, "settlement_id": settlement_id,
                                        "quantity": qty, "rights_transferred": True})
            db.execute("UPDATE trades SET status='SETTLED',settlement_id=?,settled_at_ms=? WHERE trade_id=?",
                       (settlement_id, now, trade_id))
        self._external_event(trade["buyer_entity_id"], "DATA_RIGHT_TRANSFER_SETTLED",
                             [trade["instrument_id"], trade_id],
                             {"trade_id": trade_id, "settlement_id": settlement_id,
                              "buyer_entity_id": trade["buyer_entity_id"],
                              "seller_entity_id": trade["seller_entity_id"], "quantity": qty})
        return {"trade_id": trade_id, "status": "SETTLED", "settlement_id": settlement_id,
                "quantity": qty, "rights_transferred": True,
                "market_sequence": event["sequence"], "event_id": event["event_id"]}

    def fail_trade(self, trade_id: str, *, reason: str="SETTLEMENT_FAILED") -> dict:
        with self._lock, self._connect() as db:
            trade = self._trade(db, trade_id)
            if trade["status"] != "PENDING_SETTLEMENT":
                raise ValueError("trade is not pending settlement")
            qty = int(trade["quantity"]); now = _now()
            db.execute("UPDATE positions SET reserved_units=reserved_units-?,available_units=available_units+?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",
                       (qty, qty, now, trade["instrument_id"], trade["seller_entity_id"]))
            market = self._market(db, trade["market_id"])
            event = self._market_event(db, trade["market_id"], market["operator_entity_id"],
                                       "TRADE_FAILED", trade_id,
                                       {"trade_id": trade_id, "quantity": qty, "reason": str(reason)[:256]})
            db.execute("UPDATE trades SET status='FAILED' WHERE trade_id=?", (trade_id,))
        return {"trade_id": trade_id, "status": "FAILED", "released_units": qty,
                "event_id": event["event_id"], "market_sequence": event["sequence"]}
    def consume_right(self, holder_entity_id: str, instrument_id: str, *,
                      quantity: int, usage_ref: str) -> dict:
        self._require_local(holder_entity_id)
        qty = int(quantity); ref = str(usage_ref or "").strip(); now = _now()
        if qty <= 0 or not ref:
            raise ValueError("positive quantity and usage_ref required")
        consumption_id = _id("dcon1")
        with self._lock, self._connect() as db:
            instrument = self._instrument(db, instrument_id)
            if instrument["expiry_at_ms"] is not None and int(instrument["expiry_at_ms"]) <= now:
                raise PermissionError("instrument expired")
            self._policy(jurisdiction=str(instrument["jurisdiction"]),
                         instrument_class=str(instrument["jurisdictional_classification"]),
                         action="CONSUME_DATA_RIGHT")
            pos = db.execute("SELECT * FROM positions WHERE instrument_id=? AND holder_entity_id=?",
                             (instrument_id, holder_entity_id)).fetchone()
            if not pos or int(pos["available_units"]) < qty:
                raise ValueError("insufficient available rights units")
            body = {"schema": "entity-data-right-consumption-v1", "consumption_id": consumption_id,
                    "usage_ref": ref, "instrument_id": instrument_id,
                    "holder_entity_id": holder_entity_id, "quantity": qty, "created_at_ms": now}
            signature = self.identity.sign(holder_entity_id, body)
            try:
                db.execute("INSERT INTO consumptions VALUES(?,?,?,?,?,?,?)",
                           (consumption_id, ref, instrument_id, holder_entity_id, qty, now,
                            json.dumps(signature, sort_keys=True)))
            except sqlite3.IntegrityError as exc:
                raise ValueError("duplicate/replayed usage_ref") from exc
            db.execute("UPDATE positions SET available_units=available_units-?,consumed_units=consumed_units+?,updated_at_ms=? WHERE instrument_id=? AND holder_entity_id=?",
                       (qty, qty, now, instrument_id, holder_entity_id))
            db.execute("UPDATE instruments SET circulating_units=circulating_units-?,consumed_units=consumed_units+?,updated_at_ms=? WHERE instrument_id=?",
                       (qty, qty, now, instrument_id))
        self._external_event(holder_entity_id, "DATA_RIGHT_CONSUMED", [instrument_id, consumption_id],
                             {"consumption_id": consumption_id, "usage_ref": ref, "quantity": qty})
        return {**body, "signature": signature, "status": "CONSUMED"}

    def market_snapshot(self, market_id: str, instrument_id: str) -> dict:
        with self._connect() as db:
            self._market(db, market_id); self._instrument(db, instrument_id)
            bid = db.execute("SELECT MAX(limit_price_minor) FROM orders WHERE market_id=? AND instrument_id=? AND side='BUY' AND status IN ('OPEN','PARTIALLY_FILLED') AND remaining_quantity>0",
                             (market_id, instrument_id)).fetchone()[0]
            ask = db.execute("SELECT MIN(limit_price_minor) FROM orders WHERE market_id=? AND instrument_id=? AND side='SELL' AND status IN ('OPEN','PARTIALLY_FILLED') AND remaining_quantity>0",
                             (market_id, instrument_id)).fetchone()[0]
            last = db.execute("SELECT price_minor,quantity,currency,status,created_at_ms FROM trades WHERE market_id=? AND instrument_id=? ORDER BY market_sequence DESC LIMIT 1",
                              (market_id, instrument_id)).fetchone()
            executed = db.execute("SELECT COALESCE(SUM(quantity),0) FROM trades WHERE market_id=? AND instrument_id=?",
                                  (market_id, instrument_id)).fetchone()[0]
            settled = db.execute("SELECT COALESCE(SUM(quantity),0) FROM trades WHERE market_id=? AND instrument_id=? AND status='SETTLED'",
                                 (market_id, instrument_id)).fetchone()[0]
        return {"market_id": market_id, "instrument_id": instrument_id,
                "best_bid_minor": None if bid is None else int(bid),
                "best_ask_minor": None if ask is None else int(ask),
                "last_execution": None if last is None else dict(last),
                "executed_volume": int(executed), "settled_volume": int(settled),
                "estimated_value_is_not_market_price": True}
    def verify_market(self, market_id: str) -> dict:
        with self._connect() as db:
            market = self._market(db, market_id)
            rows = db.execute("SELECT * FROM market_events WHERE market_id=? ORDER BY sequence",
                              (market_id,)).fetchall()
        prior = ZERO_HASH; expected_sequence = 1; manifests = {}
        for raw in rows:
            row = dict(raw); payload = json.loads(row["payload_json"] or "{}")
            if int(row["sequence"]) != expected_sequence or row["prior_hash"] != prior:
                return {"pass": False, "reason": "market_sequence_or_chain_failure",
                        "sequence": int(row["sequence"])}
            if _sha(payload) != row["payload_hash"]:
                return {"pass": False, "reason": "market_payload_hash_failure",
                        "sequence": int(row["sequence"])}
            body = {"schema": "entity-data-market-event-v1", "market_id": market_id,
                    "sequence": int(row["sequence"]), "event_type": row["event_type"],
                    "actor_entity_id": row["actor_entity_id"], "object_ref": row["object_ref"],
                    "payload_hash": row["payload_hash"], "prior_hash": row["prior_hash"],
                    "created_at_ms": int(row["created_at_ms"])}
            sig = json.loads(row["signature_json"]); actor = row["actor_entity_id"]
            manifest = manifests.get(actor)
            if manifest is None:
                manifest = self.identity.load_manifest(actor); manifests[actor] = manifest
            if not self.identity.verify_signature(manifest, body, sig):
                return {"pass": False, "reason": "market_signature_failure",
                        "sequence": int(row["sequence"])}
            if _sha({"body": body, "signature": sig}) != row["event_hash"]:
                return {"pass": False, "reason": "market_event_hash_failure",
                        "sequence": int(row["sequence"])}
            prior = row["event_hash"]; expected_sequence += 1
        return {"pass": prior == market["head_hash"] and len(rows) == int(market["sequence"]),
                "market_id": market_id, "events_checked": len(rows), "head_hash": prior}

    def verify_invariants(self) -> dict:
        failures = []
        with self._connect() as db:
            instruments = db.execute("SELECT * FROM instruments ORDER BY instrument_id").fetchall()
            positions = db.execute("SELECT * FROM positions ORDER BY instrument_id,holder_entity_id").fetchall()
            for instrument in instruments:
                iid = instrument["instrument_id"]
                rows = [p for p in positions if p["instrument_id"] == iid]
                available_reserved = sum(int(p["available_units"]) + int(p["reserved_units"]) for p in rows)
                consumed = sum(int(p["consumed_units"]) for p in rows)
                if int(instrument["issued_units"]) > int(instrument["authorized_units"]):
                    failures.append(f"{iid}:issued_exceeds_authorized")
                if int(instrument["issued_units"]) != int(instrument["circulating_units"]) + int(instrument["consumed_units"]):
                    failures.append(f"{iid}:issued_supply_reconciliation")
                if available_reserved != int(instrument["circulating_units"]):
                    failures.append(f"{iid}:position_circulating_reconciliation")
                if consumed != int(instrument["consumed_units"]):
                    failures.append(f"{iid}:position_consumed_reconciliation")
                for p in rows:
                    if min(int(p["available_units"]), int(p["reserved_units"]), int(p["consumed_units"])) < 0:
                        failures.append(f"{iid}:{p['holder_entity_id']}:negative_position")
                    open_sell = int(db.execute("SELECT COALESCE(SUM(remaining_quantity),0) FROM orders WHERE instrument_id=? AND entity_id=? AND side='SELL' AND status IN ('OPEN','PARTIALLY_FILLED')",
                                               (iid, p["holder_entity_id"])).fetchone()[0])
                    pending_trade = int(db.execute("SELECT COALESCE(SUM(quantity),0) FROM trades WHERE instrument_id=? AND seller_entity_id=? AND status='PENDING_SETTLEMENT'",
                                                  (iid, p["holder_entity_id"])).fetchone()[0])
                    if int(p["reserved_units"]) != open_sell + pending_trade:
                        failures.append(f"{iid}:{p['holder_entity_id']}:reservation_reconciliation")
            markets = [r[0] for r in db.execute("SELECT market_id FROM markets ORDER BY market_id").fetchall()]
        market_checks = {mid: self.verify_market(mid) for mid in markets}
        for mid, result in market_checks.items():
            if not result["pass"]:
                failures.append(f"{mid}:{result.get('reason','market_verification_failed')}")
        return {"pass": not failures, "failures": failures,
                "instruments_checked": len(instruments), "positions_checked": len(positions),
                "markets_checked": len(markets), "market_checks": market_checks,
                "double_sale_prevention": True, "settlement_before_rights_transfer": True}

    def status(self) -> dict:
        with self._connect() as db:
            commodities = int(db.execute("SELECT COUNT(*) FROM commodities").fetchone()[0])
            instruments = int(db.execute("SELECT COUNT(*) FROM instruments").fetchone()[0])
            markets = int(db.execute("SELECT COUNT(*) FROM markets").fetchone()[0])
            orders = int(db.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
            trades = int(db.execute("SELECT COUNT(*) FROM trades").fetchone()[0])
        return {"ready": True, "schema": "entity-data-commodity-exchange-v1",
                "protocol_classification": "DATA_COMMODITY", "commodities": commodities,
                "instruments": instruments, "markets": markets, "orders": orders, "trades": trades,
                "rights_aware_exchange": True, "secondary_market_supported": True,
                "market_operator_is_not_owner": True, "registration_is_not_legal_ownership": True,
                "jurisdiction_policy_fail_closed_when_configured": True,
                "settlement_before_rights_transfer": True}
