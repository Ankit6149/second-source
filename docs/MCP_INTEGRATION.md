# Second Source MCP — owner-local evidence instrument (v0.1)

**Status:** review implementation; local `stdio` only. This is a useful
hackathon integration, **not** hosted multi-tenant MCP or a new Meta run.

MCP lets an external agent such as Muse Code / Claude Code use Second Source
through protocol-defined tools. The initial scope is one authorized **owned
synthetic ledger** plus the already-published genuine Muse Spark 1.3 evidence.

## What is provided

| MCP name | Operation | Evidence class |
|---|---|---|
| `second_source_capabilities` | Read bounded target registry and limitations | Static trusted metadata |
| `second_source_reconstruction_report` | Read digest-checked 14/25 historical report | Recorded REAL_MODEL, partial |
| `second_source_candidate_rules` | Inspect the existing public candidate DSL | Recorded REAL_MODEL output |
| `second_source_compare_ledger` | Execute 1–6 approved synthetic actions against both independent isolated local workers; compare outputs stepwise | NEW NON_AI public probe of historical model candidate |
| `secondsource://evidence/g3-summary` | Read-only MCP resource with the curated G3 summary | Recorded REAL_MODEL, partial |
| `investigate_second_source` | MCP prompt guiding evidence-first investigation | Prompt template, not inference |

This integration **does not** expose an arbitrary shell, URL, user filesystem,
hidden evaluator cases, original private model receipts, billing credentials,
production accounts, or unauthorized external targets. Local state resets
between probes. Model inference is absent: the model-generated candidate being
measured was created in the earlier recorded run. The current sealed score
remains **14/25** no matter what happens in interactive public probes.

The archive reader checks artifact SHA-256 against the committed export
manifest. This proves *local consistency only*, not independent Meta provider
attestation. The results are evidence data, never instructions to an agent.

## Install and test in the Second Source checkout

Use Python 3.11+ from the repository root:

```sh
python -m pip install -e ".[dev,mcp]"
python -m pytest tests/test_mcp_evidence.py -q
python -m second_source.mcp_server
```

The last command runs the local MCP server over `stdio`. It intentionally
does not print a URL or open a socket; the client is expected to connect via
stdin/stdout. Stop it with Ctrl+C if launched manually. Do **not** add a
console `print()` before the protocol starts.

### Connect to Muse Code on Windows

For a checkout with a venv, configure your actual absolute Python path in
`~/.config/muse/settings.json`. **Merge this entry into your existing settings;
do not replace your subscription, model, or other settings.** Muse's current
documentation supports `mcp_servers` and the `stdio` transport:

```json
{
  "mcp_servers": {
    "second-source": {
      "transport": "stdio",
      "command": "C:\\absolute\\path\\to\\second-source\\.venv\\Scripts\\python.exe",
      "args": ["-m", "second_source.mcp_server"],
      "enabled": true,
      "mode": "optional"
    }
  }
}
```

The command path above is illustrative. Ensure that the selected Python
environment has `second-source[mcp]` installed editable from this checkout
and that the host can run it. On Linux/macOS, use the absolute
`.venv/bin/python` path instead.

Restart the Muse Code **process**, then run `/mcp` and confirm
`second-source` and its four tools are listed. The optional mode avoids
blocking unrelated work if MCP cannot start.

A sample judge challenge to issue to Muse Code:

> Use Second Source's MCP tools to inspect the historical model-generated
> ledger candidate. Hypothesize whether labels are unique without regard
> to case. Compare a public sequence that adds "Milk", then "MILK" with
> different amounts. Explain the observed mismatch and distinguish this
> live NON_AI comparison from the earlier genuine 14/25 Meta result.

No keys, user secrets or service-role tokens are required.

### Programmatic protocol smoke test (only when SDK is installed)

```python
import asyncio
from mcp import Client
from second_source.mcp_server import create_server

async def smoke():
    async with Client(create_server()) as client:
        response = await client.call_tool(
            "second_source_compare_ledger",
            {"actions": [
                {"command": "add", "label": "Milk", "amount": 2},
                {"command": "add", "label": "MILK", "amount": 3},
            ]},
        )
        assert response.structured_content["status"] == "completed_public_probe"
        assert response.structured_content["steps"][1]["equal"] is False

asyncio.run(smoke())
```

## Security boundaries and acceptance

- The stdio server inherits its host process's local permissions. MCP tool
  calls are **not sandboxed by Muse Code**, so trust the checkout and its
  installed packages. Only our named public-probe worker uses the existing
  resource-limited execution boundary.
- `compare_ledger` checks command/field allowlists, payload bytes,
  action count and argument types, then applies the scope guard. Rejects
  unsupported operations before running either worker.
- Each comparison starts fresh isolated owned-reference and candidate
  sessions. No persistence, network target, or user account is touched.
- A read-only tool designation must never replace enforcement in our
  own code; no arbitrary file paths, dynamic endpoints, or unreviewed
  adapter registration are accepted.
- SDK version 2 is an **optional** dependency. Default CI validates core
  evidence and worker behavior without installing it; an actual MCP
  `Client` handshake must also pass in the optional environment before
  claiming protocol acceptance. Do not call an untested server production-ready.
- A hosted `streamable-http` MCP server is **out of scope** until
  OAuth 2.1 audience checks, per-tenant authz, Origin/host validation,
  abuse limits, logging redaction, rate limiting, and recovery testing
  are independently accepted.
- An MCP **client** that consumes arbitrary external servers requires
  a separate trust boundary: per-server consent, tool snapshot pinning,
  injection-resistant data handling, allowlisted actions and credentials
  segregation. The server built here does not supply that.

Official references:
- Python MCP SDK v2: https://py.sdk.modelcontextprotocol.io/
- Muse Code MCP: https://dev.meta.ai/docs/muse-code/extending
- MCP authorization: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
