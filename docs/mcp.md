# DeliR MCP: first local connector and remote delivery path

## What works now

`backend.mcp_server` is a local stdio MCP server for Cursor. It exposes:

| Tool | Effect |
| --- | --- |
| `list_projects`, `list_processes` | Read the current tenant's workspace. |
| `get_process`, `get_bpmn_model` | Read process metadata and authoritative BPMN XML with its version ID. |
| `create_process` | Create an empty process record in a selected project; the BPMN model is saved in a separate step. |
| `validate_bpmn` | Check XML structure and basic BPMN references; this is **not** full BPMN 2.0 certification. |
| `preview_bpmn_change` | Compare proposed XML with the current version without writing. |
| `save_bpmn_model` | Save through the existing API with `expected_version_id`; stale writes get HTTP 409. |
| `update_process_element` | Rename or document one element and save through the same version guard. |

The server calls FastAPI for every workspace read and write. Tenant checks, the
write pipeline, version history, and concurrency controls remain in DeliR. It
does not introduce a new process language or claim lossless conversion from a
compact representation. BPMN XML remains the stored document.

## Run locally with Cursor

1. Start DeliR with `npm run dev` and make sure the backend is on
   `http://127.0.0.1:8000`. If it moved to another port, edit the URL in
   `.cursor/mcp.json`.
2. Open this repository in Cursor. The project MCP configuration is in
   `.cursor/mcp.json` and starts `.venv/Scripts/python.exe -m backend.mcp_server`.
3. For an authenticated DeliR environment, provide `DELIR_API_TOKEN` in
   Cursor's process environment and set the matching tenant and URL in the
   config. Never commit a real token to `mcp.json`.
4. Ask Cursor to list projects or read a process first. For a write, have it
   read the model version, preview the XML, then save with that version.

This configuration targets the Windows checkout. Other systems can substitute
their virtual environment's Python executable.

## Personal Claude pilot now

The `backend.mcp_pilot` HTTP adapter is a **single-tenant personal test**. It
uses a separate bearer token, keeps the DeliR API token on your machine, and
exposes read tools only by default. It is not an account system or a customer
deployment.

1. Start the DeliR backend on `127.0.0.1:8000` and install
   [cloudflared for Windows](https://developers.cloudflare.com/tunnel/downloads/).
2. In terminal A, run `cloudflared tunnel --url http://127.0.0.1:8765`.
   Copy only the hostname from the temporary `https://...trycloudflare.com`
   URL. The tunnel may start before the MCP process is listening.
3. In terminal B, from the repository root, set the pilot environment and run
   the server:

   ```powershell
   $env:DELIR_MCP_PILOT_TOKEN = (& .\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(48))')
   $env:DELIR_MCP_PILOT_TOKEN | Set-Clipboard
   $env:DELIR_MCP_PILOT_PUBLIC_HOST = 'replace-with-host.trycloudflare.com'
   $env:DELIR_MCP_API_URL = 'http://127.0.0.1:8000'
   $env:DELIR_MCP_TENANT_ID = 'local'
   .\.venv\Scripts\python.exe -m uvicorn backend.mcp_pilot:app --host 127.0.0.1 --port 8765
   ```

   If your DeliR backend requires auth, set `DELIR_MCP_API_TOKEN` in terminal B
   from your existing local secret source before starting the server. Do not
   put it in Claude's connector settings. Do not paste either token into git.
4. In Claude, open **Customize → Connectors → Add custom connector**. Enter
   `https://replace-with-host.trycloudflare.com/mcp`. Choose **No sign in** and
   add the request header `Authorization: Bearer <DELIR_MCP_PILOT_TOKEN>` using
   the value copied to the clipboard in terminal B. Claude stores that fixed credential for
   this connector. Ask it to list DeliR projects as the first check.
5. Stop both processes to close the pilot. The temporary hostname then stops
   working. Generate a fresh pilot token for each new session.

The pilot requires a token of at least 32 characters and rejects requests
without it. `DELIR_MCP_PILOT_PUBLIC_HOST` is an exact Host allowlist entry; it
must match the tunnel hostname. Quick Tunnels do not support SSE, so this
adapter uses JSON responses. To test editing later, set
`DELIR_MCP_PILOT_ALLOW_WRITES=1` before starting the server and review Claude's
tool permissions. This is an explicit opt-in for create and save operations.

## Claude and ChatGPT customer access

Both need a reachable **Streamable HTTP** MCP endpoint for a hosted connection.
ChatGPT's custom MCP connection requires a public HTTPS URL or its secure MCP
tunnel. Claude custom connectors accept a remote MCP URL. The local stdio
configuration cannot be entered as a URL in either product.

Do **not** publish the personal pilot as a customer service. The current DeliR backend
authenticates with a shared API token, while per-user identity, membership, and
subscription entitlements are future work in
`docs/deployment-and-tenancy.md`. A public MCP endpoint that forwards this
shared token would let an external caller act as that tenant without a
user-specific plan or permission check.

The remote implementation should use the same tool definitions against the
same application services, with these gates before exposure:

1. OAuth 2.1 resource-server authentication and token verification on every
   MCP HTTP request, with a real authorization server used by both Claude and
   ChatGPT. Bind tokens to the DeliR MCP resource.
2. Resolve user and tenant from verified identity and membership. Do not trust
   a caller-supplied tenant header as authorization.
3. Check MCP entitlement on each tool call. Product direction supplied on
   2026-11-24 is **Professional and above**, with a limited trial; exact plan
   names, prices, quotas, and trial duration are proposals to validate.
4. Separate read and write scopes. Meter simulation and AI work before adding
   those tools. Record audited writes and apply per-user rate and compute limits.
5. Deploy a stable HTTPS `/mcp` endpoint, run authorization and tenant-isolation
   tests, then test a real connection from Claude and ChatGPT before listing it.

`Supabase Auth` is a proposed Track B component in the deployment plan, not a
feature already implemented in this checkout. No subscription or usage ledger
is present here yet.

## Why no DeliR DSL yet

MCP is the interface to agents; a compact process notation is a separate
representation decision. The existing BPMN canvas has a richer XML contract,
including extensions and diagram data. A compact format must be evaluated
against realistic models for round-trip information loss, semantic correctness,
token use, latency, and edit success before it can replace XML in an MCP tool.
Atomic changes can already avoid resending the entire model for a simple rename.

## References

- [MCP Python SDK: running a server](https://py.sdk.modelcontextprotocol.io/run/)
- [MCP Python SDK: authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/)
- [Cursor MCP configuration](https://cursor.com/docs/mcp)
- [Claude custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [ChatGPT custom MCP servers](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
