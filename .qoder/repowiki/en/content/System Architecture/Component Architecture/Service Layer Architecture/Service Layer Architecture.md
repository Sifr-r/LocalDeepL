# Service Layer Architecture

<cite>
**Referenced Files in This Document**
- [server.py](file://src/omniscribe/server.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [tasks.py](file://src/omniscribe/api/tasks.py)
- [jobs.py](file://src/omniscribe/api/routers/jobs.py)
- [artifacts.py](file://src/omniscribe/api/routers/artifacts.py)
- [translation.py](file://src/omniscribe/api/routers/translation.py)
- [extraction.py](file://src/omniscribe/api/routers/extraction.py)
- [ocr.py](file://src/omniscribe/api/routers/ocr.py)
- [state.py](file://src/omniscribe/api/routers/state.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [ai_service.py](file://src/omniscribe/api/services/ai.py)
- [document_metadata_service.py](file://src/omniscribe/api/services/document_metadata.py)
- [document_exports_service.py](file://src/omniscribe/api/services/document_exports.py)
- [tree_artifact_service.py](file://src/omniscribe/api/services/tree_artifact.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)
- [conftest.py](file://tests/conftest.py)
- [test_jobs_progress_services.py](file://tests/test_jobs_progress_services.py)
- [test_security_qa.py](file://tests/test_security_qa.py)
- [test_workflows_base.py](file://tests/test_workflows_base.py)
- [test_workflows_grounded.py](file://tests/test_workflows_grounded.py)
- [test_workflows_hybrid.py](file://tests/test_workflows_hybrid.py)
</cite>

## Update Summary
**Changes Made**
- Added documentation for new OCR chunked runner service
- Added documentation for enhanced OCR job management service
- Added documentation for HTTP fetch service for external resource handling
- Added documentation for state backend services with Redis support
- Enhanced security services documentation with improved authentication and authorization patterns
- Updated architecture diagrams to reflect new service components

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document describes the service layer architecture of LocalDeepL, focusing on business logic abstraction, service composition patterns, and dependency management. It explains job management, workflow orchestration, artifact handling, security services, progress tracking, and cross-cutting concerns such as middleware and configuration. It also covers interface definitions, error propagation, transactional boundaries, and testing strategies including mocking approaches.

The service layer has been enhanced with new specialized services for OCR processing, HTTP resource fetching, and state management with Redis backend support, providing a more robust and scalable architecture.

## Project Structure
The service layer is organized under src/omniscribe/api/services and integrates with FastAPI routers, Celery tasks, and core workflow implementations:

- Routers expose HTTP endpoints and delegate to services.
- Services encapsulate business logic and coordinate workflows, artifacts, jobs, and security.
- Core workflows define reusable processing pipelines (grounded, hybrid).
- Celery app and tasks provide asynchronous execution for long-running operations.
- Security middleware and configuration enforce access control and policy.
- Progress service provides real-time status updates via websockets.
- New specialized services handle OCR chunking, HTTP fetching, and state persistence.

```mermaid
graph TB
subgraph "HTTP API"
R_J["Routers: Jobs"]
R_A["Routers: Artifacts"]
R_T["Routers: Translation"]
R_E["Routers: Extraction"]
R_O["Routers: OCR"]
R_S["Routers: State"]
R_W["Routers: Websocket"]
end
subgraph "Service Layer"
S_J["Jobs Service"]
S_A["Artifacts Service"]
S_WF["Workflow Service"]
S_P["Progress Service"]
S_SEC["Security Service"]
S_SM["Security Middleware"]
S_SC["Security Config"]
S_AI["AI Service"]
S_DM["Document Metadata Service"]
S_DE["Document Exports Service"]
S_TA["Tree Artifact Service"]
S_OCR_CR["OCR Chunked Runner"]
S_OCR_J["OCR Jobs Service"]
S_HTTP["HTTP Fetch Service"]
S_STATE["State Backend"]
S_STATE_R["State Backend Redis"]
end
subgraph "Async Execution"
C_APP["Celery App"]
C_TASKS["Tasks"]
end
subgraph "Core Workflows"
W_BASE["Base Workflow"]
W_G["Grounded Workflow"]
W_H["Hybrid Workflow"]
end
R_J --> S_J
R_A --> S_A
R_T --> S_WF
R_E --> S_WF
R_O --> S_WF
R_S --> S_P
R_W --> S_P
S_J --> C_APP
S_WF --> C_TASKS
S_SEC --> S_SM
S_SM --> S_SC
S_WF --> W_BASE
W_G --> W_BASE
W_H --> W_BASE
S_A --> S_TA
S_WF --> S_DM
S_WF --> S_DE
S_WF --> S_AI
S_OCR_CR --> S_OCR_J
S_OCR_J --> S_STATE
S_HTTP --> S_STATE
S_STATE --> S_STATE_R
```

**Diagram sources**
- [server.py](file://src/omniscribe/server.py)
- [jobs.py](file://src/omniscribe/api/routers/jobs.py)
- [artifacts.py](file://src/omniscribe/api/routers/artifacts.py)
- [translation.py](file://src/omniscribe/api/routers/translation.py)
- [extraction.py](file://src/omniscribe/api/routers/extraction.py)
- [ocr.py](file://src/omniscribe/api/routers/ocr.py)
- [state.py](file://src/omniscribe/api/routers/state.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)
- [ai_service.py](file://src/omniscribe/api/services/ai.py)
- [document_metadata_service.py](file://src/omniscribe/api/services/document_metadata.py)
- [document_exports_service.py](file://src/omniscribe/api/services/document_exports.py)
- [tree_artifact_service.py](file://src/omniscribe/api/services/tree_artifact.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [tasks.py](file://src/omniscribe/api/tasks.py)

**Section sources**
- [server.py](file://src/omniscribe/server.py)
- [jobs.py](file://src/omniscribe/api/routers/jobs.py)
- [artifacts.py](file://src/omniscribe/api/routers/artifacts.py)
- [translation.py](file://src/omniscribe/api/routers/translation.py)
- [extraction.py](file://src/omniscribe/api/routers/extraction.py)
- [ocr.py](file://src/omniscribe/api/routers/ocr.py)
- [state.py](file://src/omniscribe/api/routers/state.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)
- [ai_service.py](file://src/omniscribe/api/services/ai.py)
- [document_metadata_service.py](file://src/omniscribe/api/services/document_metadata.py)
- [document_exports_service.py](file://src/omniscribe/api/services/document_exports.py)
- [tree_artifact_service.py](file://src/omniscribe/api/services/tree_artifact.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [tasks.py](file://src/omniscribe/api/tasks.py)

## Core Components
- Job Management Service: Creates, queries, and manages lifecycle of translation/extraction jobs; coordinates async task submission and result retrieval.
- Workflow Orchestration Service: Composes multi-step pipelines using base workflow abstractions; selects grounded or hybrid strategies based on input characteristics.
- Artifact Handling Services: Persist and retrieve artifacts (documents, trees, exports); ensure consistent storage semantics and versioning.
- Security Service and Middleware: Enforce authentication, authorization, and policy checks across requests; centralize configuration.
- Progress Service: Publishes granular progress events and exposes them via state endpoints and websockets.
- AI Service: Encapsulates LLM calls and provider selection for grounding and hybrid workflows.
- Document Metadata and Export Services: Manage metadata extraction and export formats.
- **New**: OCR Chunked Runner Service: Handles large document processing by splitting into manageable chunks for parallel OCR processing.
- **New**: OCR Jobs Service: Specialized job management for OCR-specific workflows and state tracking.
- **New**: HTTP Fetch Service: Manages external resource fetching with retry logic and caching capabilities.
- **New**: State Backend Services: Abstract state persistence with pluggable backends including Redis for high-performance scenarios.

Key responsibilities and interactions are defined by service interfaces and composed within routers and tasks.

**Section sources**
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [tree_artifact_service.py](file://src/omniscribe/api/services/tree_artifact.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [ai_service.py](file://src/omniscribe/api/services/ai.py)
- [document_metadata_service.py](file://src/omniscribe/api/services/document_metadata.py)
- [document_exports_service.py](file://src/omniscribe/api/services/document_exports.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)

## Architecture Overview
The service layer follows a layered architecture with enhanced modularity:
- HTTP routers accept requests, validate inputs, and call services.
- Services implement business logic, orchestrate workflows, and manage artifacts.
- Core workflows provide composable steps for OCR, grounding, translation, and post-processing.
- Celery executes long-running tasks asynchronously; progress is emitted to the progress service and broadcast via websockets.
- Security middleware intercepts requests to enforce policies before reaching routers.
- New state backend abstraction enables flexible persistence strategies.
- Specialized OCR services handle large document processing efficiently.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Router as "Translation Router"
participant SecMW as "Security Middleware"
participant SecSvc as "Security Service"
participant JobSvc as "Jobs Service"
participant WF as "Workflow Service"
participant OCRRunner as "OCR Chunked Runner"
participant StateBackend as "State Backend"
participant Celery as "Celery Tasks"
participant Prog as "Progress Service"
participant WS as "Websocket"
Client->>Router : "POST /translate"
Router->>SecMW : "Request"
SecMW->>SecSvc : "Validate authz"
SecSvc-->>SecMW : "OK"
Router->>JobSvc : "Create job"
JobSvc->>WF : "Start workflow"
WF->>OCRRunner : "Process chunks"
OCRRunner->>StateBackend : "Store progress"
WF->>Celery : "Submit task"
Celery-->>Prog : "Emit progress events"
Prog-->>WS : "Broadcast updates"
Celery-->>WF : "Task complete"
WF-->>JobSvc : "Persist results"
JobSvc-->>Router : "Job ID"
Router-->>Client : "202 Accepted"
```

**Diagram sources**
- [translation.py](file://src/omniscribe/api/routers/translation.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [tasks.py](file://src/omniscribe/api/tasks.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)

## Detailed Component Analysis

### Job Management Service
Responsibilities:
- Create jobs with unique identifiers and initial states.
- Track job lifecycle: queued, running, completed, failed.
- Provide query APIs for job status and results.
- Coordinate with workflow service and Celery tasks.

Interface highlights:
- create_job(input_spec) -> job_id
- get_job(job_id) -> job_state
- list_jobs(filters) -> job_list
- cancel_job(job_id) -> bool

Error propagation:
- Returns structured errors for invalid inputs, not found, and permission denied.
- Wraps Celery exceptions into domain-level errors.

Transaction management:
- Ensures atomic creation of job records and initial progress entries.
- Uses rollback on failure during persistence.

```mermaid
classDiagram
class JobsService {
+create_job(input_spec) string
+get_job(job_id) JobState
+list_jobs(filters) JobState[]
+cancel_job(job_id) bool
-_persist_job(job) void
-_validate_input(spec) void
}
class CeleryApp {
+send_task(name, args) Task
}
class ProgressService {
+emit(job_id, event) void
}
JobsService --> CeleryApp : "submits tasks"
JobsService --> ProgressService : "emits progress"
```

**Diagram sources**
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)

**Section sources**
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)

### Workflow Orchestration Service
Responsibilities:
- Select appropriate workflow strategy (grounded vs hybrid).
- Compose steps: preprocessing, OCR, grounding, translation, postprocessing.
- Manage callbacks and progress emission.
- Handle retries and error recovery.

Composition patterns:
- Strategy pattern for selecting grounded or hybrid workflows.
- Pipeline pattern for stepwise processing.
- Observer pattern for progress callbacks.

```mermaid
classDiagram
class BaseWorkflow {
+execute(context) Result
+on_step(step, progress) void
+on_error(error) void
}
class GroundedWorkflow {
+execute(context) Result
}
class HybridWorkflow {
+execute(context) Result
}
class WorkflowService {
+run(input_spec) JobResult
-_select_strategy(input_spec) BaseWorkflow
}
BaseWorkflow <|-- GroundedWorkflow
BaseWorkflow <|-- HybridWorkflow
WorkflowService --> BaseWorkflow : "uses"
```

**Diagram sources**
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)

**Section sources**
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)

### Artifact Handling Services
Responsibilities:
- Store and retrieve artifacts (documents, tree structures, exports).
- Ensure consistency between artifact versions and job results.
- Provide efficient listing and filtering.

Services:
- Artifacts Service: high-level artifact operations.
- Tree Artifact Service: specialized handling for hierarchical artifacts.

```mermaid
classDiagram
class ArtifactsService {
+store(job_id, artifact_type, data) string
+retrieve(artifact_id) Artifact
+list_by_job(job_id) Artifact[]
}
class TreeArtifactService {
+build_tree(nodes) Tree
+export(tree, format) bytes
}
ArtifactsService --> TreeArtifactService : "uses"
```

**Diagram sources**
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [tree_artifact_service.py](file://src/omniscribe/api/services/tree_artifact.py)

**Section sources**
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [tree_artifact_service.py](file://src/omniscribe/api/services/tree_artifact.py)

### Security Service and Middleware
Responsibilities:
- Validate tokens and enforce role-based access.
- Centralize security configuration.
- Intercept requests to protect endpoints.

Patterns:
- Middleware pattern for request interception.
- Configuration-driven policy enforcement.

Enhanced Features:
- Improved token validation with multiple provider support.
- Granular permission checking with resource-level access control.
- Centralized security policy management.

```mermaid
classDiagram
class SecurityMiddleware {
+process_request(request) Response
-_check_auth(request) bool
}
class SecurityService {
+verify_token(token) Claims
+authorize(user, resource) bool
+_validate_permissions(user, resource) bool
}
class SecurityConfig {
+load() Policy
+is_enabled() bool
+_load_policies() dict
}
SecurityMiddleware --> SecurityService : "delegates"
SecurityService --> SecurityConfig : "reads policy"
```

**Diagram sources**
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)

**Section sources**
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)

### Progress Tracking Mechanisms
Responsibilities:
- Emit granular progress events per job.
- Broadcast updates via websockets.
- Provide state queries for clients.

Flow:
- Workflow steps emit progress events.
- Progress service persists and broadcasts.
- State router exposes current status.

```mermaid
sequenceDiagram
participant WF as "Workflow Step"
participant PS as "Progress Service"
participant SR as "State Router"
participant WS as "Websocket"
WF->>PS : "emit(job_id, step, pct)"
PS-->>SR : "update state store"
PS-->>WS : "broadcast event"
SR-->>Client : "GET /state/{job_id}"
```

**Diagram sources**
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [state.py](file://src/omniscribe/api/routers/state.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)

**Section sources**
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [state.py](file://src/omniscribe/api/routers/state.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)

### OCR Chunked Runner Service
**New Component**

Responsibilities:
- Split large documents into manageable chunks for parallel OCR processing.
- Coordinate chunk processing with progress tracking.
- Merge OCR results from multiple chunks into final output.
- Handle chunk-specific errors and retries.

Features:
- Configurable chunk size based on document characteristics.
- Parallel processing with configurable concurrency limits.
- Memory-efficient processing of large documents.
- Automatic chunk merging and validation.

```mermaid
classDiagram
class OCRChunkedRunner {
+process_document(document) OCRResult
-_split_into_chunks(document) List[Chunk]
-_process_chunk(chunk) OCRResult
-_merge_results(chunks_results) OCRResult
-_handle_chunk_errors(errors) void
}
class OCRJobsService {
+submit_chunked_job(document) JobID
+monitor_chunk_progress(job_id) Progress
+cancel_chunked_job(job_id) bool
}
OCRChunkedRunner --> OCRJobsService : "coordinates"
```

**Diagram sources**
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)

**Section sources**
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)

### HTTP Fetch Service
**New Component**

Responsibilities:
- Manage external resource fetching with retry logic and caching.
- Handle various content types and encoding detection.
- Implement timeout and rate limiting for external requests.
- Provide fallback mechanisms for failed requests.

Features:
- Configurable retry policies with exponential backoff.
- Content-type specific parsing and validation.
- Request caching with TTL support.
- Comprehensive error handling and logging.

```mermaid
classDiagram
class HTTPFetchService {
+fetch(url, options) Response
+_retry_with_backoff(request) Response
+_cache_response(url, response) void
-_detect_content_type(response) str
-_validate_response(response) bool
}
class CacheManager {
+get(key) any
+set(key, value, ttl) void
+invalidate(key) void
}
HTTPFetchService --> CacheManager : "uses"
```

**Diagram sources**
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)

**Section sources**
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)

### State Backend Services
**New Component**

Responsibilities:
- Abstract state persistence with pluggable backend implementations.
- Provide consistent interface for different storage backends.
- Support high-performance Redis backend for production deployments.
- Enable easy switching between in-memory and persistent storage.

Features:
- Pluggable backend architecture with common interface.
- Redis backend with connection pooling and serialization.
- In-memory backend for development and testing.
- Transaction support for atomic operations.

```mermaid
classDiagram
class StateBackend {
+get(key) any
+set(key, value) void
+delete(key) bool
+exists(key) bool
+_serialize(value) bytes
-_deserialize(data) any
}
class StateBackendRedis {
+connect() Connection
+get(key) any
+set(key, value) void
+_redis_operations() dict
}
class StateBackendInMemory {
+initialize() void
+get(key) any
+set(key, value) void
+_memory_store() dict
}
StateBackend <|-- StateBackendRedis
StateBackend <|-- StateBackendInMemory
```

**Diagram sources**
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)

**Section sources**
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)

### Cross-Cutting Concerns
- Logging and metrics: centralized logging in services and tasks.
- Error normalization: consistent error shapes across services.
- Configuration loading: environment-driven settings for security and workflows.
- Dependency injection: services receive dependencies explicitly for testability.
- **New**: Backend abstraction: pluggable storage backends with consistent interfaces.
- **New**: Retry patterns: standardized retry logic with exponential backoff.
- **New**: Caching strategies: configurable caching with TTL and invalidation.

## Dependency Analysis
Service dependencies are explicit and minimal with enhanced modularity:
- Routers depend on services only.
- Services depend on core workflows, Celery app, and utility services.
- Security middleware depends on security service and config.
- Progress service is used by workflows and exposed via routers.
- **New**: OCR services depend on state backends for persistence.
- **New**: HTTP fetch service uses cache managers and retry policies.
- **New**: State backends provide pluggable storage abstraction.

```mermaid
graph LR
Router_Translation["Translation Router"] --> Service_Workflow["Workflow Service"]
Router_Jobs["Jobs Router"] --> Service_Jobs["Jobs Service"]
Router_Artifacts["Artifacts Router"] --> Service_Artifacts["Artifacts Service"]
Service_Workflow --> Core_Base["Base Workflow"]
Service_Workflow --> Core_Grounded["Grounded Workflow"]
Service_Workflow --> Core_Hybrid["Hybrid Workflow"]
Service_Jobs --> Celery_App["Celery App"]
Service_Workflow --> Service_Progress["Progress Service"]
Security_MW["Security Middleware"] --> Security_Service["Security Service"]
Security_Service --> Security_Config["Security Config"]
Service_OCR_Runner["OCR Chunked Runner"] --> Service_OCR_Jobs["OCR Jobs Service"]
Service_OCR_Jobs --> Service_State_Backend["State Backend"]
Service_HTTP_Fetch["HTTP Fetch Service"] --> Service_Cache["Cache Manager"]
Service_State_Backend --> Service_State_Backend_Redis["State Backend Redis"]
```

**Diagram sources**
- [translation.py](file://src/omniscribe/api/routers/translation.py)
- [jobs.py](file://src/omniscribe/api/routers/jobs.py)
- [artifacts.py](file://src/omniscribe/api/routers/artifacts.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)

**Section sources**
- [translation.py](file://src/omniscribe/api/routers/translation.py)
- [jobs.py](file://src/omniscribe/api/routers/jobs.py)
- [artifacts.py](file://src/omniscribe/api/routers/artifacts.py)
- [workflow_service.py](file://src/omniscribe/api/services/workflow.py)
- [jobs_service.py](file://src/omniscribe/api/services/jobs.py)
- [artifacts_service.py](file://src/omniscribe/api/services/artifacts.py)
- [progress_service.py](file://src/omniscribe/api/services/progress.py)
- [security_middleware.py](file://src/omniscribe/api/services/security_middleware.py)
- [security_service.py](file://src/omniscribe/api/services/security.py)
- [security_config.py](file://src/omniscribe/api/services/security_config.py)
- [base_workflow.py](file://src/omniscribe/core/workflows/base.py)
- [grounded_workflow.py](file://src/omniscribe/core/workflows/grounded.py)
- [hybrid_workflow.py](file://src/omniscribe/core/workflows/hybrid.py)
- [celery_app.py](file://src/omniscribe/api/celery_app.py)
- [ocr_chunked_runner.py](file://src/omniscribe/api/services/ocr_chunked_runner.py)
- [ocr_jobs.py](file://src/omniscribe/api/services/ocr_jobs.py)
- [http_fetch.py](file://src/omniscribe/api/services/http_fetch.py)
- [state_backend.py](file://src/omniscribe/api/services/state_backend.py)
- [state_backend_redis.py](file://src/omniscribe/api/services/state_backend_redis.py)

## Performance Considerations
- Asynchronous execution: Use Celery for CPU-bound and I/O-heavy steps to avoid blocking HTTP responses.
- Streaming progress: Emit frequent small progress events to keep clients updated without heavy payloads.
- Artifact caching: Cache frequently accessed artifacts and metadata to reduce disk I/O.
- Workflow optimization: Choose grounded workflow for text-heavy documents; hybrid for mixed content to balance accuracy and speed.
- Resource limits: Configure Celery concurrency and memory limits per worker type.
- **New**: Chunked processing: Process large documents in chunks to optimize memory usage and enable parallel processing.
- **New**: Redis backend: Use Redis for high-performance state persistence in production environments.
- **New**: HTTP caching: Implement intelligent caching for external resource fetching to reduce network overhead.
- **New**: Connection pooling: Use connection pooling for database and Redis connections to improve throughput.

## Troubleshooting Guide
Common issues and resolutions:
- Job stuck in queued state: Check Celery workers and task queues; verify task submission logs.
- Progress not updating: Ensure progress service emits events at each workflow step; confirm websocket connections are active.
- Security failures: Validate token format and permissions; review security config and middleware logs.
- Artifact retrieval errors: Verify artifact IDs and storage backend availability; check permissions.
- **New**: OCR processing failures: Check chunk size configuration and memory limits; verify OCR service availability.
- **New**: HTTP fetch timeouts: Review timeout configurations and retry policies; check network connectivity.
- **New**: State backend issues: Verify Redis connection and credentials; check backend availability and capacity.

Diagnostic utilities:
- State endpoint for job details.
- Websocket client for live progress.
- Security QA tests for policy validation.
- **New**: Health check endpoints for backend services.
- **New**: Performance monitoring for chunked processing.

**Section sources**
- [state.py](file://src/omniscribe/api/routers/state.py)
- [websocket.py](file://src/omniscribe/api/routers/websocket.py)
- [test_security_qa.py](file://tests/test_security_qa.py)

## Conclusion
LocalDeepL's service layer cleanly separates HTTP concerns from business logic through well-defined services. Job management, workflow orchestration, artifact handling, security, and progress tracking are modular and composable. The design supports asynchronous execution, robust error propagation, and clear testing strategies. 

The recent enhancements with OCR chunked processing, HTTP resource management, and pluggable state backends significantly improve scalability and performance. The architecture now supports large document processing, efficient external resource handling, and flexible persistence strategies. Adopting these patterns ensures maintainability and scalability as features evolve.

## Appendices

### Service Interface Definitions
- Jobs Service: create_job, get_job, list_jobs, cancel_job.
- Workflow Service: run, select_strategy, handle_callbacks.
- Artifacts Service: store, retrieve, list_by_job.
- Tree Artifact Service: build_tree, export.
- Security Service: verify_token, authorize.
- Progress Service: emit, get_status.
- **New**: OCR Chunked Runner: process_document, split_into_chunks, merge_results.
- **New**: OCR Jobs Service: submit_chunked_job, monitor_progress, cancel_job.
- **New**: HTTP Fetch Service: fetch, retry_with_backoff, cache_response.
- **New**: State Backend: get, set, delete, exists.

### Error Propagation Patterns
- Normalize exceptions into domain-specific error objects.
- Include contextual information (job_id, step, message).
- Surface user-friendly messages while preserving detailed logs.
- **New**: Backend-specific error handling with graceful degradation.
- **New**: Network error classification with retry recommendations.

### Transaction Management
- Atomic job creation with initial progress entry.
- Rollback on persistence failures.
- Idempotent task completion handlers.
- **New**: Backend transaction support for atomic operations.
- **New**: Distributed transaction coordination for microservices.

### Testing Strategies and Mocking Approaches
- Unit tests for services with mocked dependencies (Celery, progress, artifacts).
- Integration tests for routers invoking services and verifying responses.
- Workflow tests covering base, grounded, and hybrid strategies.
- Security tests validating middleware and policy enforcement.
- **New**: Backend abstraction tests with multiple implementations.
- **New**: HTTP mock server for external service simulation.
- **New**: Performance tests for chunked processing scenarios.

Example test files:
- conftest.py for shared fixtures.
- test_jobs_progress_services.py for job and progress behavior.
- test_security_qa.py for security validations.
- test_workflows_base.py, test_workflows_grounded.py, test_workflows_hybrid.py for workflow strategies.
- **New**: test_ocr_chunked_runner.py for chunked processing tests.
- **New**: test_http_fetch.py for external resource handling tests.
- **New**: test_state_backend.py for persistence backend tests.

**Section sources**
- [conftest.py](file://tests/conftest.py)
- [test_jobs_progress_services.py](file://tests/test_jobs_progress_services.py)
- [test_security_qa.py](file://tests/test_security_qa.py)
- [test_workflows_base.py](file://tests/test_workflows_base.py)
- [test_workflows_grounded.py](file://tests/test_workflows_grounded.py)
- [test_workflows_hybrid.py](file://tests/test_workflows_hybrid.py)