# Temporal Usage Guide for Claude Code (2025)

## Table of Contents
- [Introduction](#introduction)
- [Installation & Setup](#installation--setup)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Workflows](#workflows)
- [Activities](#activities)
- [Workers](#workers)
- [Clients](#clients)
- [Message Passing](#message-passing)
- [Advanced Features](#advanced-features)
- [Event History vs Caching](#event-history-vs-caching)
- [Testing](#testing)
- [Production Deployment](#production-deployment)
- [Best Practices](#best-practices)

---

## Introduction

### What is Temporal?

Temporal is an open-source durable execution platform that abstracts away the complexity of building scalable, reliable distributed systems. It enables developers to write workflows as code that can run for extended periods, automatically recover from failures, and maintain complete application state.

**Key Facts:**
- Created to solve distributed system reliability challenges
- Used by companies like Netflix, Stripe, Snap, and DataDog
- Provides a development abstraction that preserves complete application state
- Official documentation: [docs.temporal.io](https://docs.temporal.io)

### What is Durable Execution?

Durable execution ensures that once started, workflow code runs to completion regardless of infrastructure failures, network issues, or process crashes. Temporal achieves this by:

- Recording every step in an Event History
- Automatically replaying workflows from their last known state
- Providing exactly-once execution guarantees for activities
- Supporting workflows that can run for days, weeks, or months

### Why Use Temporal?

- **Fault Tolerance**: Workflows survive crashes, restarts, and infrastructure failures
- **Reliability**: Automatic retries with configurable policies
- **Observability**: Complete visibility into workflow state and history
- **Scalability**: Horizontal scaling of workers and workflows
- **Developer Experience**: Write complex distributed logic as simple code
- **Language Support**: SDKs for Go, Java, TypeScript, Python, .NET, and PHP

### Core Components

1. **Workflows** - Define business logic as code sequences
2. **Activities** - Perform single, well-defined actions (API calls, database queries, etc.)
3. **Workers** - Execute workflow and activity code
4. **Temporal Service** - Manages workflow state, task queues, and orchestration
5. **Client** - Starts workflows, sends signals, and queries workflow state

---

## Installation & Setup

### Prerequisites
- Python 3.9 or higher
- Temporal CLI (for local development)

### Install Temporal Python SDK

**Using pip:**
```bash
pip install temporalio
```

**Using uv (recommended):**
```bash
uv add temporalio
```

**With specific version:**
```bash
pip install temporalio==1.8.0
```

### Install Temporal CLI

The Temporal CLI provides a local development server and management tools.

**macOS:**
```bash
brew install temporal
```

**Linux:**
```bash
curl -sSf https://temporal.download/cli.sh | sh
```

**Windows:**
```powershell
scoop install temporal
```

### Start Local Temporal Server

```bash
temporal server start-dev
```

This starts:
- Temporal Service on `localhost:7233`
- Web UI at `http://localhost:8233`
- Default namespace: `default`
- In-memory database (data cleared on restart)

### Verify Installation

```python
import temporalio
print(temporalio.__version__)  # Should print version like "1.8.0"
```

### Compatibility Notes

- **Python Version**: 3.9+ required (SDK built with Rust core)
- **Protobuf**: Use 4.x series (recommended), 3.19+ supported
- **Async Support**: Fully async-first with asyncio
- **Known Issues**: Avoid gevent monkey patching with asyncio

---

## Quick Start

### Complete Hello World Example

This example demonstrates all four core components: workflow, activity, worker, and client.

#### 1. Define Activity (`activities.py`)

```python
from temporalio import activity

@activity.defn
async def say_hello(name: str) -> str:
    """Simple activity that returns a greeting."""
    return f"Hello, {name}!"
```

#### 2. Define Workflow (`workflows.py`)

```python
from datetime import timedelta
from temporalio import workflow

# Import activity for type safety
with workflow.unsafe.imports_passed_through():
    from activities import say_hello

@workflow.defn
class SayHello:
    @workflow.run
    async def run(self, name: str) -> str:
        """Workflow that executes the say_hello activity."""
        return await workflow.execute_activity(
            say_hello,
            name,
            start_to_close_timeout=timedelta(seconds=5)
        )
```

#### 3. Create Worker (`run_worker.py`)

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from activities import say_hello
from workflows import SayHello

async def main():
    # Connect to Temporal server
    client = await Client.connect("localhost:7233", namespace="default")

    # Create worker
    worker = Worker(
        client,
        task_queue="hello-task-queue",
        workflows=[SayHello],
        activities=[say_hello]
    )

    # Run worker
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 4. Start Workflow (`run_workflow.py`)

```python
import asyncio
from temporalio.client import Client
from workflows import SayHello

async def main():
    # Connect to Temporal server
    client = await Client.connect("localhost:7233")

    # Execute workflow
    result = await client.execute_workflow(
        SayHello.run,
        "Temporal",
        id="hello-workflow-001",
        task_queue="hello-task-queue"
    )

    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

#### 5. Run the Example

```bash
# Terminal 1: Start Temporal server
temporal server start-dev

# Terminal 2: Start worker
python run_worker.py

# Terminal 3: Execute workflow
python run_workflow.py
```

**Expected Output:**
```
Result: Hello, Temporal!
```

---

## Core Concepts

### Workflow Executions

A **Workflow Execution** is a running instance of a workflow definition.

**Key Properties:**
- Has a unique Workflow ID
- Progresses through Commands and Events
- Recorded in an Event History
- Can run indefinitely
- Deterministic execution required

**Three Primary Terms:**
1. **Workflow Definition**: The code defining the workflow
2. **Workflow Type**: The name/identifier for the workflow
3. **Workflow Execution**: A running instance

### Determinism

Workflows must be deterministic to support replay from Event History.

**Allowed in Workflows:**
```python
@workflow.defn
class MyWorkflow:
    @workflow.run
    async def run(self) -> str:
        # ✅ Execute activities
        result = await workflow.execute_activity(...)

        # ✅ Use workflow-safe sleep
        await asyncio.sleep(60)  # Uses workflow time

        # ✅ Get workflow info
        info = workflow.info()

        # ✅ Wait for conditions
        await workflow.wait_condition(lambda: self.ready)

        # ✅ Start child workflows
        child = await workflow.execute_child_workflow(...)

        return "Success"
```

**NOT Allowed in Workflows:**
```python
# ❌ Random operations
import random
value = random.random()  # Non-deterministic!

# ❌ Current time
import datetime
now = datetime.datetime.now()  # Non-deterministic!

# ❌ Direct I/O operations
with open('file.txt') as f:  # Not allowed!
    data = f.read()

# ❌ Direct API calls
import requests
response = requests.get('api.example.com')  # Not allowed!
```

**The Temporal Python SDK uses a sandbox to prevent most non-deterministic operations.**

### Task Queues

Task queues route work to workers.

**Characteristics:**
- Named queues (e.g., "email-task-queue")
- Workers poll specific queues
- Workflows and activities can use different queues
- Enable worker specialization and load balancing

**Example:**
```python
# Worker listening to specific queue
worker = Worker(
    client,
    task_queue="high-priority-queue",
    workflows=[ImportantWorkflow],
    activities=[critical_activity]
)

# Start workflow on that queue
await client.start_workflow(
    ImportantWorkflow.run,
    id="important-001",
    task_queue="high-priority-queue"
)
```

### Event History

Every workflow maintains a complete Event History.

**What's Recorded:**
- Workflow started
- Activity scheduled
- Activity completed
- Timers fired
- Signals received
- Child workflows started
- Workflow completed

**Benefits:**
- Complete audit trail
- Enables replay for recovery
- Powers workflow visualization
- Supports debugging

---

## Workflows

### Basic Workflow

```python
from temporalio import workflow

@workflow.defn
class GreetingWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return f"Hello, {name}!"
```

### Workflow with Activities

```python
from datetime import timedelta
from temporalio import workflow

@workflow.defn
class OrderWorkflow:
    @workflow.run
    async def run(self, order_id: str) -> dict:
        # Execute activities in sequence
        payment = await workflow.execute_activity(
            process_payment,
            order_id,
            start_to_close_timeout=timedelta(seconds=30)
        )

        shipment = await workflow.execute_activity(
            ship_order,
            order_id,
            start_to_close_timeout=timedelta(minutes=5)
        )

        return {
            "order_id": order_id,
            "payment": payment,
            "shipment": shipment
        }
```

### Workflow with State

```python
from temporalio import workflow

@workflow.defn
class StatefulWorkflow:
    def __init__(self) -> None:
        self.counter = 0
        self.messages = []

    @workflow.run
    async def run(self) -> dict:
        # State persists across replay
        self.counter += 1
        self.messages.append("Started")

        await workflow.execute_activity(
            some_activity,
            start_to_close_timeout=timedelta(seconds=10)
        )

        self.counter += 1
        self.messages.append("Completed")

        return {
            "counter": self.counter,
            "messages": self.messages
        }
```

### Workflow with Timers

```python
import asyncio
from temporalio import workflow

@workflow.defn
class ScheduledWorkflow:
    @workflow.run
    async def run(self) -> str:
        # Sleep for 1 hour (workflow time, not real time)
        await asyncio.sleep(3600)

        # Execute activity after delay
        result = await workflow.execute_activity(
            delayed_task,
            start_to_close_timeout=timedelta(seconds=30)
        )

        return result
```

### Workflow with Conditional Logic

```python
from temporalio import workflow

@workflow.defn
class ConditionalWorkflow:
    @workflow.run
    async def run(self, user_type: str) -> dict:
        if user_type == "premium":
            result = await workflow.execute_activity(
                premium_processing,
                start_to_close_timeout=timedelta(minutes=10)
            )
        else:
            result = await workflow.execute_activity(
                standard_processing,
                start_to_close_timeout=timedelta(minutes=5)
            )

        return {"type": user_type, "result": result}
```

### Workflow with Parallel Activities

```python
import asyncio
from temporalio import workflow

@workflow.defn
class ParallelWorkflow:
    @workflow.run
    async def run(self) -> list:
        # Execute activities in parallel
        results = await asyncio.gather(
            workflow.execute_activity(
                activity_1,
                start_to_close_timeout=timedelta(seconds=30)
            ),
            workflow.execute_activity(
                activity_2,
                start_to_close_timeout=timedelta(seconds=30)
            ),
            workflow.execute_activity(
                activity_3,
                start_to_close_timeout=timedelta(seconds=30)
            )
        )

        return results
```

---

## Activities

### Basic Activity

```python
from temporalio import activity

@activity.defn
def simple_activity(name: str) -> str:
    """Synchronous activity."""
    return f"Processed: {name}"
```

### Async Activity

```python
import httpx
from temporalio import activity

@activity.defn
async def fetch_data(url: str) -> dict:
    """Async activity for I/O operations."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

### Activity with Retry Configuration

```python
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

@workflow.defn
class WorkflowWithRetry:
    @workflow.run
    async def run(self) -> str:
        result = await workflow.execute_activity(
            unreliable_activity,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                backoff_coefficient=2.0,
                maximum_attempts=5
            )
        )
        return result
```

### Activity with Heartbeats

```python
import asyncio
from temporalio import activity

@activity.defn
async def long_running_activity(total_items: int) -> str:
    """Activity that reports progress via heartbeats."""
    for i in range(total_items):
        # Perform work
        await asyncio.sleep(1)

        # Send heartbeat to indicate progress
        activity.heartbeat(f"Processed {i+1}/{total_items}")

    return f"Completed {total_items} items"
```

### Activity with Context

```python
from temporalio import activity

@activity.defn
async def activity_with_context(data: str) -> str:
    """Access activity information via context."""
    info = activity.info()

    # Access workflow and activity metadata
    workflow_id = info.workflow_id
    activity_id = info.activity_id
    attempt = info.attempt

    # Use logger
    activity.logger.info(f"Processing in workflow {workflow_id}")

    return f"Processed by attempt {attempt}"
```

### Activity Timeout Configuration

```python
from datetime import timedelta
from temporalio import workflow

@workflow.defn
class TimeoutWorkflow:
    @workflow.run
    async def run(self) -> str:
        result = await workflow.execute_activity(
            my_activity,
            # How long activity can take from start to completion
            start_to_close_timeout=timedelta(seconds=30),

            # How long activity can wait in queue before starting
            schedule_to_start_timeout=timedelta(minutes=5),

            # Total time from scheduling to completion
            schedule_to_close_timeout=timedelta(minutes=10),

            # Maximum time between heartbeats
            heartbeat_timeout=timedelta(seconds=5)
        )
        return result
```

### Activity Cancellation

```python
import asyncio
from temporalio import activity

@activity.defn
async def cancellable_activity() -> str:
    """Activity that handles cancellation gracefully."""
    try:
        for i in range(100):
            # Check for cancellation
            if activity.is_cancelled():
                # Cleanup
                await cleanup()
                return "Cancelled"

            await asyncio.sleep(1)
            activity.heartbeat()

        return "Completed"
    except asyncio.CancelledError:
        # Handle cancellation
        await cleanup()
        raise
```

---

## Workers

### Basic Worker

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from workflows import MyWorkflow
from activities import my_activity

async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="my-task-queue",
        workflows=[MyWorkflow],
        activities=[my_activity]
    )

    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Worker with Multiple Workflows and Activities

```python
worker = Worker(
    client,
    task_queue="main-queue",
    workflows=[
        OrderWorkflow,
        PaymentWorkflow,
        ShipmentWorkflow
    ],
    activities=[
        process_payment,
        ship_order,
        send_notification,
        update_inventory
    ]
)
```

### Worker with Concurrency Configuration

```python
from concurrent.futures import ThreadPoolExecutor

worker = Worker(
    client,
    task_queue="high-throughput-queue",
    workflows=[MyWorkflow],
    activities=[my_activity],

    # Max concurrent workflow tasks
    max_concurrent_workflow_tasks=100,

    # Max concurrent activities
    max_concurrent_activities=200,

    # Executor for sync activities
    activity_executor=ThreadPoolExecutor(max_workers=50)
)
```

### Worker for Synchronous Activities

```python
from concurrent.futures import ThreadPoolExecutor

# Synchronous activity (no async)
@activity.defn
def sync_activity(data: str) -> str:
    # CPU-bound or blocking operation
    return process_data(data)

worker = Worker(
    client,
    task_queue="sync-queue",
    workflows=[MyWorkflow],
    activities=[sync_activity],

    # Required for sync activities
    activity_executor=ThreadPoolExecutor(max_workers=10)
)
```

### Multiple Workers

```python
async def run_workers():
    client = await Client.connect("localhost:7233")

    # Worker for high-priority tasks
    worker_high = Worker(
        client,
        task_queue="high-priority",
        workflows=[UrgentWorkflow],
        activities=[urgent_activity]
    )

    # Worker for low-priority tasks
    worker_low = Worker(
        client,
        task_queue="low-priority",
        workflows=[BackgroundWorkflow],
        activities=[background_activity]
    )

    # Run both workers concurrently
    await asyncio.gather(
        worker_high.run(),
        worker_low.run()
    )
```

### Worker with Graceful Shutdown

```python
import signal
import asyncio

async def main():
    client = await Client.connect("localhost:7233")
    worker = Worker(client, task_queue="my-queue", workflows=[...], activities=[...])

    # Handle shutdown signals
    shutdown_event = asyncio.Event()

    def signal_handler():
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Run worker until shutdown signal
    async def run_until_shutdown():
        worker_task = asyncio.create_task(worker.run())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [worker_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Shutdown worker gracefully
        await worker.shutdown()

    await run_until_shutdown()
```

---

## Clients

### Connect to Temporal

```python
from temporalio.client import Client

# Connect to local server
client = await Client.connect("localhost:7233")

# Connect with namespace
client = await Client.connect("localhost:7233", namespace="production")

# Connect to Temporal Cloud
client = await Client.connect(
    "my-namespace.a1b2c.tmprl.cloud:7233",
    namespace="my-namespace",
    tls=True
)
```

### Start Workflow

```python
# Start and wait for completion
result = await client.execute_workflow(
    MyWorkflow.run,
    "input-data",
    id="workflow-001",
    task_queue="my-task-queue"
)

# Start without waiting
handle = await client.start_workflow(
    MyWorkflow.run,
    "input-data",
    id="workflow-002",
    task_queue="my-task-queue"
)

# Later, get the result
result = await handle.result()
```

### Get Workflow Handle

```python
# Get handle to existing workflow
handle = client.get_workflow_handle("workflow-001")

# Get result
result = await handle.result()

# Query workflow
state = await handle.query("get_state")

# Send signal
await handle.signal("update_status", "active")

# Cancel workflow
await handle.cancel()

# Terminate workflow
await handle.terminate("Manual termination")
```

### List Workflows

```python
from temporalio.client import WorkflowExecutionStatus

# List all running workflows
async for workflow in client.list_workflows("WorkflowType = 'MyWorkflow'"):
    print(f"ID: {workflow.id}, Status: {workflow.status}")

# List completed workflows
async for workflow in client.list_workflows(
    f"ExecutionStatus = '{WorkflowExecutionStatus.COMPLETED}'"
):
    print(f"ID: {workflow.id}")
```

---

## Message Passing

### Signals (Async Messages)

Signals send asynchronous messages to running workflows.

#### Define Signal Handler

```python
from temporalio import workflow

@workflow.defn
class ApprovalWorkflow:
    def __init__(self) -> None:
        self.approved = False
        self.approver = None

    @workflow.run
    async def run(self) -> dict:
        # Wait for approval signal
        await workflow.wait_condition(lambda: self.approved)

        return {
            "status": "approved",
            "approver": self.approver
        }

    @workflow.signal
    def approve(self, approver_name: str) -> None:
        """Signal handler for approval."""
        self.approved = True
        self.approver = approver_name
```

#### Send Signal

```python
# Get workflow handle
handle = client.get_workflow_handle("approval-workflow-001")

# Send signal
await handle.signal("approve", "Alice")
```

### Queries (Sync Read)

Queries read workflow state without modifying it.

#### Define Query Handler

```python
from temporalio import workflow
from enum import IntEnum

class Language(IntEnum):
    ENGLISH = 1
    SPANISH = 2
    FRENCH = 3

@workflow.defn
class TranslationWorkflow:
    def __init__(self) -> None:
        self.current_language = Language.ENGLISH
        self.translations = []

    @workflow.run
    async def run(self) -> dict:
        # Workflow logic
        pass

    @workflow.query
    def get_current_language(self) -> Language:
        """Query handler returns current language."""
        return self.current_language

    @workflow.query
    def get_translation_count(self) -> int:
        """Query handler returns count."""
        return len(self.translations)
```

#### Send Query

```python
# Get workflow handle
handle = client.get_workflow_handle("translation-workflow-001")

# Query workflow state
language = await handle.query("get_current_language")
count = await handle.query("get_translation_count")

print(f"Language: {language}, Translations: {count}")
```

### Updates (Sync Write)

Updates synchronously modify workflow state and return a result.

#### Define Update Handler

```python
from temporalio import workflow

@workflow.defn
class ConfigWorkflow:
    def __init__(self) -> None:
        self.config = {}

    @workflow.run
    async def run(self) -> dict:
        # Wait indefinitely
        await workflow.wait_condition(lambda: False)

    @workflow.update
    def set_config(self, key: str, value: str) -> str:
        """Update handler that modifies state and returns result."""
        old_value = self.config.get(key)
        self.config[key] = value
        return f"Updated {key}: {old_value} -> {value}"

    @set_config.validator
    def validate_config(self, key: str, value: str) -> None:
        """Validator runs before update is accepted."""
        if not key or not value:
            raise ValueError("Key and value cannot be empty")
```

#### Send Update

```python
# Get workflow handle
handle = client.get_workflow_handle("config-workflow-001")

# Send update and wait for result
result = await handle.execute_update("set_config", "timeout", "30s")
print(result)  # "Updated timeout: None -> 30s"
```

### Dynamic Handlers

```python
@workflow.defn
class DynamicWorkflow:
    def __init__(self) -> None:
        self.data = {}

    @workflow.run
    async def run(self) -> dict:
        await workflow.wait_condition(lambda: False)

    @workflow.signal(dynamic=True)
    def dynamic_signal(self, name: str, args: list) -> None:
        """Handle any signal dynamically."""
        self.data[name] = args

    @workflow.query(dynamic=True)
    def dynamic_query(self, name: str, args: list):
        """Handle any query dynamically."""
        return self.data.get(name, "Not found")
```

---

## Advanced Features

### Child Workflows

```python
from temporalio import workflow

@workflow.defn
class ParentWorkflow:
    @workflow.run
    async def run(self, items: list) -> list:
        results = []

        # Start child workflow for each item
        for item in items:
            result = await workflow.execute_child_workflow(
                ChildWorkflow.run,
                item,
                id=f"child-{item}",
                parent_close_policy=ParentClosePolicy.ABANDON
            )
            results.append(result)

        return results

@workflow.defn
class ChildWorkflow:
    @workflow.run
    async def run(self, item: str) -> str:
        # Process item
        result = await workflow.execute_activity(
            process_item,
            item,
            start_to_close_timeout=timedelta(seconds=30)
        )
        return result
```

### Continue-As-New

Continue-As-New creates a new workflow execution to limit Event History size.

```python
from temporalio import workflow

@workflow.defn
class LongRunningWorkflow:
    @workflow.run
    async def run(self, counter: int) -> str:
        # Process batch
        await workflow.execute_activity(
            process_batch,
            counter,
            start_to_close_timeout=timedelta(seconds=30)
        )

        # Check if should continue
        if workflow.info().is_continue_as_new_suggested():
            # Continue as new with updated state
            workflow.continue_as_new(counter + 1)

        return f"Completed {counter} batches"
```

### Schedules (Cron Workflows)

```python
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec

async def create_schedule():
    client = await Client.connect("localhost:7233")

    # Create schedule with cron expression
    await client.create_schedule(
        "daily-report-schedule",
        Schedule(
            action=ScheduleActionStartWorkflow(
                ReportWorkflow.run,
                id="daily-report",
                task_queue="reports"
            ),
            spec=ScheduleSpec(
                cron_expressions=["0 9 * * *"]  # Daily at 9 AM
            )
        )
    )
```

### Schedule with Intervals

```python
from temporalio.common import ScheduleIntervalSpec
from datetime import timedelta

await client.create_schedule(
    "health-check-schedule",
    Schedule(
        action=ScheduleActionStartWorkflow(
            HealthCheckWorkflow.run,
            task_queue="monitoring"
        ),
        spec=ScheduleSpec(
            intervals=[
                ScheduleIntervalSpec(
                    every=timedelta(minutes=5)
                )
            ]
        )
    )
)
```

### Data Encryption

```python
from temporalio.converter import PayloadCodec, DataConverter
import base64

class EncryptionCodec(PayloadCodec):
    """Custom codec for encrypting/decrypting payloads."""

    async def encode(self, payloads):
        # Encrypt each payload
        return [self._encrypt(p) for p in payloads]

    async def decode(self, payloads):
        # Decrypt each payload
        return [self._decrypt(p) for p in payloads]

    def _encrypt(self, payload):
        # Simple example - use real encryption in production
        encrypted = base64.b64encode(payload.data)
        payload.data = encrypted
        return payload

    def _decrypt(self, payload):
        decrypted = base64.b64decode(payload.data)
        payload.data = decrypted
        return payload

# Use encrypted data converter
client = await Client.connect(
    "localhost:7233",
    data_converter=DataConverter(payload_codec=EncryptionCodec())
)
```

### Versioning Workflows

```python
from temporalio import workflow

@workflow.defn
class VersionedWorkflow:
    @workflow.run
    async def run(self) -> str:
        # Use versioning for workflow changes
        version = workflow.patched("my-change")

        if version:
            # New code path
            result = await workflow.execute_activity(
                new_activity,
                start_to_close_timeout=timedelta(seconds=30)
            )
        else:
            # Old code path (for replay compatibility)
            result = await workflow.execute_activity(
                old_activity,
                start_to_close_timeout=timedelta(seconds=30)
            )

        return result
```

---

## Event History vs Caching

One of the most common questions when coming from tools like Prefect to Temporal is: "Why can't I just cache activity results like Prefect does?" This section explains how Temporal's Event History works, why it's different from traditional caching, and how to implement Prefect-style caching patterns in Temporal.

### Understanding Event History

Temporal's Event History is a complete, immutable log of everything that happens in a workflow execution.

#### What Gets Stored in Event History

```python
@activity.defn
async def fetch_user(user_id: int) -> dict:
    """Activity that fetches user from database"""
    return await db.query(f"SELECT * FROM users WHERE id = {user_id}")

@workflow.defn
class MyWorkflow:
    @workflow.run
    async def run(self, user_id: int) -> dict:
        user = await workflow.execute_activity(
            fetch_user,
            user_id,
            start_to_close_timeout=timedelta(seconds=30)
        )
        return {"user": user, "processed": True}
```

**Event History for this workflow:**

1. `WorkflowExecutionStarted` - Input: `user_id=123`
2. `WorkflowTaskScheduled` - Workflow code starts
3. `WorkflowTaskStarted` - Worker picks up task
4. `ActivityTaskScheduled` - Activity: `fetch_user`, Input: `user_id=123`
5. `ActivityTaskStarted` - Worker executes activity
6. **`ActivityTaskCompleted`** - **Result: `{"id": 123, "name": "Alice", ...}` ✅ STORED HERE**
7. `WorkflowTaskScheduled` - Workflow resumes
8. `WorkflowExecutionCompleted` - Final result returned

#### How Replay Uses Event History

When a workflow crashes or a worker restarts, Temporal replays the workflow:

```python
# Worker restarts, workflow replays

@workflow.defn
class MyWorkflow:
    @workflow.run
    async def run(self, user_id: int) -> dict:
        # Workflow code runs again from the start
        user = await workflow.execute_activity(
            fetch_user,
            user_id,
            start_to_close_timeout=timedelta(seconds=30)
        )
        # What happens here? ↑
```

**During replay:**
1. Temporal checks Event History: "Was this activity already executed?"
2. Finds `ActivityTaskCompleted` with result `{"id": 123, "name": "Alice", ...}`
3. **Activity does NOT execute again** - result loaded from Event History
4. Workflow continues with the stored result

**This is deterministic replay, NOT caching for performance!**

#### Storage Details

**Where:** Temporal Server database (PostgreSQL, MySQL, Cassandra, etc.)
**Retention:** Configurable (default 7-30 days)
**Size Limit:** ~2MB per activity result (configurable)
**Purpose:** Enable reliable replay after failures

### Event History vs Prefect-Style Caching

| Feature | Temporal Event History | Prefect Cache |
|---------|----------------------|---------------|
| **Scope** | Per-workflow-execution | Cross-execution (shared) |
| **Purpose** | Reliability & replay | Performance optimization |
| **Reuse** | Only within same workflow execution | Across different flow runs |
| **Trigger** | Automatic (always on) | Opt-in (cache policies) |
| **Key** | Workflow execution ID | Cache key (inputs hash, etc.) |
| **Sharing** | Isolated to one workflow | Shared across flows/tasks |
| **Expiration** | Workflow retention period | Configurable TTL |

#### The Key Difference Illustrated

```python
# Temporal Event History (automatic)
# =================================

# Workflow execution 1: workflow-123
result1 = await client.execute_workflow(
    MyWorkflow.run,
    user_id=123,
    id="workflow-123",
    task_queue="my-queue"
)
# Activity executes → Result stored in Event History for workflow-123

# Workflow-123 crashes and replays
# ✅ Activity result retrieved from Event History
# ✅ Activity does NOT execute again (deterministic replay)

# NEW workflow execution: workflow-456
result2 = await client.execute_workflow(
    MyWorkflow.run,
    user_id=123,  # ← Same input!
    id="workflow-456",  # ← Different workflow ID
    task_queue="my-queue"
)
# ❌ Activity executes AGAIN
# ❌ Cannot reuse workflow-123's result
# ❌ Each workflow has separate Event History
```

```python
# Prefect Cache (opt-in)
# ======================

@task(cache_key_fn=task_input_hash, cache_expiration=timedelta(hours=1))
def fetch_user(user_id: int):
    return db.query(f"SELECT * FROM users WHERE id = {user_id}")

@flow
def flow_1():
    result = fetch_user(user_id=123)  # Executes, caches result

@flow
def flow_2():
    result = fetch_user(user_id=123)  # ✅ Cache HIT! Uses cached result
    # Different flow, same inputs, reuses cache!
```

**Bottom Line:** Event History enables **reliability within a workflow**, not **performance optimization across workflows**.

### Why Determinism Makes Caching Tricky

Workflows must be **deterministic** - they must take the same execution path during replay.

#### ❌ What Breaks: Non-Deterministic Cache Reads

```python
import redis

redis_client = redis.Redis()

@workflow.defn
class BrokenCachingWorkflow:
    @workflow.run
    async def run(self, user_id: int) -> dict:
        # ❌ PROBLEM: Reading from cache in workflow is non-deterministic!
        cache_key = f"user:{user_id}"
        cached_data = redis_client.get(cache_key)

        if cached_data:  # ← Condition can change during replay!
            return json.loads(cached_data)

        data = await workflow.execute_activity(
            fetch_user_data,
            user_id,
            start_to_close_timeout=timedelta(seconds=30)
        )

        redis_client.set(cache_key, json.dumps(data))
        return data
```

**Why this fails:**
1. **First execution:** Cache miss → `if False` → execute activity
2. **Workflow crashes** (server restart, deployment)
3. **Replay:** Cache hit (data now in cache) → `if True` → return cached
4. **Different execution path!** → Non-deterministic → **Workflow fails!** ❌

#### ✅ What Works: Deterministic Conditionals

**Based on workflow inputs:**
```python
@workflow.defn
class DeterministicWorkflow:
    @workflow.run
    async def run(self, user_type: str) -> dict:
        # ✅ Deterministic - input never changes
        if user_type == "premium":
            discount = 0.20
        else:
            discount = 0.10

        # Always same path during replay ✅
        return {"discount": discount}
```

**Based on activity results:**
```python
@workflow.defn
class ActivityConditional:
    @workflow.run
    async def run(self, user_id: int) -> str:
        # Execute activity
        user = await workflow.execute_activity(
            fetch_user,
            user_id,
            start_to_close_timeout=timedelta(seconds=30)
        )

        # ✅ Deterministic - activity result is in Event History
        if user["age"] >= 18:
            result = await workflow.execute_activity(
                adult_process,
                user_id,
                start_to_close_timeout=timedelta(seconds=30)
            )
        else:
            result = await workflow.execute_activity(
                minor_process,
                user_id,
                start_to_close_timeout=timedelta(seconds=30)
            )

        return result
```

**Using workflow-safe functions:**
```python
@workflow.defn
class SafeRandomWorkflow:
    @workflow.run
    async def run(self) -> str:
        # ❌ random.random() - non-deterministic
        # ✅ workflow.random() - deterministic (seeded)
        value = workflow.random().random()

        if value > 0.5:
            return "heads"
        return "tails"
```

### Implementing Prefect-Style Caching in Temporal

Since Temporal doesn't have built-in cross-workflow caching, implement it in activities:

#### Pattern 1: Activity-Level Caching with Redis

```python
import redis
import hashlib
import json
from temporalio import activity, workflow
from datetime import timedelta
from typing import Any

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def compute_cache_key(function_name: str, inputs: dict) -> str:
    """Compute cache key from function name and inputs."""
    sorted_inputs = json.dumps(inputs, sort_keys=True)
    combined = f"{function_name}:{sorted_inputs}"
    return hashlib.sha256(combined.encode()).hexdigest()

@activity.defn
async def cached_fetch_user(user_id: int) -> dict:
    """Activity with caching - Prefect-style!"""
    # Compute cache key
    cache_key = compute_cache_key(
        "cached_fetch_user",
        {"user_id": user_id}
    )

    # Check cache
    cached = redis_client.get(cache_key)
    if cached:
        activity.logger.info(f"Cache HIT: {cache_key}")
        return json.loads(cached)

    activity.logger.info(f"Cache MISS: {cache_key}")

    # Execute expensive operation
    user_data = await db.fetch_user(user_id)

    # Store in cache with TTL
    redis_client.setex(
        cache_key,
        timedelta(hours=1),
        json.dumps(user_data)
    )

    return user_data

@workflow.defn
class CachedWorkflow:
    @workflow.run
    async def run(self, user_id: int) -> dict:
        # Workflow is deterministic - always calls activity
        # Activity handles caching internally
        user = await workflow.execute_activity(
            cached_fetch_user,
            user_id,
            start_to_close_timeout=timedelta(seconds=30)
        )
        return user
```

**Cross-workflow caching:**
```python
# Workflow 1: Fetches user 123
await client.execute_workflow(
    CachedWorkflow.run,
    123,
    id="wf-001",
    task_queue="my-queue"
)
# Activity executes, stores in Redis: cache_key → {user_data}

# Workflow 2: Also fetches user 123
await client.execute_workflow(
    CachedWorkflow.run,
    123,
    id="wf-002",  # Different workflow!
    task_queue="my-queue"
)
# Activity executes BUT hits Redis cache! ✅
# Returns cached data immediately
# Event History still records ActivityTaskCompleted
```

#### Pattern 2: Reusable Cache Decorator (Prefect-like)

```python
from enum import Enum
from typing import Callable, Optional
import inspect

class CachePolicy(Enum):
    INPUTS = "inputs"
    TASK_SOURCE = "task_source"
    NO_CACHE = "no_cache"

class TemporalCache:
    def __init__(self, redis_client):
        self.redis_client = redis_client

    def compute_cache_key(
        self,
        func_name: str,
        inputs: dict,
        policy: CachePolicy
    ) -> Optional[str]:
        if policy == CachePolicy.NO_CACHE:
            return None

        if policy == CachePolicy.INPUTS:
            key_data = {"func": func_name, "inputs": inputs}
        elif policy == CachePolicy.TASK_SOURCE:
            # Include source code
            source = inspect.getsource(func_name)
            key_data = {"func": func_name, "source": source, "inputs": inputs}

        serialized = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get(self, cache_key: str) -> Optional[Any]:
        if not cache_key:
            return None
        cached = self.redis_client.get(cache_key)
        return json.loads(cached) if cached else None

    def set(self, cache_key: str, value: Any, expiration: Optional[timedelta] = None):
        if not cache_key:
            return
        serialized = json.dumps(value)
        if expiration:
            self.redis_client.setex(cache_key, expiration, serialized)
        else:
            self.redis_client.set(cache_key, serialized)

cache = TemporalCache(redis_client)

def cached_activity(
    policy: CachePolicy = CachePolicy.INPUTS,
    expiration: Optional[timedelta] = None
):
    """Decorator for cached activities - Prefect-style!"""
    def decorator(func: Callable):
        @activity.defn(name=func.__name__)
        async def wrapper(*args, **kwargs):
            # Build inputs dict
            inputs = {"args": args, "kwargs": kwargs}

            # Compute cache key
            cache_key = cache.compute_cache_key(
                func.__name__,
                inputs,
                policy
            )

            # Check cache
            if cache_key:
                cached_result = cache.get(cache_key)
                if cached_result is not None:
                    activity.logger.info(f"Cache HIT: {func.__name__}")
                    return cached_result
                activity.logger.info(f"Cache MISS: {func.__name__}")

            # Execute function
            import asyncio
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

            # Store in cache
            if cache_key:
                cache.set(cache_key, result, expiration)

            return result
        return wrapper
    return decorator

# Usage
@cached_activity(policy=CachePolicy.INPUTS, expiration=timedelta(hours=1))
async def fetch_user_data(user_id: int) -> dict:
    """Cached based on user_id for 1 hour"""
    return await db.fetch_user(user_id)

@cached_activity(policy=CachePolicy.TASK_SOURCE)
def calculate_result(x: int, y: int) -> int:
    """Cached by inputs AND source code"""
    return x * y + 42

@cached_activity(policy=CachePolicy.NO_CACHE)
async def always_run(data: str) -> str:
    """Never cached"""
    return f"Processed: {data}"
```

#### Pattern 3: Client-Side Caching (Before Starting Workflow)

```python
async def run_workflow_with_cache(
    client: Client,
    user_id: int
) -> dict:
    """Check cache before even starting workflow"""
    cache_key = f"workflow_result:user:{user_id}"

    # Check cache
    cached = redis_client.get(cache_key)
    if cached:
        print("Cache HIT - not starting workflow")
        return json.loads(cached)

    print("Cache MISS - starting workflow")

    # Run workflow
    result = await client.execute_workflow(
        FetchUserWorkflow.run,
        user_id,
        id=f"user-wf-{user_id}-{uuid.uuid4()}",
        task_queue="my-queue"
    )

    # Cache result
    redis_client.setex(
        cache_key,
        timedelta(hours=1),
        json.dumps(result)
    )

    return result
```

#### Pattern 4: Multi-Task Caching (Transactional)

For Prefect's multi-task caching (multiple tasks run together or use cache together):

```python
@workflow.defn
class TransactionalCacheWorkflow:
    @workflow.run
    async def run(self, order_id: str) -> dict:
        # Compute cache key for entire workflow
        cache_key = f"order_workflow:{order_id}"

        # Check if all results are cached
        cached_results = redis_client.get(cache_key)
        if cached_results:
            workflow.logger.info("Using cached workflow results")
            return json.loads(cached_results)

        # Execute all activities together
        results = await workflow.execute_activity(
            process_order_transaction,
            order_id,
            start_to_close_timeout=timedelta(minutes=5)
        )

        # Cache complete results
        redis_client.setex(
            cache_key,
            timedelta(hours=24),
            json.dumps(results)
        )

        return results

@activity.defn
async def process_order_transaction(order_id: str) -> dict:
    """Execute multiple related operations as transaction"""
    transaction_key = f"order_txn:{order_id}"

    # Check if transaction is cached
    if redis_client.exists(transaction_key):
        return json.loads(redis_client.get(transaction_key))

    # Execute all operations
    payment = await process_payment(order_id)
    inventory = await update_inventory(order_id)
    shipping = await create_shipment(order_id)

    # Store atomically
    results = {
        "payment": payment,
        "inventory": inventory,
        "shipping": shipping
    }

    redis_client.setex(
        transaction_key,
        timedelta(hours=24),
        json.dumps(results)
    )

    return results
```

#### Pattern 5: Workflow-Level Memoization (Within Execution)

For caching within a single workflow execution:

```python
@workflow.defn
class MemoizedWorkflow:
    def __init__(self):
        self._memo_cache = {}

    def memoize(self, func: Callable, *args, **kwargs) -> Any:
        """Memoize function calls within workflow"""
        cache_key = hashlib.sha256(
            json.dumps({
                "func": func.__name__,
                "args": args,
                "kwargs": kwargs
            }, sort_keys=True).encode()
        ).hexdigest()

        if cache_key in self._memo_cache:
            workflow.logger.info(f"Memo HIT: {func.__name__}")
            return self._memo_cache[cache_key]

        workflow.logger.info(f"Memo MISS: {func.__name__}")

        # Use mutable side effect for determinism
        result = workflow.unsafe.mutable_side_effect(
            lambda: func(*args, **kwargs)
        )

        self._memo_cache[cache_key] = result
        return result

    @workflow.run
    async def run(self, items: list[int]) -> list[int]:
        results = []
        for item in items:
            # Cached within this workflow execution
            result = self.memoize(expensive_calc, item)
            results.append(result)
        return results

def expensive_calc(x: int) -> int:
    """Deterministic calculation"""
    return x ** 2 + 42
```

### Comparison: Temporal vs Prefect Caching

| Feature | Prefect | Temporal Equivalent |
|---------|---------|---------------------|
| **Cache Policies** | Built-in (INPUTS, TASK_SOURCE, etc.) | Custom implementation |
| **Cache Storage** | Configurable | Redis, DynamoDB, or any KV store |
| **Cache Keys** | Auto-computed from policies | Manually computed (hash inputs) |
| **Expiration** | `cache_expiration` parameter | TTL in cache store (Redis SETEX) |
| **Multi-task Caching** | Transaction-based | Activity-level with external cache |
| **Cache Isolation** | READ_COMMITTED, SERIALIZABLE | Implement with distributed locks |
| **Automatic** | Yes (opt-in) | No (manual implementation) |

### Why No Built-in Caching Library?

1. **Architecture:** Temporal prioritizes reliability over performance optimization
2. **Determinism:** Workflows must be deterministic; caching introduces non-determinism
3. **Event History:** Already provides replay capability (not performance caching)
4. **External State:** True caching requires external systems (Redis, etc.)
5. **Flexibility:** Different use cases need different caching strategies

### Best Practices for Caching in Temporal

#### 1. Cache at Activity Level

✅ **Do:**
```python
@activity.defn
async def cached_operation(input_data: str) -> str:
    # Check cache in activity (safe)
    cached = redis_client.get(cache_key)
    if cached:
        return cached

    result = expensive_operation(input_data)
    redis_client.set(cache_key, result)
    return result
```

❌ **Don't:**
```python
@workflow.defn
class BadWorkflow:
    @workflow.run
    async def run(self, input_data: str) -> str:
        # ❌ Don't check cache in workflow
        cached = redis_client.get(cache_key)
        if cached:
            return cached
        # Non-deterministic!
```

#### 2. Use Deterministic Cache Keys

```python
def compute_cache_key(func_name: str, **params) -> str:
    # Always sort keys for consistent hashing
    sorted_params = json.dumps(params, sort_keys=True)
    return hashlib.sha256(f"{func_name}:{sorted_params}".encode()).hexdigest()
```

#### 3. Set Appropriate TTLs

```python
# Short TTL for rapidly changing data
redis_client.setex(cache_key, timedelta(minutes=5), result)

# Longer TTL for stable data
redis_client.setex(cache_key, timedelta(hours=24), result)

# No expiration for immutable data
redis_client.set(cache_key, result)
```

#### 4. Handle Cache Failures Gracefully

```python
@activity.defn
async def resilient_cached_activity(input_data: str) -> str:
    try:
        # Try cache
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        activity.logger.warning(f"Cache read failed: {e}")

    # Always have fallback to actual execution
    result = await perform_operation(input_data)

    try:
        # Try to cache result
        redis_client.setex(cache_key, timedelta(hours=1), json.dumps(result))
    except Exception as e:
        activity.logger.warning(f"Cache write failed: {e}")

    return result
```

#### 5. Monitor Cache Effectiveness

```python
from prometheus_client import Counter, Histogram

cache_hits = Counter('activity_cache_hits_total', 'Cache hits', ['activity'])
cache_misses = Counter('activity_cache_misses_total', 'Cache misses', ['activity'])

@activity.defn
async def monitored_cached_activity(data: str) -> str:
    cached = redis_client.get(cache_key)

    if cached:
        cache_hits.labels(activity='monitored_cached_activity').inc()
        return json.loads(cached)

    cache_misses.labels(activity='monitored_cached_activity').inc()
    result = await expensive_operation(data)
    redis_client.setex(cache_key, timedelta(hours=1), json.dumps(result))
    return result
```

#### 6. Consider Cache Invalidation

```python
# Time-based invalidation
redis_client.setex(cache_key, timedelta(hours=1), result)

# Event-based invalidation (via Signal)
@workflow.defn
class CacheInvalidationWorkflow:
    @workflow.run
    async def run(self) -> str:
        result = await workflow.execute_activity(
            cached_activity,
            "input",
            start_to_close_timeout=timedelta(seconds=30)
        )
        return result

    @workflow.signal
    def invalidate_cache(self, cache_key: str) -> None:
        """Signal to invalidate specific cache entry"""
        redis_client.delete(cache_key)
```

### Common Pitfalls to Avoid

#### 1. Reading Cache in Workflow

❌ **Wrong:**
```python
@workflow.defn
class BadWorkflow:
    @workflow.run
    async def run(self) -> str:
        if redis_client.exists(cache_key):  # ❌ Non-deterministic!
            return redis_client.get(cache_key)
```

✅ **Correct:**
```python
@activity.defn
async def cached_activity() -> str:
    if redis_client.exists(cache_key):  # ✅ OK in activity
        return redis_client.get(cache_key)
```

#### 2. Using datetime.now() in Workflow

❌ **Wrong:**
```python
@workflow.defn
class BadWorkflow:
    @workflow.run
    async def run(self) -> str:
        if datetime.now().hour >= 17:  # ❌ Non-deterministic!
            return "after_hours"
```

✅ **Correct:**
```python
@workflow.defn
class GoodWorkflow:
    @workflow.run
    async def run(self) -> str:
        if workflow.now().hour >= 17:  # ✅ Deterministic
            return "after_hours"
```

#### 3. Storing Large Results

❌ **Wrong:**
```python
@activity.defn
async def bad_activity() -> dict:
    # Returns 10MB of data → stored in Event History
    return {"huge_dataset": [...]}  # ❌ Exceeds size limit!
```

✅ **Correct:**
```python
@activity.defn
async def good_activity() -> dict:
    huge_dataset = [...]
    # Store large data externally
    s3_key = await upload_to_s3(huge_dataset)
    # Return only reference
    return {"s3_key": s3_key, "size": len(huge_dataset)}  # ✅ Small result
```

### Summary: Key Takeaways

1. **Event History ≠ Cache**: Event History enables replay within a workflow, not performance optimization across workflows

2. **Determinism is Critical**: Workflows must be deterministic; cache reads are non-deterministic

3. **Cache in Activities**: Activities can be non-deterministic; put caching logic there

4. **External Storage Required**: Use Redis, DynamoDB, etc. for cross-workflow caching

5. **Manual Implementation**: No built-in Prefect-style caching; implement custom patterns

6. **Activity Results ARE Stored**: In Event History, but only for replay, not cross-workflow reuse

7. **Use Safe Alternatives**: `workflow.now()`, `workflow.random()`, `workflow.uuid4()` for determinism

**The Pattern:** Keep workflows deterministic (always call activities), let activities handle non-deterministic caching.

---

## Testing

### Testing with WorkflowEnvironment

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows import MyWorkflow
from activities import my_activity

@pytest.mark.asyncio
async def test_workflow():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Create worker
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[MyWorkflow],
            activities=[my_activity]
        ):
            # Execute workflow
            result = await env.client.execute_workflow(
                MyWorkflow.run,
                "test-input",
                id="test-workflow",
                task_queue="test-queue"
            )

            assert result == "expected-output"
```

### Time Skipping

```python
@pytest.mark.asyncio
async def test_workflow_with_timer():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[DelayedWorkflow],
            activities=[delayed_activity]
        ):
            # This completes instantly despite 1-hour sleep
            result = await env.client.execute_workflow(
                DelayedWorkflow.run,
                id="test-delayed",
                task_queue="test-queue"
            )

            assert result == "completed"
```

### Mocking Activities

```python
from temporalio import activity

# Original activity
@activity.defn
async def fetch_external_data(url: str) -> dict:
    # Real API call
    pass

# Mock activity for testing
@activity.defn
async def fetch_external_data_mock(url: str) -> dict:
    # Return test data
    return {"test": "data"}

@pytest.mark.asyncio
async def test_with_mock():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[MyWorkflow],
            activities=[fetch_external_data_mock]  # Use mock
        ):
            result = await env.client.execute_workflow(
                MyWorkflow.run,
                id="test",
                task_queue="test-queue"
            )

            assert "test" in result
```

### Activity Testing

```python
from temporalio.testing import ActivityEnvironment

@pytest.mark.asyncio
async def test_activity():
    env = ActivityEnvironment()

    # Test activity directly
    result = await env.run(my_activity, "input")

    assert result == "expected"
```

### Activity Testing with Heartbeats

```python
@pytest.mark.asyncio
async def test_activity_heartbeats():
    env = ActivityEnvironment()
    heartbeats = []

    # Capture heartbeats
    env.on_heartbeat = lambda *args: heartbeats.append(args[0])

    # Run activity
    result = await env.run(heartbeat_activity, 10)

    # Verify heartbeats
    assert len(heartbeats) == 10
```

### Workflow Replay Testing

```python
from temporalio.worker import Replayer

@pytest.mark.asyncio
async def test_replay():
    # Get workflow history from Temporal
    replayer = Replayer(workflows=[MyWorkflow])

    # Replay history to verify determinism
    await replayer.replay_workflow(history)
```

---

## Production Deployment

### Environment Configuration

```python
import os
from temporalio.client import Client, TLSConfig

async def create_client():
    env = os.getenv("ENVIRONMENT", "development")

    if env == "production":
        # Production: Connect to Temporal Cloud
        client = await Client.connect(
            f"{os.getenv('TEMPORAL_NAMESPACE')}.tmprl.cloud:7233",
            namespace=os.getenv('TEMPORAL_NAMESPACE'),
            tls=TLSConfig(
                client_cert=load_cert(),
                client_private_key=load_key()
            )
        )
    else:
        # Development: Local server
        client = await Client.connect("localhost:7233")

    return client
```

### Worker Deployment

```python
import asyncio
import logging
from temporalio.client import Client
from temporalio.worker import Worker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        # Connect to Temporal
        client = await create_client()
        logger.info("Connected to Temporal")

        # Create worker
        worker = Worker(
            client,
            task_queue=os.getenv("TASK_QUEUE", "default"),
            workflows=[...],
            activities=[...],
            max_concurrent_workflow_tasks=100,
            max_concurrent_activities=200
        )

        logger.info("Worker started")
        await worker.run()

    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
```

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run worker
CMD ["python", "run_worker.py"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  worker:
    build: .
    environment:
      - TEMPORAL_HOST=temporal:7233
      - TASK_QUEUE=production
      - ENVIRONMENT=production
    restart: unless-stopped
    deploy:
      replicas: 3
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal-worker
spec:
  replicas: 5
  selector:
    matchLabels:
      app: temporal-worker
  template:
    metadata:
      labels:
        app: temporal-worker
    spec:
      containers:
      - name: worker
        image: my-temporal-worker:latest
        env:
        - name: TEMPORAL_HOST
          value: "temporal.default.svc.cluster.local:7233"
        - name: TASK_QUEUE
          value: "production"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Monitoring and Observability

```python
import logging
from temporalio import workflow, activity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@activity.defn
async def monitored_activity(data: str) -> str:
    # Use activity logger
    activity.logger.info(f"Processing: {data}")

    # Activity info
    info = activity.info()
    activity.logger.info(
        f"Workflow: {info.workflow_id}, "
        f"Attempt: {info.attempt}"
    )

    return f"Processed: {data}"

@workflow.defn
class MonitoredWorkflow:
    @workflow.run
    async def run(self, data: str) -> str:
        # Use workflow logger
        workflow.logger.info(f"Starting workflow with: {data}")

        result = await workflow.execute_activity(
            monitored_activity,
            data,
            start_to_close_timeout=timedelta(seconds=30)
        )

        workflow.logger.info(f"Completed with: {result}")
        return result
```

### Metrics with Prometheus

```python
from prometheus_client import Counter, Histogram, start_http_server
import time

# Define metrics
workflow_executions = Counter(
    'temporal_workflow_executions_total',
    'Total workflow executions',
    ['workflow_type', 'status']
)

activity_duration = Histogram(
    'temporal_activity_duration_seconds',
    'Activity execution duration',
    ['activity_type']
)

@activity.defn
async def instrumented_activity(data: str) -> str:
    start = time.time()

    try:
        # Process data
        result = await process(data)
        return result
    finally:
        # Record duration
        duration = time.time() - start
        activity_duration.labels(
            activity_type='instrumented_activity'
        ).observe(duration)

# Start metrics server
start_http_server(8000)
```

---

## Best Practices

### 1. Workflow Design

#### ✅ Do: Keep Workflows Focused

```python
@workflow.defn
class OrderWorkflow:
    """Single responsibility: Process orders."""

    @workflow.run
    async def run(self, order: dict) -> dict:
        # Validate
        validation = await workflow.execute_activity(
            validate_order, order, ...
        )

        # Process
        result = await workflow.execute_activity(
            process_order, order, ...
        )

        # Notify
        await workflow.execute_activity(
            send_notification, result, ...
        )

        return result
```

#### ❌ Don't: Create Monolithic Workflows

```python
# Avoid workflows that do too many things
@workflow.defn
class EverythingWorkflow:
    """Bad: Handles orders, payments, shipping, inventory, etc."""
    # ... 1000 lines of code
```

### 2. Activity Design

#### ✅ Do: Make Activities Idempotent

```python
@activity.defn
async def idempotent_activity(order_id: str) -> dict:
    """Activity can safely retry without side effects."""

    # Check if already processed
    if await is_already_processed(order_id):
        return await get_existing_result(order_id)

    # Process with unique identifier
    result = await process_with_idempotency_key(order_id)

    return result
```

#### ✅ Do: Use Appropriate Timeouts

```python
@workflow.defn
class TimeoutWorkflow:
    @workflow.run
    async def run(self) -> str:
        # Short timeout for quick operations
        cache = await workflow.execute_activity(
            check_cache,
            start_to_close_timeout=timedelta(seconds=5)
        )

        # Longer timeout for external APIs
        data = await workflow.execute_activity(
            fetch_from_api,
            start_to_close_timeout=timedelta(seconds=30)
        )

        # Very long timeout for batch processing
        result = await workflow.execute_activity(
            process_large_batch,
            start_to_close_timeout=timedelta(minutes=30)
        )

        return result
```

### 3. Error Handling

#### ✅ Do: Handle Errors Gracefully

```python
from temporalio.exceptions import ActivityError, ApplicationError

@workflow.defn
class RobustWorkflow:
    @workflow.run
    async def run(self, data: str) -> dict:
        try:
            result = await workflow.execute_activity(
                risky_activity,
                data,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            return {"status": "success", "result": result}

        except ActivityError as e:
            # Activity failed after retries
            workflow.logger.error(f"Activity failed: {e}")
            return {"status": "failed", "error": str(e)}
```

#### ✅ Do: Use Retry Policies Wisely

```python
@workflow.defn
class RetryWorkflow:
    @workflow.run
    async def run(self) -> str:
        # Conservative retry for critical operations
        result = await workflow.execute_activity(
            critical_operation,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=60),
                backoff_coefficient=2.0,
                maximum_attempts=10
            )
        )

        return result
```

### 4. State Management

#### ✅ Do: Use Workflow State for Coordination

```python
@workflow.defn
class StatefulWorkflow:
    def __init__(self) -> None:
        self.processed_items = []
        self.total_count = 0
        self.failed_count = 0

    @workflow.run
    async def run(self, items: list) -> dict:
        self.total_count = len(items)

        for item in items:
            try:
                result = await workflow.execute_activity(
                    process_item, item, ...
                )
                self.processed_items.append(result)
            except Exception:
                self.failed_count += 1

        return {
            "total": self.total_count,
            "processed": len(self.processed_items),
            "failed": self.failed_count
        }

    @workflow.query
    def get_progress(self) -> dict:
        """Query current progress."""
        return {
            "total": self.total_count,
            "processed": len(self.processed_items),
            "failed": self.failed_count
        }
```

### 5. Testing

#### ✅ Do: Write Comprehensive Tests

```python
import pytest
from temporalio.testing import WorkflowEnvironment

@pytest.mark.asyncio
async def test_workflow_success():
    """Test successful workflow execution."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="test", workflows=[...], activities=[...]
        ):
            result = await env.client.execute_workflow(...)
            assert result["status"] == "success"

@pytest.mark.asyncio
async def test_workflow_failure():
    """Test workflow handles failures."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="test", workflows=[...], activities=[failing_activity]
        ):
            result = await env.client.execute_workflow(...)
            assert result["status"] == "failed"

@pytest.mark.asyncio
async def test_workflow_timeout():
    """Test workflow timeout handling."""
    # Test implementation
```

### 6. Naming Conventions

```python
# Workflows: Use descriptive names ending in "Workflow"
@workflow.defn
class ProcessOrderWorkflow: pass

@workflow.defn
class SendEmailWorkflow: pass

# Activities: Use verb-noun pattern
@activity.defn
async def validate_order(): pass

@activity.defn
async def send_notification(): pass

@activity.defn
async def update_inventory(): pass

# Task queues: Use domain-based names
task_queue = "orders-processing"
task_queue = "email-sending"
task_queue = "high-priority"
```

### 7. Observability

```python
@workflow.defn
class ObservableWorkflow:
    @workflow.run
    async def run(self, data: dict) -> dict:
        # Log important events
        workflow.logger.info(f"Starting workflow with: {data}")

        try:
            result = await workflow.execute_activity(
                process_data,
                data,
                start_to_close_timeout=timedelta(seconds=30)
            )

            workflow.logger.info(f"Activity completed: {result}")
            return {"status": "success", "result": result}

        except Exception as e:
            workflow.logger.error(f"Workflow failed: {e}")
            raise
```

### 8. Security

```python
import os

# Store secrets in environment variables
API_KEY = os.environ.get("API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

@activity.defn
async def secure_api_call(endpoint: str) -> dict:
    """Activity that uses secrets securely."""

    # Use encryption for sensitive data
    headers = {"Authorization": f"Bearer {API_KEY}"}

    # Make secure request
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint, headers=headers)
        return response.json()
```

---

## Quick Reference

### Common Imports

```python
# Core
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

# Testing
from temporalio.testing import WorkflowEnvironment, ActivityEnvironment

# Types
from datetime import timedelta
from typing import Optional, List, Dict
```

### Workflow Template

```python
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class MyWorkflow:
    def __init__(self) -> None:
        self.state = {}

    @workflow.run
    async def run(self, input_data: str) -> dict:
        result = await workflow.execute_activity(
            my_activity,
            input_data,
            start_to_close_timeout=timedelta(seconds=30)
        )
        return {"result": result}

    @workflow.signal
    def my_signal(self, data: str) -> None:
        self.state["signal_data"] = data

    @workflow.query
    def my_query(self) -> dict:
        return self.state
```

### Activity Template

```python
from temporalio import activity

@activity.defn
async def my_activity(input_data: str) -> str:
    """Activity description."""
    activity.logger.info(f"Processing: {input_data}")

    # Activity logic here
    result = await process(input_data)

    return result
```

### Worker Template

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="my-task-queue",
        workflows=[MyWorkflow],
        activities=[my_activity]
    )

    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Client Template

```python
import asyncio
from temporalio.client import Client
from workflows import MyWorkflow

async def main():
    client = await Client.connect("localhost:7233")

    result = await client.execute_workflow(
        MyWorkflow.run,
        "input-data",
        id="my-workflow-001",
        task_queue="my-task-queue"
    )

    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Additional Resources

### Official Documentation
- **Main Docs**: [docs.temporal.io](https://docs.temporal.io)
- **Python SDK**: [docs.temporal.io/develop/python](https://docs.temporal.io/develop/python)
- **API Reference**: [python.temporal.io](https://python.temporal.io)
- **Learn Temporal**: [learn.temporal.io](https://learn.temporal.io)

### Code Samples
- **GitHub**: [github.com/temporalio/samples-python](https://github.com/temporalio/samples-python)
- **SDK Repository**: [github.com/temporalio/sdk-python](https://github.com/temporalio/sdk-python)

### Community
- **Slack**: [temporal.io/slack](https://temporal.io/slack)
- **Community Forum**: [community.temporal.io](https://community.temporal.io)
- **YouTube**: Temporal Technologies channel

### Tools
- **Temporal CLI**: [docs.temporal.io/cli](https://docs.temporal.io/cli)
- **Web UI**: Included with local server at `localhost:8233`
- **Cloud**: [cloud.temporal.io](https://cloud.temporal.io)

---

## Changelog (2025)

- **Python SDK 1.8+**: Latest stable version
- **Enhanced Testing**: Time-skipping improvements
- **Nexus**: Cross-namespace communication
- **Improved Observability**: Better logging and metrics
- **Schedule Updates**: Enhanced cron support
- **Security**: Improved encryption options

---

*Last Updated: 2025 - This guide reflects the current state of Temporal for use with Claude Code.*
