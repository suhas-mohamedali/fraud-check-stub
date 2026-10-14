# PRM Fraud Check Stub (FastAPI)

A local stand-in for the external PRM fraud-check web service that
`PrmCheckService.sendForFraudCheck()` calls. It hosts:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/prm/check` | The fraud check the BECS processor calls |
| GET | `/api/prm/files/{fileName}` | Decisions recorded for a file |
| GET | `/health` | Liveness |
| GET | `/docs` | Swagger UI |

## Rejection rule

* Each request carries one whole BECS file (`fileName` + all its `payments`),
  so the total is simply the number of payments in the request.
* A random number of payments, from 0 up to **5% of the total (rounded down)**,
  is declined (`prmStatus: "D"`); the rest are approved (`"A"`). Which payments
  are declined is also random.
* Because of rounding down, a file with fewer than 20 payments is never rejected.
* Decisions are remembered per `fileName` (in memory, until restart), so
  re-sending a file returns the same answer and can never push it past 5%.

`A`/`D` match the `prm_status` values allowed in `becs_payment_record`.

## Run

```bash
cd fraud-check-stub
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
python main.py                   # listens on http://localhost:9090
```

or `uvicorn main:app --port 9090 --reload`.

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `9090` | Listen port |
| `REJECT_CAP_PERCENT` | `5` | Max share of a file's payments that may be declined |
| `RANDOM_SEED` | unset | Set for repeatable rejections |

## Point the processor at it

The processor already defaults to this address
(`becs.prm-service-url: ${BECS_PRM_URL:http://localhost:9090/api/prm/check}`
in `application.yml`), so running the processor locally needs no change.

When the processor runs in Docker (`docker-compose.yml`), `localhost` is the
container itself; set `BECS_PRM_URL=http://host.docker.internal:9090/api/prm/check`
on the `becs-app` service instead.

## Example

```bash
curl -X POST http://localhost:9090/api/prm/check -H "Content-Type: application/json" \
  -d '{"fileName":"test.bpy","payments":[{"lineNumber":2,"bsbNumber":"062-000","accountNumber":"12345678","amountCents":1000}]}'
```

Response:

```json
{
  "fileName": "test.bpy",
  "totalPayments": 1,
  "rejectedPayments": 0,
  "maxRejectionsAllowed": 0,
  "rejectionPercent": 0.0,
  "results": [
    {"lineNumber": 2, "bsbNumber": "062-000", "accountNumber": "12345678",
     "amountCents": 1000, "prmStatus": "A", "reason": null}
  ]
}
```

The processor currently ignores the response body (`toBodilessEntity()`), so
any 2xx is accepted; the per-payment `prmStatus` is ready for when it starts
recording `prm_status`.
