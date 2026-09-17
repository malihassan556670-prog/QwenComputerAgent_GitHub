# Architecture

The controller sends a compact conversation to Qwen3 8B through Ollama. Qwen returns JSON describing a tool call. The controller executes the tool and sends a structured success/failure result back to Qwen.

Every tool returns:

```json
{"success": true, "message": "..."}
```

or:

```json
{"success": false, "message": "..."}
```

A failed tool immediately terminates the current task.

Multiple adjacent JSON objects are recovered and converted into `MULTI_ACTION`.

For diagnostics, commands beginning with `!` are executed directly. Example:

```text
!ollama ps
```
