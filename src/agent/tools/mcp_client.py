# MCP Client - Standardized tool calling via MCP protocol
import json
import subprocess
import sys


class MCPClient:
    # MCP Client that connects to MCP Servers via stdio transport

    SERVERS = {
        "device": {
            "command": [sys.executable, "-m", "app.tools.mcp_servers.device_server"],
            "description": "Device status service",
        },
    }

    def __init__(self):
        self._processes = {}
        self._tool_registry = {}

    def discover(self, server_name):
        # Discover available tools from the server
        # Sends list_tools request, returns tool definitions
        if server_name not in self.SERVERS:
            return []
        if server_name in self._tool_registry:
            return self._tool_registry[server_name]

        cfg = self.SERVERS[server_name]
        proc = subprocess.Popen(
            cfg["command"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._processes[server_name] = proc

        request = json.dumps({"method": "list_tools"})
        stdout, _ = proc.communicate(input=request + "\n", timeout=5)

        try:
            response = json.loads(stdout.strip())
            tools = response.get("result", {}).get("tools", [])
            self._tool_registry[server_name] = tools
            return tools
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[MCP] discover failed: {e}")
            return []

    def call(self, server_name, tool_name, arguments):
        # Call a tool on the MCP Server
        # Returns text result or None
        if server_name not in self._processes:
            self.discover(server_name)
            if server_name not in self._processes:
                return None

        proc = self._processes[server_name]
        request = json.dumps(
            {
                "method": "call_tool",
                "params": {"name": tool_name, "arguments": arguments},
            },
            ensure_ascii=False,
        )

        try:
            stdout, _ = proc.communicate(input=request + "\n", timeout=10)
            response = json.loads(stdout.strip())
            texts = [c["text"] for c in response.get("result", {}).get("content", []) if c.get("type") == "text"]
            return "\n".join(texts) if texts else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            print(f"[MCP] call failed: {e}")
            return None

    def discover_all(self):
        # Discover tools from all registered servers
        registry = {}
        for name in self.SERVERS:
            tools = self.discover(name)
            if tools:
                registry[name] = tools
                print(f"[MCP] Discovered [{name}]: {[t['name'] for t in tools]}")
        return registry

    def close(self):
        # Close all MCP server connections
        for name, proc in self._processes.items():
            proc.terminate()
        self._processes.clear()
        self._tool_registry.clear()
