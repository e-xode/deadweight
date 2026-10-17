# Shop events (fictional)

#### Common fields

| Field | Required | Description |
| :- | :- | :- |
| `type` | yes | `"command"`, `"webhook"`, or `"agent"` |
| `timeout` | no | Seconds before giving up |

Events that support all three hook types (`command`, `webhook`, and `agent`):

* `OrderPlaced`

Events that support `command`, `http`, and `mcp_tool` hooks but not `prompt` or `agent`:

* `OrderShipped`

Events that support all five hook types (`command`, `http`, `mcp_tool`, `prompt`, and `agent`):

* `OrderPlaced`
* `CartEmptied`

### OrderPlaced

Runs when `OrderPlaced` fires.

### OrderShipped

Runs when `OrderShipped` fires.

### CartEmptied

Runs when `CartEmptied` fires.

### Exit code output

Not an event: no backticked name.
