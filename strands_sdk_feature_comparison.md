# Strands SDK Feature Comparison: Python vs TypeScript

## Table of Contents
1. [Features with Equivalent Implementation](#1-features-with-equivalent-implementation)
2. [Features Implemented Differently](#2-features-implemented-differently)
3. [Python SDK Exclusive Features](#3-python-sdk-exclusive-features)
4. [TypeScript SDK Exclusive Features](#4-typescript-sdk-exclusive-features)
5. [Implementation Pattern Analysis](#5-implementation-pattern-analysis)
6. [API Surface Comparison](#6-api-surface-comparison)

---

## 1. Features with Equivalent Implementation

These features exist in both SDKs with similar functionality and API design, accounting for language differences.

### 1.1 Core Agent Functionality

#### ✅ Agent Instantiation
Both SDKs provide similar agent creation patterns:

**Python:**
```python
from strands import Agent
from strands.models import BedrockModel

agent = Agent(
    model=BedrockModel(model_id="claude-3-sonnet"),
    tools=[tool1, tool2],
    system_prompt="You are helpful"
)
```

**TypeScript:**
```typescript
import { Agent, BedrockModel } from '@strands-agents/sdk'

const agent = new Agent({
  model: new BedrockModel({ modelId: 'claude-3-sonnet' }),
  tools: [tool1, tool2],
  systemPrompt: 'You are helpful'
})
```

#### ✅ Basic Agent Invocation
Both support text-based agent calls:

**Python:**
```python
result = agent("What's the weather?")
# or async
result = await agent.invoke_async("What's the weather?")
```

**TypeScript:**
```typescript
const result = await agent.invoke("What's the weather?")
```

#### ✅ Message History Access
Both provide access to conversation messages:

**Python:**
```python
messages = agent.messages  # List[Message]
```

**TypeScript:**
```typescript
const messages = agent.messages  // Message[]
```

#### ✅ Agent State Management
Both provide stateful storage:

**Python:**
```python
agent.state.set("key", "value")
value = agent.state.get("key")
```

**TypeScript:**
```typescript
agent.state.set("key", "value")
const value = agent.state.get("key")
```

### 1.2 Bedrock Model Provider

#### ✅ Basic Bedrock Configuration
Both support similar Bedrock model configuration:

**Python:**
```python
model = BedrockModel(
    model_id="claude-3-sonnet",
    max_tokens=1000,
    temperature=0.7
)
```

**TypeScript:**
```typescript
const model = new BedrockModel({
  modelId: 'claude-3-sonnet',
  maxTokens: 1000,
  temperature: 0.7
})
```

#### ✅ Bedrock Streaming
Both implement streaming responses:

**Python:**
```python
async for event in agent.stream_async("Hello"):
    if event.get("data"):
        print(event["data"])
```

**TypeScript:**
```typescript
for await (const event of agent.stream("Hello")) {
  if (event.type === 'modelContentBlockDeltaEvent') {
    console.log(event.delta)
  }
}
```

#### ✅ Bedrock Error Handling
Both handle context window overflow and throttling:

**Python:**
```python
from strands.types.exceptions import ContextWindowOverflowException

try:
    result = agent("long prompt")
except ContextWindowOverflowException:
    # Handle context overflow
```

**TypeScript:**
```typescript
import { ContextWindowOverflowError } from '@strands-agents/sdk'

try {
  const result = await agent.invoke("long prompt")
} catch (error) {
  if (error instanceof ContextWindowOverflowError) {
    // Handle context overflow
  }
}
```

### 1.3 Content and Message Types

#### ✅ Text Content Blocks
Both support text content:

**Python:**
```python
content_block = {"text": "Hello world"}
```

**TypeScript:**
```typescript
const contentBlock = new TextBlock("Hello world")
```

#### ✅ Multi-modal Content
Both support images, videos, and documents:

**Python:**
```python
image_block = {
    "image": {
        "format": "png",
        "source": {"bytes": image_bytes}
    }
}
```

**TypeScript:**
```typescript
const imageBlock = new ImageBlock({
  format: 'png',
  source: { type: 'imageSourceBytes', bytes: imageBytes }
})
```

#### ✅ Message Roles
Both support user/assistant message roles:

**Python:**
```python
message = {
    "role": "user",
    "content": [{"text": "Hello"}]
}
```

**TypeScript:**
```typescript
const message = new Message({
  role: 'user',
  content: [new TextBlock('Hello')]
})
```

### 1.4 Tool System Core

#### ✅ Tool Specification Format
Both use similar tool spec structures:

**Python:**
```python
tool_spec = {
    "name": "calculator",
    "description": "Performs calculations",
    "inputSchema": {"json": schema}
}
```

**TypeScript:**
```typescript
const toolSpec: ToolSpec = {
  name: 'calculator',
  description: 'Performs calculations',
  inputSchema: schema
}
```

#### ✅ Tool Use/Result Flow
Both implement the same tool use/result pattern:

**Python:**
```python
# Tool use from model
tool_use = {
    "name": "calculator",
    "toolUseId": "123",
    "input": {"operation": "add", "a": 2, "b": 3}
}

# Tool result back to model
tool_result = {
    "toolUseId": "123",
    "status": "success",
    "content": [{"text": "5"}]
}
```

**TypeScript:**
```typescript
// Tool use from model
const toolUse: ToolUse = {
  name: 'calculator',
  toolUseId: '123',
  input: { operation: 'add', a: 2, b: 3 }
}

// Tool result back to model
const toolResult = new ToolResultBlock({
  toolUseId: '123',
  status: 'success',
  content: [new TextBlock('5')]
})
```

### 1.5 Hook System

#### ✅ Hook Event Types
Both support similar hook events:

**Python:**
```python
from strands.hooks import BeforeInvocationEvent, AfterInvocationEvent

def my_hook(event):
    if isinstance(event, BeforeInvocationEvent):
        print("Starting invocation")

agent.hooks.add_hook(my_hook)
```

**TypeScript:**
```typescript
import { BeforeInvocationEvent, AfterInvocationEvent } from '@strands-agents/sdk'

const myHook = {
  async onBeforeInvocation(event: BeforeInvocationEvent) {
    console.log('Starting invocation')
  }
}

agent.hooks.addHook(myHook)
```

### 1.6 Conversation Management

#### ✅ Sliding Window Manager
Both provide sliding window conversation management:

**Python:**
```python
from strands.agent.conversation_manager import SlidingWindowConversationManager

manager = SlidingWindowConversationManager(window_size=20)
agent = Agent(conversation_manager=manager)
```

**TypeScript:**
```typescript
import { SlidingWindowConversationManager } from '@strands-agents/sdk'

const manager = new SlidingWindowConversationManager({ windowSize: 20 })
const agent = new Agent({ conversationManager: manager })
```

---

## 2. Features Implemented Differently

These features exist in both SDKs but have different implementation approaches or APIs.

### 2.1 Tool Definition and Creation

#### 🔄 Tool Definition Syntax

**Python: Decorator-Based with Introspection**
```python
from strands import tool

@tool
def calculator(operation: str, a: float, b: float) -> dict:
    """Performs basic arithmetic operations.
    
    Args:
        operation: The operation to perform (add, subtract, multiply, divide)
        a: First number
        b: Second number
    
    Returns:
        Calculation result
    """
    if operation == "add":
        result = a + b
    # ... other operations
    
    return {
        "status": "success",
        "content": [{"text": f"Result: {result}"}]
    }

# Usage
agent = Agent(tools=[calculator])
```

**TypeScript: Schema-First with Zod**
```typescript
import { tool } from '@strands-agents/sdk'
import { z } from 'zod'

const calculator = tool({
  name: 'calculator',
  description: 'Performs basic arithmetic operations',
  inputSchema: z.object({
    operation: z.enum(['add', 'subtract', 'multiply', 'divide']),
    a: z.number(),
    b: z.number()
  }),
  callback: (input) => {
    let result: number
    switch (input.operation) {
      case 'add': result = input.a + input.b; break
      // ... other operations
    }
    return { result }
  }
})

// Usage
const agent = new Agent({ tools: [calculator] })
```

**Key Differences:**
- Python extracts metadata from docstrings and type hints
- TypeScript requires explicit schema definition
- Python supports both direct function calls and tool use
- TypeScript has separate `invoke()` method for direct calls

#### 🔄 Tool Context Access

**Python: Automatic Injection**
```python
@tool(context=True)
def my_tool(param: str, tool_context: ToolContext) -> dict:
    agent = tool_context.agent
    tool_use_id = tool_context.tool_use["toolUseId"]
    return {"status": "success", "content": [{"text": f"Used by {agent.name}"}]}
```

**TypeScript: Explicit Parameter**
```typescript
const myTool = tool({
  name: 'my_tool',
  inputSchema: z.object({ param: z.string() }),
  callback: (input, context) => {
    const agent = context?.agent
    const toolUseId = context?.toolUse.toolUseId
    return { result: `Used by ${agent?.constructor.name}` }
  }
})
```

### 2.2 Agent Invocation Patterns

#### 🔄 Synchronous vs Asynchronous

**Python: Dual Sync/Async Support**
```python
# Synchronous (blocks thread)
result = agent("What's 2+2?")

# Asynchronous
result = await agent.invoke_async("What's 2+2?")

# Streaming
async for event in agent.stream_async("What's 2+2?"):
    print(event)
```

**TypeScript: Async-Only**
```typescript
// All operations are async
const result = await agent.invoke("What's 2+2?")

// Streaming (primary interface)
for await (const event of agent.stream("What's 2+2?")) {
  console.log(event)
}
```

#### 🔄 Direct Tool Access

**Python: Agent Tool Proxy**
```python
# Direct tool access through agent
result = agent.tool.calculator(operation="add", a=2, b=2)

# Returns tool result format
# {"toolUseId": "...", "status": "success", "content": [...]}
```

**TypeScript: Tool Registry Access**
```typescript
// Access through registry
const calc = agent.tools.find(t => t.name === 'calculator')
const result = await calc?.invoke({ operation: 'add', a: 2, b: 2 })

// Returns unwrapped result
// { result: 4 }
```

### 2.3 Input Format Handling

#### 🔄 Multi-format Input Support

**Python: Auto-detection**
```python
# String input
result = agent("Hello")

# ContentBlock list
result = agent([{"text": "Hello"}])

# Message list  
result = agent([{"role": "user", "content": [{"text": "Hello"}]}])
```

**TypeScript: Type-based Overloads**
```typescript
// String input
const result1 = await agent.invoke("Hello")

// ContentBlock array
const result2 = await agent.invoke([new TextBlock("Hello")])

// Message array
const result3 = await agent.invoke([
  new Message({ role: 'user', content: [new TextBlock("Hello")] })
])
```

### 2.4 Configuration Patterns

#### 🔄 Agent Configuration

**Python: Keyword Arguments**
```python
agent = Agent(
    model=BedrockModel(model_id="claude-3-sonnet"),
    tools=[tool1, tool2],
    system_prompt="You are helpful",
    conversation_manager=SlidingWindowConversationManager(),
    callback_handler=PrintingCallbackHandler(),
    record_direct_tool_call=True,
    load_tools_from_directory=False,
    # ... many more options
)
```

**TypeScript: Configuration Object**
```typescript
const agent = new Agent({
  model: new BedrockModel({ modelId: 'claude-3-sonnet' }),
  tools: [tool1, tool2],
  systemPrompt: 'You are helpful',
  conversationManager: new SlidingWindowConversationManager(),
  printer: true,
  hooks: [hook1, hook2]
})
```

### 2.5 Content Block Handling

#### 🔄 Content Block Structure

**Python: TypedDict with Optional Fields**
```python
# Single dictionary type with optional fields
content_block = {
    "text": "Hello",           # Optional
    "toolUse": {...},         # Optional
    "toolResult": {...},      # Optional
    # Only one field should be present
}

# Type checking at runtime
if "text" in content_block:
    text = content_block["text"]
```

**TypeScript: Discriminated Union Types**
```typescript
// Specific types with discriminators
type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock

// Type checking at compile time
if (block.type === 'textBlock') {
  const text = block.text  // TypeScript knows this is TextBlock
}
```

### 2.6 Error Handling

#### 🔄 Error Types and Patterns

**Python: Exception Hierarchy**
```python
from strands.types.exceptions import (
    ContextWindowOverflowException,
    ModelThrottledException
)

try:
    result = agent("prompt")
except ContextWindowOverflowException as e:
    # Handle context overflow
    print(f"Context overflow: {e}")
except ModelThrottledException as e:
    # Handle throttling
    print(f"Throttled: {e}")
```

**TypeScript: Error Classes with instanceof**
```typescript
import { 
  ContextWindowOverflowError,
  MaxTokensError 
} from '@strands-agents/sdk'

try {
  const result = await agent.invoke("prompt")
} catch (error) {
  if (error instanceof ContextWindowOverflowError) {
    console.log(`Context overflow: ${error.message}`)
  } else if (error instanceof MaxTokensError) {
    console.log(`Max tokens: ${error.message}`)
  }
}
```

---

## 3. Python SDK Exclusive Features

Features that exist only in the Python SDK.

### 3.1 Multiple Model Providers

#### 🐍 OpenAI Provider
```python
from strands.models import OpenAIModel

model = OpenAIModel(
    model_id="gpt-4",
    api_key="your-key"
)
agent = Agent(model=model)
```

#### 🐍 Anthropic Provider
```python
from strands.models import AnthropicModel

model = AnthropicModel(
    model_id="claude-3-sonnet",
    api_key="your-key"
)
agent = Agent(model=model)
```

#### 🐍 LiteLLM Provider (Multi-provider support)
```python
from strands.models import LiteLLMModel

model = LiteLLMModel(
    model_id="gpt-4",  # or any LiteLLM supported model
    api_key="your-key"
)
agent = Agent(model=model)
```

#### 🐍 Ollama Provider (Local models)
```python
from strands.models import OllamaModel

model = OllamaModel(
    model_id="llama2",
    host="http://localhost:11434"
)
agent = Agent(model=model)
```

### 3.2 Experimental Features

#### 🐍 Bidirectional Communication (Bidi)
```python
from strands.experimental.bidi import BidiAgent

bidi_agent = BidiAgent(
    model=BedrockModel(),
    tools=[tool1, tool2]
)

# Real-time bidirectional communication
async for message in bidi_agent.listen():
    response = await bidi_agent.respond(message)
```

#### 🐍 Agent-to-Agent Communication (A2A)
```python
from strands.experimental.a2a import A2AAgent

agent1 = A2AAgent(name="agent1", model=BedrockModel())
agent2 = A2AAgent(name="agent2", model=BedrockModel())

# Direct agent communication
response = await agent1.communicate_with(agent2, "Hello from agent1")
```

#### 🐍 Advanced Steering
```python
from strands.experimental.steering import SteeringAgent
from strands.experimental.steering.context_providers import RAGContextProvider

steering_agent = SteeringAgent(
    base_model=BedrockModel(),
    context_providers=[RAGContextProvider(...)],
    steering_config=SteeringConfig(...)
)
```

### 3.3 Advanced Tool Features

#### 🐍 Hot Reloading from Directory
```python
agent = Agent(
    model=BedrockModel(),
    load_tools_from_directory=True  # Auto-loads from ./tools/
)

# Tools are automatically reloaded when files change
```

#### 🐍 MCP (Model Context Protocol) Support
```python
from strands.tools.mcp import MCPClient

mcp_client = MCPClient("stdio", command=["python", "my_mcp_server.py"])
agent = Agent(
    model=BedrockModel(),
    tools=[mcp_client]  # MCP tools automatically loaded
)
```

#### 🐍 Complex Tool Execution Strategies
```python
from strands.tools.executors import ConcurrentToolExecutor, SequentialToolExecutor

# Concurrent execution
agent = Agent(
    model=BedrockModel(),
    tools=[tool1, tool2, tool3],
    tool_executor=ConcurrentToolExecutor(max_workers=3)
)

# Sequential execution
agent = Agent(
    model=BedrockModel(),
    tools=[tool1, tool2, tool3],
    tool_executor=SequentialToolExecutor()
)
```

### 3.4 Session Management

#### 🐍 Persistent Sessions
```python
from strands.session import SessionManager

session_manager = SessionManager(
    storage_backend="redis",  # or "file", "memory"
    connection_string="redis://localhost:6379"
)

agent = Agent(
    model=BedrockModel(),
    session_manager=session_manager,
    agent_id="user-123-agent"
)

# Conversations and state persist across invocations
```

### 3.5 Structured Output

#### 🐍 Pydantic Model Integration
```python
from pydantic import BaseModel
from strands import Agent

class WeatherInfo(BaseModel):
    temperature: float
    conditions: str
    humidity: int

agent = Agent(
    model=BedrockModel(),
    structured_output_model=WeatherInfo
)

# Returns structured output
weather = agent("What's the weather in NYC?")  # Returns WeatherInfo instance
print(f"Temperature: {weather.temperature}°F")
```

#### 🐍 Legacy Structured Output Method
```python
weather = agent.structured_output(
    WeatherInfo,
    "What's the weather in NYC?"
)
```

### 3.6 Advanced Configuration Options

#### 🐍 Callback Handlers
```python
from strands.handlers import PrintingCallbackHandler, CustomCallbackHandler

def my_callback(event_type, **kwargs):
    print(f"Event: {event_type}, Data: {kwargs}")

agent = Agent(
    model=BedrockModel(),
    callback_handler=my_callback
)
```

#### 🐍 Trace Attributes
```python
agent = Agent(
    model=BedrockModel(),
    trace_attributes={
        "environment": "production",
        "user_id": "user-123",
        "session_id": "session-456"
    }
)
```

#### 🐍 Direct Tool Call Recording
```python
agent = Agent(
    model=BedrockModel(),
    record_direct_tool_call=False  # Don't record direct tool calls in history
)
```

---

## 4. TypeScript SDK Exclusive Features

Features that exist only in the TypeScript SDK.

### 4.1 Vended Tools (Built-in Tools)

#### 🔷 Bash Tool
```typescript
import { bashTool } from '@strands-agents/sdk/vended_tools/bash'

const agent = new Agent({
  model: new BedrockModel(),
  tools: [bashTool]
})

// Can execute shell commands
const result = await agent.invoke("List files in current directory")
```

#### 🔷 File Editor Tool
```typescript
import { fileEditorTool } from '@strands-agents/sdk/vended_tools/file_editor'

const agent = new Agent({
  model: new BedrockModel(),
  tools: [fileEditorTool]
})

// Can read, write, and edit files
const result = await agent.invoke("Create a new Python file with hello world")
```

#### 🔷 HTTP Request Tool
```typescript
import { httpRequestTool } from '@strands-agents/sdk/vended_tools/http_request'

const agent = new Agent({
  model: new BedrockModel(),
  tools: [httpRequestTool]
})

// Can make HTTP requests
const result = await agent.invoke("Get the weather from httpbin.org/json")
```

#### 🔷 Notebook Tool (Jupyter Integration)
```typescript
import { notebookTool } from '@strands-agents/sdk/vended_tools/notebook'

const agent = new Agent({
  model: new BedrockModel(),
  tools: [notebookTool]
})

// Can execute Jupyter notebook cells
const result = await agent.invoke("Calculate 2+2 in a notebook cell")
```

### 4.2 Superior Type Safety Features

#### 🔷 Compile-time Type Checking
```typescript
// TypeScript catches errors at compile time
const tool = tool({
  name: 'calculator',
  inputSchema: z.object({
    a: z.number(),
    b: z.number()
  }),
  callback: (input) => {
    // TypeScript knows input.a and input.b are numbers
    return { result: input.a + input.b }
  }
})

// This would cause a compile error:
// return { result: input.a + input.c }  // Error: Property 'c' does not exist
```

#### 🔷 Generic Type Safety
```typescript
// Tool with specific input/output types
const calculator = tool({
  name: 'calculator',
  inputSchema: z.object({ a: z.number(), b: z.number() }),
  callback: (input): { result: number } => {
    return { result: input.a + input.b }
  }
})

// TypeScript infers the correct return type
const result = await calculator.invoke({ a: 2, b: 3 })
// result is typed as { result: number }
```

#### 🔷 Better IDE Integration
```typescript
// Autocompletion works perfectly
agent.stream("Hello")  // IDE shows all available methods
     .then(events => {
       for await (const event of events) {
         if (event.type === 'model') {  // IDE suggests available event types
           // Autocomplete works here too
         }
       }
     })
```

### 4.3 Cleaner Async Patterns

#### 🔷 Consistent Async/Await
```typescript
// Everything is async/await - no sync/async bridge confusion
const agent = new Agent({ model: new BedrockModel() })

const result = await agent.invoke("Hello")
const events = agent.stream("Hello")  // Returns AsyncIterable

for await (const event of events) {
  // Handle events
}
```

#### 🔷 Generator-based Streaming
```typescript
// Clean generator pattern for streaming
async function* processAgentStream(prompt: string) {
  for await (const event of agent.stream(prompt)) {
    if (event.type === 'modelContentBlockDeltaEvent') {
      yield event.delta
    }
  }
}

// Usage
for await (const delta of processAgentStream("Hello")) {
  console.log(delta)
}
```

### 4.4 Advanced Zod Integration

#### 🔷 Schema Composition
```typescript
import { z } from 'zod'

const baseInputSchema = z.object({
  apiKey: z.string(),
  retries: z.number().default(3)
})

const weatherTool = tool({
  name: 'weather',
  inputSchema: baseInputSchema.extend({
    location: z.string(),
    units: z.enum(['celsius', 'fahrenheit']).default('celsius')
  }),
  callback: (input) => {
    // input has all fields from baseInputSchema + extended fields
    return { temperature: 25, units: input.units }
  }
})
```

#### 🔷 Runtime Validation with Better Errors
```typescript
const tool = tool({
  name: 'calculator',
  inputSchema: z.object({
    operation: z.enum(['add', 'subtract']),
    a: z.number().min(0),
    b: z.number().max(100)
  }),
  callback: (input) => input.a + input.b
})

// Provides detailed validation errors
try {
  await tool.invoke({ operation: 'multiply', a: -1, b: 200 })
} catch (error) {
  // Error includes specific field validation failures
}
```

### 4.5 Modern JavaScript Features

#### 🔷 Disposable Pattern Support
```typescript
class DisposableAgent {
  private agent: Agent

  constructor(config: AgentConfig) {
    this.agent = new Agent(config)
  }

  [Symbol.dispose]() {
    // Cleanup resources
    this.agent.cleanup()
  }
}

// Usage with using declaration (when supported)
using agent = new DisposableAgent({ model: new BedrockModel() })
// Automatically disposed at end of scope
```

#### 🔷 Template Literal Types (Future)
```typescript
// Potential future feature with template literal types
type ModelId = `anthropic.claude-${string}` | `openai.gpt-${string}`

const model = new BedrockModel({
  modelId: 'anthropic.claude-3-sonnet' // Type checked
})
```

### 4.6 Browser Compatibility

#### 🔷 Web Browser Support
```typescript
// Works in browser environments
import { Agent, BedrockModel } from '@strands-agents/sdk'

// Browser-compatible streaming
const agent = new Agent({
  model: new BedrockModel({
    region: 'us-west-2',
    // Browser credentials via AWS SDK
    credentials: {
      accessKeyId: 'your-access-key',
      secretAccessKey: 'your-secret-key'
    }
  })
})
```

---

## 5. Implementation Pattern Analysis

### 5.1 Type System Approaches

#### Python: Duck Typing with Runtime Validation
```python
# Flexible but runtime errors
def process_content(content: ContentBlock) -> str:
    if "text" in content:
        return content["text"]
    elif "toolUse" in content:
        return f"Tool: {content['toolUse']['name']}"
    else:
        return "Unknown content"

# Runtime error if content structure is wrong
```

#### TypeScript: Static Typing with Compile-time Safety
```typescript
// Compile-time safety
function processContent(content: ContentBlock): string {
  switch (content.type) {
    case 'textBlock':
      return content.text  // TypeScript knows this is valid
    case 'toolUseBlock':
      return `Tool: ${content.name}`
    default:
      return 'Unknown content'
  }
}

// Compile-time error if content structure is wrong
```

### 5.2 Error Handling Patterns

#### Python: Exception-based with Context
```python
try:
    result = agent("Hello")
except ContextWindowOverflowException as e:
    # Rich exception with context
    print(f"Overflow in region {e.region} with model {e.model_id}")
    # Can inspect e.context for more details
except Exception as e:
    print(f"Unexpected error: {e}")
```

#### TypeScript: Error Objects with instanceof
```typescript
try {
  const result = await agent.invoke("Hello")
} catch (error) {
  if (error instanceof ContextWindowOverflowError) {
    console.log(`Overflow: ${error.message}`)
    console.log(`Model: ${error.modelId}`)
  } else {
    console.log(`Unexpected error: ${error}`)
  }
}
```

### 5.3 Configuration Patterns

#### Python: Keyword Arguments with Defaults
```python
# Many optional parameters with defaults
agent = Agent(
    model=BedrockModel(),
    tools=None,  # Optional
    system_prompt=None,  # Optional
    callback_handler=_DEFAULT_CALLBACK_HANDLER,  # Default sentinel
    conversation_manager=None,  # Gets default if None
    # ... 15+ more optional parameters
)
```

#### TypeScript: Configuration Objects with Partial Types
```typescript
// Clean configuration object
interface AgentConfig {
  model?: Model
  tools?: ToolList
  systemPrompt?: SystemPrompt
  printer?: boolean
  // ... fewer, more focused options
}

const agent = new Agent({
  model: new BedrockModel(),
  tools: [tool1, tool2],
  systemPrompt: 'You are helpful'
  // Only specify what you need
})
```

### 5.4 Async Pattern Differences

#### Python: Sync/Async Bridge
```python
# Synchronous wrapper
def sync_invoke(prompt: str) -> AgentResult:
    return run_async(lambda: agent.invoke_async(prompt))

# Internal async implementation
async def invoke_async(prompt: str) -> AgentResult:
    # Actual implementation
    pass

# Threading bridge for streaming
def stream_sync(prompt: str) -> Iterator[Dict]:
    queue = Queue()
    thread = Thread(target=lambda: asyncio.run(
        self._stream_to_queue(prompt, queue)
    ))
    thread.start()
    # ... yield from queue
```

#### TypeScript: Pure Async
```typescript
// Single async implementation
async invoke(prompt: string): Promise<AgentResult> {
  // Direct implementation, no sync bridge needed
}

// Native async generators
async *stream(prompt: string): AsyncGenerator<AgentStreamEvent> {
  // Direct async generator implementation
}
```

---

## 6. API Surface Comparison

### 6.1 Agent Class Methods

#### Python Agent API
```python
class Agent:
    # Core invocation
    def __call__(self, prompt=None, **kwargs) -> AgentResult
    async def invoke_async(self, prompt=None, **kwargs) -> AgentResult
    async def stream_async(self, prompt=None, **kwargs) -> AsyncIterator[Any]
    
    # Structured output (deprecated)
    def structured_output(self, model, prompt=None) -> T
    async def structured_output_async(self, model, prompt=None) -> T
    
    # Direct tool access
    @property
    def tool(self) -> ToolCaller  # agent.tool.tool_name()
    
    # Properties
    @property
    def system_prompt(self) -> str | None
    @system_prompt.setter
    def system_prompt(self, value) -> None
    
    @property
    def tool_names(self) -> list[str]
    
    # State and messages
    messages: Messages
    state: AgentState
    
    # Configuration
    model: Model
    conversation_manager: ConversationManager
    hooks: HookRegistry
    
    # Cleanup
    def cleanup(self) -> None
```

#### TypeScript Agent API
```typescript
class Agent {
  // Core invocation (async only)
  async invoke(args: InvokeArgs): Promise<AgentResult>
  stream(args: InvokeArgs): AsyncGenerator<AgentStreamEvent, AgentResult>
  
  // Properties (readonly)
  readonly messages: Message[]
  readonly state: AgentState
  readonly conversationManager: HookProvider
  readonly hooks: HookRegistryImplementation
  
  // Configuration
  model: Model
  systemPrompt?: SystemPrompt
  
  // Tool access
  get tools(): Tool[]
  get toolRegistry(): ToolRegistry
  
  // Initialization
  async initialize(): Promise<void>
}
```

### 6.2 Model Provider APIs

#### Python BedrockModel
```python
class BedrockModel(Model):
    def __init__(self, 
                 boto_session=None,
                 boto_client_config=None,
                 region_name=None,
                 endpoint_url=None,
                 **model_config)
    
    def update_config(self, **model_config) -> None
    def get_config(self) -> BedrockConfig
    
    async def stream(self, messages, tool_specs=None, system_prompt=None, 
                    *, tool_choice=None, system_prompt_content=None, **kwargs) -> AsyncGenerator[StreamEvent, None]
    
    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]
```

#### TypeScript BedrockModel
```typescript
class BedrockModel extends Model<BedrockModelConfig> {
  constructor(options?: BedrockModelOptions)
  
  updateConfig(modelConfig: BedrockModelConfig): void
  getConfig(): BedrockModelConfig
  
  stream(messages: Message[], options?: StreamOptions): AsyncIterable<ModelStreamEvent>
}
```

### 6.3 Tool Definition APIs

#### Python Tool Decorator
```python
# Decorator with multiple options
@tool(description="Custom desc", name="custom_name", context=True)
def my_tool(param: str, tool_context: ToolContext) -> dict:
    return {"status": "success", "content": [{"text": result}]}

# Tool interface
class AgentTool(ABC):
    @property
    @abstractmethod
    def tool_name(self) -> str: ...
    
    @property  
    @abstractmethod
    def tool_spec(self) -> ToolSpec: ...
    
    @abstractmethod
    async def stream(self, tool_use: ToolUse, invocation_state: dict) -> ToolGenerator: ...
```

#### TypeScript Tool Factory
```typescript
// Factory function with Zod
const myTool = tool({
  name: 'my_tool',
  description: 'Custom description',
  inputSchema: z.object({ param: z.string() }),
  callback: (input, context?) => ({ result: input.param })
})

// Tool interface
abstract class Tool {
  abstract get name(): string
  abstract get description(): string
  abstract get toolSpec(): ToolSpec
  abstract stream(toolContext: ToolContext): ToolStreamGenerator
}
```

---

## Summary

### Feature Parity Matrix

| Feature Category | Python SDK | TypeScript SDK | Implementation Difference |
|------------------|------------|----------------|--------------------------|
| **Core Agent** | ✅ Full | ✅ Full | Sync/Async vs Async-only |
| **Bedrock Model** | ✅ Full | ✅ Full | Similar APIs |
| **Basic Tools** | ✅ Full | ✅ Full | Decorator vs Factory |
| **Content Blocks** | ✅ Full | ✅ Full | TypedDict vs Classes |
| **Streaming** | ✅ Full | ✅ Full | Callback vs Generator |
| **Hooks** | ✅ Full | ✅ Full | Similar APIs |
| **Conversation Mgmt** | ✅ Full | ✅ Full | Similar APIs |
| **Multi-model** | ✅ Full | ⚠️ Partial | Python has more providers |
| **Vended Tools** | ❌ None | ✅ Full | TS exclusive |
| **MCP Support** | ✅ Full | ❌ None | Python exclusive |
| **Session Management** | ✅ Full | ❌ None | Python exclusive |
| **Structured Output** | ✅ Full | ❌ None | Python exclusive |
| **Hot Reloading** | ✅ Full | ❌ None | Python exclusive |
| **Experimental** | ✅ Full | ❌ None | Python exclusive |

### Recommendations

1. **For Feature Parity**: TypeScript SDK could benefit from MCP support, additional model providers, and session management
2. **For Developer Experience**: Python SDK could adopt some of TypeScript's cleaner patterns
3. **For Type Safety**: Both could benefit from each other's approaches - Python could use more strict typing, TypeScript could learn from Python's flexibility
4. **For Tool Ecosystem**: Consider standardizing tool definition patterns across both SDKs

Both SDKs are well-designed for their target audiences, with Python emphasizing flexibility and comprehensive features, while TypeScript focuses on type safety and developer experience.