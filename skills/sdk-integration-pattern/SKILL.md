---
name: sdk-integration-pattern
description: Common patterns for integrating external SDKs and libraries into existing projects. Covers authentication, error handling, configuration, and testing patterns that apply to most SDK integrations.
---

# SDK Integration Patterns

Reusable patterns for integrating external SDKs. These apply to most libraries and frameworks.

## Pattern 1: Configuration Management

**Problem**: SDKs need API keys, endpoints, and options. Where do you put them?

**Pattern**:
```
# Good: Centralized config
# config/sdk-name.ts
export const sdkConfig = {
  apiKey: process.env.SDK_API_KEY,
  baseUrl: process.env.SDK_BASE_URL ?? "https://api.default.com",
  timeout: 30_000,
  retries: 3,
} as const;

# Good: Validation at startup
# config/validate.ts
if (!sdkConfig.apiKey) {
  throw new Error("SDK_API_KEY environment variable is required");
}
```

**Anti-patterns**:
- API keys hardcoded in source files
- Config scattered across multiple files
- No validation of required config

## Pattern 2: Error Handling Wrapper

**Problem**: SDKs throw different error types. How do you handle them consistently?

**Pattern**:
```
# Good: Typed error wrapper
class SDKError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly statusCode?: number,
    public readonly originalError?: Error
  ) {
    super(message);
    this.name = "SDKError";
  }
}

async function safeSDKCall<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    if (error instanceof SDKError) throw error;
    throw new SDKError(
      "SDK operation failed",
      "SDK_ERROR",
      undefined,
      error as Error
    );
  }
}
```

**Anti-patterns**:
- Catching errors and returning null
- Generic try/catch with no context
- Different error handling per SDK call

## Pattern 3: Client Singleton

**Problem**: Creating new SDK clients on every request wastes resources.

**Pattern**:
```
# Good: Lazy singleton
let _client: SDKClient | null = null;

export function getSDKClient(): SDKClient {
  if (!_client) {
    _client = new SDKClient(sdkConfig);
  }
  return _client;
}

# Good: Dependency injection for testing
export function createSDKClient(config = sdkConfig): SDKClient {
  return new SDKClient(config);
}
```

**Anti-patterns**:
- Creating new client in every function
- Global mutable client variable
- No way to inject test doubles

## Pattern 4: Request/Response Logging

**Problem**: Hard to debug SDK issues without seeing what's sent/received.

**Pattern**:
```
# Good: Structured logging
const logger = createLogger("sdk:stripe");

async function makeSDKCall(operation: string, params: unknown) {
  logger.info({ operation, params }, "SDK call started");
  const start = Date.now();

  try {
    const result = await client.operation(params);
    logger.info({
      operation,
      duration: Date.now() - start,
      success: true
    }, "SDK call completed");
    return result;
  } catch (error) {
    logger.error({
      operation,
      duration: Date.now() - start,
      error: error.message
    }, "SDK call failed");
    throw error;
  }
}
```

## Pattern 5: Type-Safe Wrappers

**Problem**: SDK types don't match your project's domain types.

**Pattern**:
```
# Good: Adapter layer
// types/domain.ts
interface User {
  id: string;
  email: string;
  createdAt: Date;
}

// adapters/user-adapter.ts
function toDomainUser(sdkUser: SDKUser): User {
  return {
    id: sdkUser.id,
    email: sdkUser.email_address,
    createdAt: new Date(sdkUser.created * 1000),
  };
}

function toSDKUser(user: Partial<User>): Partial<SDKUser> {
  const result: Partial<SDKUser> = {};
  if (user.email) result.email_address = user.email;
  return result;
}
```

## Pattern 6: Retry with Backoff

**Problem**: SDK calls fail transiently. How do you retry safely?

**Pattern**:
```
# Good: Exponential backoff with jitter
async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries = 3,
  baseDelay = 1000
): Promise<T> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxRetries) throw error;
      if (!isRetryable(error)) throw error;

      const delay = baseDelay * Math.pow(2, attempt);
      const jitter = delay * 0.5 * Math.random();
      await sleep(delay + jitter);
    }
  }
  throw new Error("Unreachable");
}
```

**Only retry on**:
- Network timeouts
- 429 (rate limit)
- 5xx server errors
- Connection resets

**Never retry on**:
- 4xx client errors (except 429)
- Authentication failures
- Validation errors

## Pattern 7: Testing SDK Integrations

**Problem**: SDK calls are slow, flaky, and cost money in tests.

**Pattern**:
```
# Good: Mock at the adapter boundary
// __mocks__/stripe.ts
export const mockStripe = {
  checkout: {
    sessions: {
      create: jest.fn().mockResolvedValue({
        id: "cs_test_123",
        url: "https://checkout.stripe.com/test",
      }),
    },
  },
};

// In tests
import { mockStripe } from "../__mocks__/stripe";
mockStripe.checkout.sessions.create.mockResolvedValueOnce({
  id: "cs_test_456",
  url: "https://checkout.stripe.com/custom",
});
```

## How to use these patterns

1. **Before integrating a new SDK**: Read this skill to understand common patterns
2. **During integration**: Apply relevant patterns to your implementation
3. **After integration**: OpenSpace captures your specific implementation as a new skill

These patterns are starting points. The system will evolve better, project-specific versions as you use them.
