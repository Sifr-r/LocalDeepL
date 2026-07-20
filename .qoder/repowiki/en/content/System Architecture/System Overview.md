# System Overview

<cite>
**Referenced Files in This Document**
- [server.py](file://src/local_deepl/server.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)
- [translation.py](file://src/local_deepl/api/routers/translation.py)
- [extraction.py](file://src/local_deepl/api/routers/extraction.py)
- [jobs.py](file://src/local_deepl/api/routers/jobs.py)
- [ocr.py](file://src/local_deepl/api/routers/ocr.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [pipeline.py](file://src/local_deepl/pipeline.py)
- [document.py](file://src/local_deepl/core/document.py)
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [processors.py](file://src/local_deepl/core/processors.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [docx_writer.py](file://src/local_deepl/core/docx_writer.py)
- [html_writer.py](file://src/local_deepl/core/html_writer.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [nllb_engine.py](file://src/local_deepl/core/nllb_engine.py)
- [trocr_engine.py](file://src/local_deepl/core/trocr_engine.py)
- [client.py](file://src/local_deepl/core/ocr/client.py)
- [filters.py](file://src/local_deepl/core/ocr/filters.py)
- [prompted.py](file://src/local_deepl/core/grounded/prompted.py)
- [rasterize.py](file://src/local_deepl/core/grounded/rasterize.py)
- [compose.yaml](file://compose.yaml)
- [Dockerfile](file://Dockerfile)
</cite>

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
This section provides a high-level overview of LocalDeepL’s system architecture and design principles. The platform is a local-first document translation and extraction service that supports multiple input formats (PDF, DOCX, images), OCR for scanned or image-based content, and LLM-assisted grounded processing. It exposes a FastAPI HTTP API, WebSocket endpoints for real-time progress updates, and Celery background workers to execute long-running tasks such as OCR, translation, and export.

Key goals:
- Provide a robust, scalable backend for multi-format document processing
- Enable real-time feedback via WebSockets
- Support pluggable OCR and translation engines
- Maintain clear boundaries between API, orchestration, and core processing logic

## Project Structure
The repository follows a layered structure:
- API layer: FastAPI routers, services, schemas, and Celery integration
- Core layer: Document models, preprocessing, processors, translation, post-processing, and writers
- Workflows: Pluggable pipelines for grounded and hybrid processing strategies
- Utilities: Shared helpers for file handling, image processing, and providers
- Static assets: Frontend UI components served by the server

```mermaid
graph TB
subgraph "API Layer"
A["FastAPI Routers<br/>translation.py, extraction.py, jobs.py, ocr.py, websocket.py"]
S["Services<br/>workflow.py, progress.py, security_*"]
C["Celery App & Tasks<br/>celery_app.py, tasks.py"]
end
subgraph "Core Layer"
D["Document Model<br/>document.py"]
P["Preprocessing<br/>preprocessing.py"]
PR["Processors<br/>processors.py"]
T["Translation<br/>dual_translator.py, nllb_engine.py, trocr_engine.py"]
PP["Post-processing<br/>postprocess.py"]
W["Writers<br/>docx_writer.py, html_writer.py, tree_export.py"]
end
subgraph "Workflows"
WF["Workflow Base<br/>workflows/base.py"]
WG["Grounded Workflow<br/>workflows/grounded.py"]
WH["Hybrid Workflow<br/>workflows/hybrid.py"]
end
subgraph "OCR Subsystem"
OC["OCR Client<br/>ocr/client.py"]
OF["Filters<br/>ocr/filters.py"]
end
subgraph "Deployment"
DC["Dockerfile"]
CO["compose.yaml"]
end
A --> S
S --> C
C --> WF
WF --> D
WF --> P
WF --> PR
WF --> T
WF --> PP
WF --> W
WF --> OC
WF --> OF
A --> WS["WebSocket Router<br/>websocket.py"]
DC --> CO
```

**Diagram sources**
- [server.py:1-200](file://src/local_deepl/server.py#L1-L200)
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [websocket.py:1-150](file://src/local_deepl/api/routers/websocket.py#L1-L150)
- [workflow.py:1-200](file://src/local_deepl/api/services/workflow.py#L1-L200)
- [progress.py:1-120](file://src/local_deepl/api/services/progress.py#L1-L120)
- [pipeline.py:1-120](file://src/local_deepl/pipeline.py#L1-L120)
- [document.py:1-120](file://src/local_deepl/core/document.py#L1-L120)
- [preprocessing.py:1-120](file://src/local_deepl/core/preprocessing.py#L1-L120)
- [processors.py:1-120](file://src/local_deepl/core/processors.py#L1-L120)
- [dual_translator.py:1-120](file://src/local_deepl/core/dual_translator.py#L1-L120)
- [postprocess.py:1-120](file://src/local_deepl/core/postprocess.py#L1-L120)
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)
- [grounded.py:1-120](file://src/local_deepl/core/workflows/grounded.py#L1-L120)
- [hybrid.py:1-120](file://src/local_deepl/core/workflows/hybrid.py#L1-L120)
- [base.py:1-120](file://src/local_deepl/core/workflows/base.py#L1-L120)
- [nllb_engine.py:1-120](file://src/local_deepl/core/nllb_engine.py#L1-L120)
- [trocr_engine.py:1-120](file://src/local_deepl/core/trocr_engine.py#L1-L120)
- [client.py:1-120](file://src/local_deepl/core/ocr/client.py#L1-L120)
- [filters.py:1-120](file://src/local_deepl/core/ocr/filters.py#L1-L120)
- [prompted.py:1-120](file://src/local_deepl/core/grounded/prompted.py#L1-L120)
- [rasterize.py:1-120](file://src/local_deepl/core/grounded/rasterize.py#L1-L120)
- [compose.yaml:1-120](file://compose.yaml#L1-L120)
- [Dockerfile:1-120](file://Dockerfile#L1-L120)

**Section sources**
- [server.py:1-200](file://src/local_deepl/server.py#L1-L200)
- [compose.yaml:1-120](file://compose.yaml#L1-L120)
- [Dockerfile:1-120](file://Dockerfile#L1-L120)

## Core Components
- FastAPI Backend: Exposes REST endpoints for translation, extraction, OCR, and job management; serves static frontend assets.
- Celery Workers: Execute long-running tasks asynchronously, including OCR, translation, and export operations.
- WebSocket Service: Provides real-time progress updates and event streaming to clients.
- Document Processing Pipeline: Orchestrates preprocessing, OCR, translation, post-processing, and output generation across multiple formats.
- Workflows: Encapsulate different strategies (grounded, hybrid) with shared base behavior and callbacks.
- OCR Subsystem: Integrates OCR client and filters for scanned/image inputs.
- Writers: Generate final artifacts in DOCX, HTML, and structured tree exports.

**Section sources**
- [translation.py:1-200](file://src/local_deepl/api/routers/translation.py#L1-L200)
- [extraction.py:1-200](file://src/local_deepl/api/routers/extraction.py#L1-L200)
- [jobs.py:1-200](file://src/local_deepl/api/routers/jobs.py#L1-L200)
- [ocr.py:1-200](file://src/local_deepl/api/routers/ocr.py#L1-L200)
- [websocket.py:1-150](file://src/local_deepl/api/routers/websocket.py#L1-L150)
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [workflow.py:1-200](file://src/local_deepl/api/services/workflow.py#L1-L200)
- [progress.py:1-120](file://src/local_deepl/api/services/progress.py#L1-L120)
- [pipeline.py:1-120](file://src/local_deepl/pipeline.py#L1-L120)
- [document.py:1-120](file://src/local_deepl/core/document.py#L1-L120)
- [preprocessing.py:1-120](file://src/local_deepl/core/preprocessing.py#L1-L120)
- [processors.py:1-120](file://src/local_deepl/core/processors.py#L1-L120)
- [dual_translator.py:1-120](file://src/local_deepl/core/dual_translator.py#L1-L120)
- [postprocess.py:1-120](file://src/local_deepl/core/postprocess.py#L1-L120)
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)
- [grounded.py:1-120](file://src/local_deepl/core/workflows/grounded.py#L1-L120)
- [hybrid.py:1-120](file://src/local_deepl/core/workflows/hybrid.py#L1-L120)
- [base.py:1-120](file://src/local_deepl/core/workflows/base.py#L1-L120)
- [nllb_engine.py:1-120](file://src/local_deepl/core/nllb_engine.py#L1-L120)
- [trocr_engine.py:1-120](file://src/local_deepl/core/trocr_engine.py#L1-L120)
- [client.py:1-120](file://src/local_deepl/core/ocr/client.py#L1-L120)
- [filters.py:1-120](file://src/local_deepl/core/ocr/filters.py#L1-L120)
- [prompted.py:1-120](file://src/local_deepl/core/grounded/prompted.py#L1-L120)
- [rasterize.py:1-120](file://src/local_deepl/core/grounded/rasterize.py#L1-L120)

## Architecture Overview
LocalDeepL uses a decoupled architecture:
- API Gateway: FastAPI handles HTTP requests and routes them to services.
- Orchestration Services: Manage workflow execution, task submission, and progress tracking.
- Background Workers: Celery processes heavy tasks off the request path.
- Core Pipeline: Executes document processing steps with pluggable engines and writers.
- Real-time Updates: WebSockets push progress events to clients.

```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "FastAPI Server"
participant Router as "Routers"
participant Service as "Workflow Service"
participant Celery as "Celery Worker"
participant WS as "WebSocket Hub"
participant Pipeline as "Core Pipeline"
participant Writer as "Artifacts Writers"
Client->>API : "POST /translate"
API->>Router : "Route to translation endpoint"
Router->>Service : "Start workflow"
Service->>Celery : "Enqueue OCR/Translate tasks"
Celery->>Pipeline : "Execute preprocessing + OCR + translation"
Pipeline-->>WS : "Emit progress events"
WS-->>Client : "Real-time updates"
Pipeline->>Writer : "Generate DOCX/HTML/Tree"
Writer-->>Service : "Artifact references"
Service-->>Router : "Task result"
Router-->>Client : "Response with artifact links"
```

**Diagram sources**
- [server.py:1-200](file://src/local_deepl/server.py#L1-L200)
- [translation.py:1-200](file://src/local_deepl/api/routers/translation.py#L1-L200)
- [workflow.py:1-200](file://src/local_deepl/api/services/workflow.py#L1-L200)
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [websocket.py:1-150](file://src/local_deepl/api/routers/websocket.py#L1-L150)
- [pipeline.py:1-120](file://src/local_deepl/pipeline.py#L1-L120)
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)

## Detailed Component Analysis

### FastAPI Backend
Responsibilities:
- Define REST endpoints for translation, extraction, OCR, and job management
- Serve static frontend assets
- Integrate middleware for security and configuration

Design principles:
- Clear separation between routers and services
- Request validation via Pydantic schemas
- Consistent error responses and status codes

Integration points:
- Calls workflow service to orchestrate tasks
- Publishes progress events through WebSocket hub
- Returns artifact references after completion

**Section sources**
- [server.py:1-200](file://src/local_deepl/server.py#L1-L200)
- [translation.py:1-200](file://src/local_deepl/api/routers/translation.py#L1-L200)
- [extraction.py:1-200](file://src/local_deepl/api/routers/extraction.py#L1-L200)
- [jobs.py:1-200](file://src/local_deepl/api/routers/jobs.py#L1-L200)
- [ocr.py:1-200](file://src/local_deepl/api/routers/ocr.py#L1-L200)

### Celery Background Workers
Responsibilities:
- Execute long-running tasks such as OCR, translation, and export
- Report progress back to the API via shared state or messaging
- Handle retries and failures gracefully

Design principles:
- Task decomposition into small, composable units
- Idempotent operations where possible
- Centralized task registry and routing

Integration points:
- Receives tasks from workflow service
- Invokes core pipeline stages
- Emits progress events consumed by WebSocket hub

**Section sources**
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [progress.py:1-120](file://src/local_deepl/api/services/progress.py#L1-L120)

### WebSocket Real-time Communication
Responsibilities:
- Maintain persistent connections for live progress updates
- Broadcast events to relevant clients based on job IDs
- Handle connection lifecycle and reconnection scenarios

Design principles:
- Event-driven updates with minimal payload size
- Decoupled from business logic via service abstractions
- Robust error handling and fallbacks

Integration points:
- Consumes progress events from pipeline and tasks
- Pushes updates to connected clients
- Supports subscription by job ID

**Section sources**
- [websocket.py:1-150](file://src/local_deepl/api/routers/websocket.py#L1-L150)
- [progress.py:1-120](file://src/local_deepl/api/services/progress.py#L1-L120)

### Multi-format Document Processing Pipeline
Responsibilities:
- Parse and normalize input documents (PDF, DOCX, images)
- Apply preprocessing, OCR, translation, and post-processing
- Generate outputs in multiple formats (DOCX, HTML, tree export)

Design principles:
- Modular stages with clear interfaces
- Pluggable engines for OCR and translation
- Callbacks for progress and side effects

Data flow patterns:
- Input normalization -> Preprocessing -> OCR (if needed) -> Translation -> Post-processing -> Export
- Each stage emits progress events and can be retried independently

**Section sources**
- [pipeline.py:1-120](file://src/local_deepl/pipeline.py#L1-L120)
- [document.py:1-120](file://src/local_deepl/core/document.py#L1-L120)
- [preprocessing.py:1-120](file://src/local_deepl/core/preprocessing.py#L1-L120)
- [processors.py:1-120](file://src/local_deepl/core/processors.py#L1-L120)
- [dual_translator.py:1-120](file://src/local_deepl/core/dual_translator.py#L1-L120)
- [postprocess.py:1-120](file://src/local_deepl/core/postprocess.py#L1-L120)
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)

### Workflows: Grounded and Hybrid Strategies
Responsibilities:
- Encapsulate processing strategies with shared base behavior
- Provide hooks for LLM prompting and rasterization when needed
- Allow composition of OCR and translation steps

Design principles:
- Strategy pattern for interchangeable workflows
- Extensible via base class and callback mechanisms
- Clear separation between orchestration and engine calls

**Section sources**
- [base.py:1-120](file://src/local_deepl/core/workflows/base.py#L1-L120)
- [grounded.py:1-120](file://src/local_deepl/core/workflows/grounded.py#L1-L120)
- [hybrid.py:1-120](file://src/local_deepl/core/workflows/hybrid.py#L1-L120)
- [prompted.py:1-120](file://src/local_deepl/core/grounded/prompted.py#L1-L120)
- [rasterize.py:1-120](file://src/local_deepl/core/grounded/rasterize.py#L1-L120)

### OCR Subsystem
Responsibilities:
- Interface with OCR engines (e.g., Tesseract via client)
- Apply filters to improve recognition quality
- Return normalized text blocks aligned with document structure

Design principles:
- Abstraction over OCR providers
- Configurable filters and parameters
- Error isolation and fallbacks

**Section sources**
- [client.py:1-120](file://src/local_deepl/core/ocr/client.py#L1-L120)
- [filters.py:1-120](file://src/local_deepl/core/ocr/filters.py#L1-L120)
- [trocr_engine.py:1-120](file://src/local_deepl/core/trocr_engine.py#L1-L120)

### Translation Engines
Responsibilities:
- Provide translation capabilities using NLLB and other engines
- Support dual translation paths and fallbacks
- Integrate with glossaries and prompts when applicable

Design principles:
- Engine abstraction for pluggable backends
- Configurable parameters and retry policies
- Progress reporting and error propagation

**Section sources**
- [nllb_engine.py:1-120](file://src/local_deepl/core/nllb_engine.py#L1-L120)
- [dual_translator.py:1-120](file://src/local_deepl/core/dual_translator.py#L1-L120)

### Writers and Artifacts
Responsibilities:
- Generate final artifacts in DOCX, HTML, and structured tree formats
- Preserve document structure and metadata
- Support incremental writes and memory-efficient processing

Design principles:
- Format-specific writer implementations
- Common interface for artifact creation
- Integration with progress reporting

**Section sources**
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)

## Dependency Analysis
High-level dependencies:
- API depends on services and routers
- Services depend on Celery tasks and workflow orchestrators
- Workflows depend on core pipeline components and engines
- Writers are leaf components producing final artifacts

```mermaid
graph LR
API["FastAPI Routers"] --> SVC["Workflow Service"]
SVC --> CEL["Celery Tasks"]
CEL --> PIPE["Core Pipeline"]
PIPE --> WR["Writers"]
PIPE --> OCR["OCR Client/Filters"]
PIPE --> TR["Translation Engines"]
API --> WS["WebSocket Hub"]
```

**Diagram sources**
- [server.py:1-200](file://src/local_deepl/server.py#L1-L200)
- [workflow.py:1-200](file://src/local_deepl/api/services/workflow.py#L1-L200)
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [pipeline.py:1-120](file://src/local_deepl/pipeline.py#L1-L120)
- [client.py:1-120](file://src/local_deepl/core/ocr/client.py#L1-L120)
- [filters.py:1-120](file://src/local_deepl/core/ocr/filters.py#L1-L120)
- [nllb_engine.py:1-120](file://src/local_deepl/core/nllb_engine.py#L1-L120)
- [trocr_engine.py:1-120](file://src/local_deepl/core/trocr_engine.py#L1-L120)
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)
- [websocket.py:1-150](file://src/local_deepl/api/routers/websocket.py#L1-L150)

**Section sources**
- [server.py:1-200](file://src/local_deepl/server.py#L1-L200)
- [workflow.py:1-200](file://src/local_deepl/api/services/workflow.py#L1-L200)
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [pipeline.py:1-120](file://src/local_deepl/pipeline.py#L1-L120)

## Performance Considerations
- Asynchronous processing: Offload heavy tasks to Celery workers to keep API responsive
- Streaming progress: Use WebSockets to provide immediate feedback without polling
- Memory efficiency: Process large documents in chunks and stream writes to disk
- Engine selection: Choose appropriate OCR and translation engines based on workload characteristics
- Scaling: Deploy multiple Celery workers horizontally; use container orchestration for elasticity

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- Task failures: Inspect Celery logs and task results; verify environment variables and model availability
- WebSocket disconnects: Check network stability and ensure proper reconnection logic on the client
- OCR errors: Validate image preprocessing and filter configurations; review OCR client logs
- Translation timeouts: Adjust engine parameters and consider fallback strategies
- Artifact generation: Confirm writer permissions and disk space; validate output format constraints

**Section sources**
- [celery_app.py:1-120](file://src/local_deepl/api/celery_app.py#L1-L120)
- [tasks.py:1-200](file://src/local_deepl/api/tasks.py#L1-L200)
- [websocket.py:1-150](file://src/local_deepl/api/routers/websocket.py#L1-L150)
- [client.py:1-120](file://src/local_deepl/core/ocr/client.py#L1-L120)
- [filters.py:1-120](file://src/local_deepl/core/ocr/filters.py#L1-L120)
- [nllb_engine.py:1-120](file://src/local_deepl/core/nllb_engine.py#L1-L120)
- [docx_writer.py:1-120](file://src/local_deepl/core/docx_writer.py#L1-L120)
- [html_writer.py:1-120](file://src/local_deepl/core/html_writer.py#L1-L120)
- [tree_export.py:1-120](file://src/local_deepl/core/tree_export.py#L1-L120)

## Conclusion
LocalDeepL’s architecture balances responsiveness, scalability, and extensibility. The FastAPI backend provides a clean API surface, Celery workers handle intensive processing, and WebSockets deliver real-time insights. The modular core pipeline and pluggable engines enable flexible document processing across formats and languages. With a containerized deployment model and horizontal scaling options, the system is well-suited for both local development and production environments.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Deployment Model
- Containerization: Dockerfile defines the runtime environment and dependencies
- Orchestration: compose.yaml specifies services (API, workers, optional Redis/Broker)
- Environment configuration: Externalize secrets and model paths via environment variables

**Section sources**
- [Dockerfile:1-120](file://Dockerfile#L1-L120)
- [compose.yaml:1-120](file://compose.yaml#L1-L120)