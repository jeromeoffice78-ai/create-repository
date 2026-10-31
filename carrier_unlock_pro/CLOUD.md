# Carrier Unlock Pro cloud integration

Run from backend: `uvicorn cloud:app --host 0.0.0.0 --port $PORT`.
Set CUP_ADMIN_TOKEN and UNLOCKBASE_API_KEY in hosting environment variables only.
All endpoints except / and /health require `Authorization: Bearer <CUP_ADMIN_TOKEN>`.

- GET /provider/account: authenticates to UnlockBase, returns balance and currency.
- GET /provider/services: reads the provider service catalog and required fields.
- GET /provider/orders/{id}: reads the specified provider order status and last four IMEI digits.
- POST /provider/orders: unavailable; never creates a billable provider order.
- Cloud draft creation is unavailable until durable storage is configured.

Provider protocol: https://www.unlockbase.com/download/api/v3/API.pdf
Endpoint: https://www.unlockbase.com/xml/api/v3 (POST form Key and Action).
Delivery status uses polling via GetOrders, not an unverified webhook contract.
The first provider API call binds the account API security to its source IP.
Confirm the hosting outbound IP configuration before initial verification.

Validation: 9 local tests passed, including protected endpoints, request contract,
provider errors, entity rejection, ID filtering and IMEI minimization.
These are mock transport tests; live connectivity requires separate verification.
