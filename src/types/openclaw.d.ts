/**
 * Type stubs for OpenClaw Plugin SDK.
 * These will be replaced by actual types once OpenClaw is installed.
 */

declare module "openclaw/plugin-sdk/plugin-entry" {
  interface ToolContent {
    type: "text" | "image";
    text?: string;
    data?: string;
    mimeType?: string;
  }

  interface ToolResult {
    content: ToolContent[];
  }

  interface ToolDefinition {
    name: string;
    description: string;
    parameters: any;
    execute(id: string, params: any): Promise<ToolResult>;
  }

  interface PluginApi {
    registerTool(tool: ToolDefinition, options?: { optional?: boolean }): void;
    registerMediaUnderstandingProvider(provider: any): void;
    registerHook(hook: any): void;
    registerHttpRoute(route: any): void;
    registerCommand(command: any): void;
  }

  interface PluginEntry {
    id: string;
    name: string;
    description: string;
    register(api: PluginApi): void;
  }

  export function definePluginEntry(entry: PluginEntry): PluginEntry;
}
