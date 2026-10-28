# Railway Nooks capture

Two isolated services provide a stable public webhook and private signature
verification. This release captures the original test contact only. It has no
lemlist completion operation, worker, scheduling, enrollment or dialing.

Use the existing `ai-sdr` Railway project and its production environment, adding
`nooks-receiver` and `nooks-verifier`. Preserve the existing `sdr-bridge`, its
domain, credentials, PostgreSQL and data. Both new services build this directory's
Dockerfile from the exact independently reviewed GitHub commit. Set one replica
per service, healthcheck `/healthz`, port 8080, no sleep, no cron. Expose only the
receiver with a Railway-generated domain; the verifier uses private networking.

## Configuration

Both services need `SDR_ROLE` (`receiver` or `verifier`) and `CAPTURE_SCOPE`, a
non-secret JSON object with `workspace_id`, `prospect_id`, `not_before` and
`expires_at`. Timestamps are integer UTC seconds; the window is at most 48 hours.
The selected expected prospect is HubSpot `213807637412`, workspace
`0qzObckuGaOQjpdI`. Capture cannot prove that CRM relationship: independently
verify the Nooks record's HubSpot link before any later completion is authorized.
Unknown/mismatched prospect IDs are rejected. Scope changes cannot overwrite an
existing durable inbox without an explicitly reviewed migration.

The receiver requires a new dedicated volume mounted at `/data` (start with
500 MB) and `VERIFIER_URL=http://nooks-verifier.railway.internal:8080`. It refuses
ephemeral storage. Configure the verifier's private endpoint as `nooks-verifier`.
The receiver holds an exclusive volume lock. SQLite transactions use FULL
synchronization; ACK follows commit. Duplicate call IDs are idempotent, changed
replays and additional calls hold the test, and the inbox is bounded to 100 calls.
It stores only normalized IDs, timestamps and a disposition label, never raw
webhooks, notes, recordings, signatures, email addresses or phone numbers.

Railway mounts volumes as root. The cloud-only launcher initializes the new
state directory, then drops privileges before serving: UID502 for the receiver,
UID503 for the verifier. It rejects non-Linux or non-Railway execution. Development
and tests on the Mini remain under agentwork UID502; no sudo is used there.

## Identity and secrets

On first boot the receiver generates an Ed25519 identity into a private file on
its own persistent volume. `/identity` returns only its public key. After checking
the actual Railway service, domain and deployed source revision, pin that public
key in the verifier's `RECEIVER_PUBLIC_KEY`. Do not automatically repin a changed
identity. A replaced volume requires deliberate identity review. Never inspect,
return or export the private key using agent tools.

The receiver signs the operation, audience, method/path, timestamp, nonce, body
digest and Nooks signature header. The verifier authenticates this before parsing
Nooks content. A bounded in-memory nonce/rate cache rejects recent repeats;
the durable receiver inbox deduplicates calls across either service's restart.
Private requests have a fixed host/port, no redirects, no environment proxies,
bounded body/response sizes and a total exchange deadline.

Only the verifier gets `NOOKS_SIGNING_KEY`. The user enters it privately in
Railway's Variables UI; the agent never retrieves or transfers its value. Do not
copy credentials from the Mini or existing bridge. No lemlist or HubSpot keys,
Railway tokens or old admin tokens are passed to the receiver. Request bodies,
authentication headers and exceptions are not logged. Access logging is off.

## Registration and cutover

1. Deploy both services and verify the exact revision, receiver domain, one
   replica and mounted volume. Pin the receiver public key as described above.
2. When the user is ready to save the stable Nooks URL, set the receiver's
   `REGISTRATION_ID` to a fresh 32-character lowercase hex identifier and
   `REGISTRATION_DEADLINE` to a UTC epoch no more than one hour ahead. This is a
   public one-shot setup ACK, not authentication. Normal signed verification
   runs first, so a real selected-contact call is captured during setup too.
   The setup fallback accepts only an empty probe or a completed inbound or outbound
   call-shaped probe with explicit workspace/prospect IDs outside this test's
   selected pair. Selected or ambiguous calls that fail verification receive
   retryable errors and never consume setup. No out-of-scope probe is retained. Nooks documents an inbound example in its
   [webhook guide](https://support.nooks.ai/articles/8109690071-nooks-webhooks-integration-guide).
   During setup, private logs report each fixed rejection reason at most once per
   process. They never include request values, headers, keys or raw errors.
   The consumption record survives restart; expiry does not crash the service.
3. Save `https://<verified-railway-domain>/api/sdr/webhooks/nooks` in Nooks once.
   If Nooks issues a new signing key, the user stores it privately on the verifier.
   Close setup by clearing both registration variables to empty/zero and deploy.
   `/ready` must show `registration_open:false` and `verifier_ready:true`.
4. Preserve the local test journal; stop local ingress and never run the local
   completion command against this cloud experiment. No dual workers exist in
   this release. A later hosted completion release must reconcile the selected
   lemlist task afresh and consume this durable inbox under independent review.
5. Receive a real finalized call for the selected contact. Verify successful
   signed capture, duplicate delivery and retained count/identity after redeploy.
   A healthy process, generated URL or setup ACK does not prove signed capture.

Public health, readiness, identity and aggregate event count expose no contact
records. There is no public event-read, arm, completion or provider forwarding
endpoint. A future reviewed worker will access normalized durable evidence.

Recovery: preserve the receiver volume and key identity. Roll back to the prior
reviewed source revision using Railway without reverting unrelated settings or
credentials. The local experiment's source/state and original blocked controller
task remain intact. Do not restore old configuration over later operator changes.

## Validation

From `/Users/agentwork/apps/linkedin-agent`, as UID502:

```
.venv/bin/python -B -m unittest discover -s tests -p 'test_cloud_sdr.py' -v
```

Run `DOCKER_HOST=unix:///path/to/isolated/docker.sock .venv/bin/python -B tests/cloud_container_smoke.py` against a dedicated agentwork-owned Docker daemon for the Linux smoke check. It builds only cloud source, uses disposable containers/volume/network with dummy credentials, verifies UID/GID dropping, private HTTP verification, signed capture and volume reuse, and removes its test resources. It never mounts host directories.

Tests use dummy keys and real cryptography, in-process HTTP transport and temporary
SQLite. They do not call providers, dial or complete any task. Cloud verification
also requires an actual mounted volume, private network, installed public-key
pin, private signing-key entry and real Nooks event.
