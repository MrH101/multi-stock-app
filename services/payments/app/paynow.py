"""Minimal Paynow (Zimbabwe) client, following the official Python and Node SDKs.

* POST form-encoded to /interface/initiatetransaction (web) or /interface/remotetransaction (mobile).
* The hash is SHA512 over the field values concatenated in send order (excluding ``hash``), followed by
  the integration key in lower case, as UPPERCASE hex. Responses and status updates are verified the
  same way over the fields in the order they were received.
* We only send values that URL-encoding leaves unchanged (references, decimals, digits, lower-case method),
  so the SDKs' encode-before-hash quirk can't cause mismatches. URLs and the e-mail go raw, as in the SDK.
"""
import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import parse_qsl

import httpx

# Paynow statuses that mean the money has been received.
PAID_STATUSES = {"paid", "awaiting delivery", "delivered"}
FAILED_STATUSES = {"failed"}
CANCELLED_STATUSES = {"cancelled"}
DISPUTED_STATUSES = {"disputed"}
REFUNDED_STATUSES = {"refunded"}


class PaynowError(Exception):
    pass


def make_hash(values: list[tuple[str, str]], integration_key: str) -> str:
    raw = "".join(str(v) for k, v in values if k.lower() != "hash") + integration_key.lower()
    return hashlib.sha512(raw.encode("utf-8")).hexdigest().upper()


def verify(fields: list[tuple[str, str]], integration_key: str) -> bool:
    received = next((v for k, v in fields if k.lower() == "hash"), None)
    if not received:
        return False
    return hmac.compare_digest(received.upper(), make_hash(fields, integration_key))


def parse(body: str) -> list[tuple[str, str]]:
    return parse_qsl(body, keep_blank_values=True)


@dataclass
class InitResult:
    poll_url: str | None
    redirect_url: str | None
    instructions: str | None
    innbucks_code: str | None
    innbucks_expires: str | None


@dataclass
class StatusResult:
    status: str  # Paynow's status, lower-cased
    amount: str | None
    reference: str | None
    paynow_reference: str | None
    poll_url: str | None


class PaynowClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(30.0, connect=5.0), transport=transport)

    def _send(self, path: str, values: list[tuple[str, str]], key: str) -> dict[str, str]:
        fields = [*values, ("hash", make_hash(values, key))]
        try:
            r = self._http.post(path, data=dict(fields))
        except httpx.HTTPError as exc:
            raise PaynowError(f"Paynow is unreachable ({type(exc).__name__}). Please try again.") from exc
        if r.status_code != 200:
            raise PaynowError(f"Paynow returned HTTP {r.status_code}")
        resp = parse(r.text)
        data = {k.lower(): v for k, v in resp}
        if data.get("status", "").lower() == "error":
            raise PaynowError(data.get("error") or "Paynow rejected the payment request")
        if not verify(resp, key):
            raise PaynowError("Paynow's reply failed its integrity check")
        return data

    def initiate(self, *, integration_id: str, integration_key: str, reference: str, amount: str, info: str,
                 return_url: str, result_url: str, auth_email: str = "", phone: str | None = None,
                 method: str | None = None) -> InitResult:
        values = [("resulturl", result_url), ("returnurl", return_url), ("reference", reference),
                  ("amount", amount), ("id", integration_id), ("additionalinfo", info), ("authemail", auth_email)]
        if phone is not None:
            values += [("phone", phone), ("method", method or "ecocash")]
        values.append(("status", "Message"))
        path = "/interface/remotetransaction" if phone is not None else "/interface/initiatetransaction"
        d = self._send(path, values, integration_key)
        return InitResult(poll_url=d.get("pollurl"), redirect_url=d.get("browserurl"),
                          instructions=d.get("instructions"), innbucks_code=d.get("authorizationcode"),
                          innbucks_expires=d.get("authorizationexpires"))

    def poll(self, poll_url: str, integration_key: str) -> StatusResult:
        try:
            r = self._http.post(poll_url, data={})
        except httpx.HTTPError as exc:
            raise PaynowError(f"Paynow is unreachable ({type(exc).__name__})") from exc
        fields = parse(r.text)
        data = {k.lower(): v for k, v in fields}
        if data.get("status", "").lower() == "error":
            raise PaynowError(data.get("error") or "Paynow could not report the status")
        if not verify(fields, integration_key):
            raise PaynowError("Paynow's status reply failed its integrity check")
        return to_status(data)


def to_status(data: dict[str, str]) -> StatusResult:
    return StatusResult(status=(data.get("status") or "").strip().lower(), amount=data.get("amount"),
                        reference=data.get("reference"), paynow_reference=data.get("paynowreference"),
                        poll_url=data.get("pollurl"))
