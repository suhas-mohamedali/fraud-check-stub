"""
Fraud-check (PRM) stub for the BECS processor.

Hosts the POST endpoint that PrmCheckService.sendForFraudCheck() calls
(default http://localhost:9090/api/prm/check, see application.yml
`becs.prm-service-url`). The processor sends one request per BECS file:

    { "fileName": "...", "payments": [ PrmPaymentDto, ... ] }

Every payment is approved ('A') except a random subset that is declined
('D'). The number declined is random but never more than
REJECT_CAP_PERCENT of the payments in the file (rounded down), so a file
with fewer than 20 payments is never rejected at the default 5%.

Decisions are remembered per fileName, so a re-sent file gets the same
answer and repeated calls can never push a file over the cap.
"""
import logging
import math
import os
import random
import threading
from typing import Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

REJECT_CAP_PERCENT = float(os.getenv("REJECT_CAP_PERCENT", "5"))
SEED = os.getenv("RANDOM_SEED")

APPROVED = "A"
DECLINED = "D"

log = logging.getLogger("fraud-check-stub")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

rng = random.Random(int(SEED)) if SEED is not None else random.Random()


class PrmPayment(BaseModel):
    """Mirrors com.becs.processor.dto.PrmPaymentDto."""
    model_config = ConfigDict(extra="allow")

    bsbNumber: Optional[str] = None
    accountNumber: Optional[str] = None
    indicator: Optional[str] = None
    transactionCode: Optional[str] = None
    amountCents: Optional[int] = None
    accountName: Optional[str] = None
    lodgementReference: Optional[str] = None
    traceBsb: Optional[str] = None
    traceAccount: Optional[str] = None
    remitterName: Optional[str] = None
    withholdingTax: Optional[int] = None
    lineNumber: Optional[int] = None
    recordType: Optional[str] = None


class PrmCheckRequest(BaseModel):
    fileName: str
    payments: List[PrmPayment] = []


class PaymentResult(BaseModel):
    lineNumber: Optional[int]
    bsbNumber: Optional[str]
    accountNumber: Optional[str]
    amountCents: Optional[int]
    prmStatus: str
    reason: Optional[str] = None


class PrmCheckResponse(BaseModel):
    fileName: str
    totalPayments: int
    rejectedPayments: int
    maxRejectionsAllowed: int
    rejectionPercent: float
    results: List[PaymentResult]


app = FastAPI(title="PRM Fraud Check Stub", version="1.0.0")

# fileName -> {payment key -> status}
_decisions: Dict[str, Dict[str, str]] = {}
_lock = threading.Lock()


def _key(p: PrmPayment, index: int) -> str:
    # lineNumber is unique within a BECS file; fall back to position.
    return f"L{p.lineNumber}" if p.lineNumber is not None else f"I{index}"


def _decide(file_name: str, payments: List[PrmPayment]) -> Dict[str, str]:
    keys = [_key(p, i) for i, p in enumerate(payments)]
    with _lock:
        known = _decisions.setdefault(file_name, {})
        total = len(set(known) | set(keys))
        cap = math.floor(total * REJECT_CAP_PERCENT / 100)
        already_rejected = sum(1 for s in known.values() if s == DECLINED)

        new_keys = [k for k in dict.fromkeys(keys) if k not in known]
        budget = max(0, cap - already_rejected)
        # Pick how many of the new payments to reject (0..budget), at random.
        n_reject = rng.randint(0, min(budget, len(new_keys)))
        rejected = set(rng.sample(new_keys, n_reject))
        for k in new_keys:
            known[k] = DECLINED if k in rejected else APPROVED
        return dict(known)


@app.post("/api/prm/check", response_model=PrmCheckResponse)
def prm_check(req: PrmCheckRequest) -> PrmCheckResponse:
    decisions = _decide(req.fileName, req.payments)

    results = []
    for i, p in enumerate(req.payments):
        status = decisions[_key(p, i)]
        results.append(PaymentResult(
            lineNumber=p.lineNumber,
            bsbNumber=p.bsbNumber,
            accountNumber=p.accountNumber,
            amountCents=p.amountCents,
            prmStatus=status,
            reason="Random fraud-check rejection (stub)" if status == DECLINED else None,
        ))

    total = len(decisions)
    rejected = sum(1 for s in decisions.values() if s == DECLINED)
    resp = PrmCheckResponse(
        fileName=req.fileName,
        totalPayments=total,
        rejectedPayments=rejected,
        maxRejectionsAllowed=math.floor(total * REJECT_CAP_PERCENT / 100),
        rejectionPercent=round(100 * rejected / total, 2) if total else 0.0,
        results=results,
    )
    log.info("PRM check %s: %d payments, %d rejected (cap %d)",
             req.fileName, total, rejected, resp.maxRejectionsAllowed)
    for r in results:
        if r.prmStatus == DECLINED:
            log.info("  declined line %s bsb %s acct %s amount %s",
                     r.lineNumber, r.bsbNumber, r.accountNumber, r.amountCents)
    return resp


@app.get("/api/prm/files/{file_name}")
def file_summary(file_name: str):
    """Decisions recorded for a file, handy for checking the 5% cap."""
    d = _decisions.get(file_name, {})
    rejected = sorted(k for k, s in d.items() if s == DECLINED)
    return {"fileName": file_name, "totalPayments": len(d),
            "rejectedPayments": len(rejected), "rejectedKeys": rejected}


@app.get("/health")
def health():
    return {"status": "UP", "rejectCapPercent": REJECT_CAP_PERCENT}


if __name__ == "__main__":
    import uvicorn
    # Java's JDK HttpClient (used by Spring's RestClient) sends HTTP/1.1 requests
    # with "Upgrade: h2c". uvicorn's default httptools parser drops the body of
    # such requests (422 "Field required"); the h11 parser ignores the upgrade.
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "9090")),
                http="h11")
