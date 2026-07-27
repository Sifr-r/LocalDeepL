# Data Flow and Processing Pipelines

<cite>
**Referenced Files in This Document**
- [server.py](file://src/local_deepl/server.py)
- [pipeline.py](file://src/local_deepl/pipeline.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [jobs.py](file://src/local_deepl/api/routers/jobs.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)
- [document.py](file://src/local_deepl/core/document.py)
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [ocr_response.py](file://src/local_deepl/api/services/ocr_response.py)
- [ocr_settings.py](file://src/local_deepl/api/services/ocr_settings.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)
- [resilience.py](file://src/local_deepl/core/ocr/resilience.py)
- [exceptions.py](file://src/local_deepl/core/ocr/exceptions.py)
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

## Introduction
This document explains LocalDeepL’s data flow and processing pipelines from file upload through OCR, translation, and export. It covers the pipeline orchestration via a base workflow class and concrete implementations (hybrid and grounded), how data transforms across stages (preprocessing, OCR extraction, post-processing, output generation), error handling and retries, progress tracking, and background job execution with Celery workers.

## Project Structure
LocalDeepL is organized into API routers and services that expose HTTP/WebSocket endpoints, Celery task definitions for background processing, and core modules implementing OCR, translation, workflows, and document I/O. The key areas relevant to data flow are:
- API layer: routers for jobs, OCR, translation, websocket events; services for workflow orchestration, progress tracking, and settings.
- Core layer: preprocessing, OCR engines, post-processing, translation engines, tree export, and workflow base/impls.
- Background processing: Celery app and tasks that execute long-running jobs.

```mermaid
graph TB
subgraph "API Layer"
RJobs["routers/jobs.py"]
ROcr["routers/ocr.py"]
RTrans["routers/translation.py"]
RWs["routers/websocket.py"]
SWork["services/workflow.py"]
SProg["services/progress.py"]
SFact["services/ocr_pipeline_factory.py"]
end
subgraph "Background"
CApp["api/celery_app.py"]
Tasks["api/tasks.py"]
end
subgraph "Core"
BaseW["core/workflows/base.py"]
HybW["core/workflows/hybrid.py"]
GrdW["core/workflows/grounded.py"]
Pre["core/preprocessing.py"]
Ocr["core/ocr/*"]
Post["core/postprocess.py"]
Trans["core/translation.py"]
DualT["core/dual_translator.py"]
Export["core/tree_export.py"]
Doc["core/document.py"]
end
RJobs --> SWork
ROcr --> SFact
RTrans --> SWork
RWs --> SProg
SWork --> BaseW
BaseW --> HybW
BaseW --> GrdW
SWork --> Pre
SWork --> Ocr
SWork --> Post
SWork --> Trans
Trans --> DualT
SWork --> Export
SWork --> Doc
Tasks --> CApp
SWork --> Tasks
```

**Diagram sources**
- [jobs.py](file://src/local_deepl/api/routers/jobs.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)
- [document.py](file://src/local_deepl/core/document.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)

**Section sources**
- [server.py](file://src/local_deepl/server.py)
- [pipeline.py](file://src/local_deepl/pipeline.py)

## Core Components
- Workflow base and implementations: define the abstract pipeline steps and concrete strategies (hybrid, grounded).
- Preprocessing and post-processing: prepare images/PDFs and refine OCR results.
- OCR subsystem: client, resilience, filters, and prompts for robust extraction.
- Translation subsystem: dual translator and engines for language conversion.
- Export subsystem: tree-based export utilities for final artifacts.
- API services: workflow orchestration, progress tracking, OCR settings, and response shaping.
- Background jobs: Celery app and tasks for asynchronous processing.

**Section sources**
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [ocr_response.py](file://src/local_deepl/api/services/ocr_response.py)
- [ocr_settings.py](file://src/local_deepl/api/services/ocr_settings.py)
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)
- [document.py](file://src/local_deepl/core/document.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)

## Architecture Overview
The system exposes HTTP endpoints to start jobs, tracks progress via WebSocket events, and executes long-running tasks asynchronously using Celery. A workflow orchestrator composes preprocessing, OCR, post-processing, translation, and export steps. Concrete workflows implement strategy-specific logic while reusing shared components.

```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "API Router"
participant Worker as "Celery Task"
participant Orchestrator as "Workflow Service"
participant BaseWF as "Base Workflow"
participant ImplWF as "Hybrid/Grounded WF"
participant Progress as "Progress Service"
participant WS as "WebSocket"
Client->>API : "POST /jobs or /ocr"
API->>Worker : "Queue job with payload"
Worker->>Orchestrator : "Start pipeline"
Orchestrator->>BaseWF : "Initialize workflow"
BaseWF-->>ImplWF : "Dispatch to concrete implementation"
ImplWF->>ImplWF : "Preprocess -> OCR -> Post-process"
ImplWF->>Orchestrator : "Emit progress updates"
Orchestrator->>Progress : "Persist progress"
Progress-->>WS : "Broadcast events"
ImplWF->>ImplWF : "Translate (optional)"
ImplWF->>ImplWF : "Export artifacts"
Orchestrator-->>Worker : "Return result/status"
Worker-->>API : "Job completed"
API-->>Client : "Poll status or receive WS event"
```

**Diagram sources**
- [jobs.py](file://src/local_deepl/api/routers/jobs.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)

## Detailed Component Analysis

### Pipeline Orchestration: Base Workflow and Implementations
The base workflow defines the canonical pipeline stages and lifecycle hooks. Concrete workflows (hybrid, grounded) override specific steps to tailor OCR and post-processing behavior while sharing common orchestration.

```mermaid
classDiagram
class BaseWorkflow {
+initialize()
+preprocess(input)
+run_ocr(preprocessed)
+post_process(ocr_result)
+translate(text_or_tree)
+export(tree)
+execute(input)
}
class HybridWorkflow {
+run_ocr(preprocessed)
+post_process(ocr_result)
}
class GroundedWorkflow {
+run_ocr(preprocessed)
+post_process(ocr_result)
}
BaseWorkflow <|-- HybridWorkflow
BaseWorkflow <|-- GroundedWorkflow
```

Key responsibilities:
- Initialization and input validation
- Stage dispatching and state passing between steps
- Hook points for progress callbacks and error propagation
- Optional translation and artifact export

**Diagram sources**
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)

**Section sources**
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)

### Data Transformations Across Stages
- Preprocessing: normalizes inputs (images/PDFs), enhances readability, prepares pages/chunks for OCR.
- OCR extraction: runs OCR engines with resilience and filtering; produces structured text and optional layout metadata.
- Post-processing: refines OCR output (cleanups, normalization, structure inference).
- Translation: converts extracted text using dual translator and configured engines.
- Export: serializes results into target formats via tree export utilities.

```mermaid
flowchart TD
Start(["Input File"]) --> Pre["Preprocessing"]
Pre --> OCR["OCR Extraction"]
OCR --> Post["Post-processing"]
Post --> Translate{"Translation Enabled?"}
Translate --> |Yes| Trans["Translation"]
Translate --> |No| Export["Export Artifacts"]
Trans --> Export
Export --> End(["Output Artifacts"])
```

**Diagram sources**
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)

**Section sources**
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)

### OCR Subsystem and Resilience
OCR is encapsulated with resilience mechanisms, exception types, and configuration. The factory selects appropriate OCR pipelines based on settings and input characteristics.

```mermaid
sequenceDiagram
participant WF as "Workflow Step"
participant Factory as "OCR Pipeline Factory"
participant Client as "OCR Client"
participant Resil as "Resilience Wrapper"
participant Filters as "Filters"
WF->>Factory : "build(settings, input_type)"
Factory-->>WF : "OCR pipeline instance"
WF->>Client : "run(pages/images)"
Client->>Resil : "invoke with retry/backoff"
Resil-->>Client : "result or raise"
Client->>Filters : "apply filters"
Filters-->>WF : "structured OCR result"
```

**Diagram sources**
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [client.py](file://src/local_deepl/core/ocr/client.py)
- [resilience.py](file://src/local_deepl/core/ocr/resilience.py)
- [filters.py](file://src/local_deepl/core/ocr/filters.py)
- [exceptions.py](file://src/local_deepl/core/ocr/exceptions.py)

**Section sources**
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [ocr_response.py](file://src/local_deepl/api/services/ocr_response.py)
- [ocr_settings.py](file://src/local_deepl/api/services/ocr_settings.py)
- [resilience.py](file://src/local_deepl/core/ocr/resilience.py)
- [exceptions.py](file://src/local_deepl/core/ocr/exceptions.py)

### Translation Subsystem
Translation uses a dual translator abstraction to support multiple engines and fallback strategies. Settings control source/target languages and engine selection.

```mermaid
classDiagram
class DualTranslator {
+translate(text, src_lang, tgt_lang) string
+fallback_chain()
}
class TranslationConfig {
+src_lang
+tgt_lang
+engine
}
DualTranslator --> TranslationConfig : "uses"
```

**Diagram sources**
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [translation.py](file://src/local_deepl/core/translation.py)

**Section sources**
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)

### Export and Document Models
Tree export utilities serialize processed structures into various formats. The document model represents the unified intermediate representation used throughout the pipeline.

```mermaid
classDiagram
class Document {
+pages
+blocks
+metadata
}
class TreeExporter {
+to_json(document)
+to_html(document)
+to_docx(document)
}
TreeExporter --> Document : "serializes"
```

**Diagram sources**
- [document.py](file://src/local_deepl/core/document.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)

**Section sources**
- [document.py](file://src/local_deepl/core/document.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)

### Background Jobs and Celery Integration
Long-running jobs are queued via Celery tasks. The Celery app configures brokers and workers; tasks invoke the workflow service and emit progress updates.

```mermaid
sequenceDiagram
participant API as "API Router"
participant Celery as "Celery App"
participant Task as "Task Function"
participant Service as "Workflow Service"
participant Progress as "Progress Service"
participant WS as "WebSocket"
API->>Celery : "send_task('process_job', args)"
Celery->>Task : "dispatch to worker"
Task->>Service : "execute_workflow(payload)"
Service->>Progress : "update(job_id, stage, pct)"
Progress-->>WS : "emit event"
Service-->>Task : "return result or error"
Task-->>Celery : "mark complete"
```

**Diagram sources**
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)

**Section sources**
- [celery_app.py](file://src/local_deepl/api/celery_app.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)

## Dependency Analysis
- API routers depend on services for orchestration and progress.
- Services depend on core workflows and utilities (OCR, translation, export).
- Workflows depend on preprocessing, OCR, post-processing, translation, and export modules.
- Celery tasks depend on the workflow service and progress service.

```mermaid
graph LR
RJobs["routers/jobs.py"] --> SWork["services/workflow.py"]
RJobs --> SProg["services/progress.py"]
SWork --> BaseW["core/workflows/base.py"]
BaseW --> HybW["core/workflows/hybrid.py"]
BaseW --> GrdW["core/workflows/grounded.py"]
SWork --> Pre["core/preprocessing.py"]
SWork --> OcrF["api/services/ocr_pipeline_factory.py"]
SWork --> Post["core/postprocess.py"]
SWork --> Trans["core/translation.py"]
Trans --> DualT["core/dual_translator.py"]
SWork --> Export["core/tree_export.py"]
Tasks["api/tasks.py"] --> SWork
Tasks --> CApp["api/celery_app.py"]
```

**Diagram sources**
- [jobs.py](file://src/local_deepl/api/routers/jobs.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [base.py](file://src/local_deepl/core/workflows/base.py)
- [hybrid.py](file://src/local_deepl/core/workflows/hybrid.py)
- [grounded.py](file://src/local_deepl/core/workflows/grounded.py)
- [preprocessing.py](file://src/local_deepl/core/preprocessing.py)
- [ocr_pipeline_factory.py](file://src/local_deepl/api/services/ocr_pipeline_factory.py)
- [postprocess.py](file://src/local_deepl/core/postprocess.py)
- [translation.py](file://src/local_deepl/core/translation.py)
- [dual_translator.py](file://src/local_deepl/core/dual_translator.py)
- [tree_export.py](file://src/local_deepl/core/tree_export.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)

**Section sources**
- [jobs.py](file://src/local_deepl/api/routers/jobs.py)
- [workflow.py](file://src/local_deepl/api/services/workflow.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)

## Performance Considerations
- Prefer batched OCR calls where possible to reduce overhead.
- Use resilient wrappers with tuned backoff to avoid cascading failures.
- Cache reusable assets (e.g., dictionaries, models) to minimize cold starts.
- Stream large documents page-by-page to limit memory usage.
- Offload heavy work to Celery workers to keep API responsive.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and remedies:
- OCR failures: check resilience configuration, network timeouts, and engine availability. Inspect exceptions raised by OCR clients.
- Translation errors: verify language codes and engine credentials; use dual translator fallback chain.
- Progress not updating: ensure progress service is invoked at each stage and WebSocket connections are active.
- Job stuck: inspect Celery worker logs, broker connectivity, and task queue depth.

**Section sources**
- [resilience.py](file://src/local_deepl/core/ocr/resilience.py)
- [exceptions.py](file://src/local_deepl/core/ocr/exceptions.py)
- [progress.py](file://src/local_deepl/api/services/progress.py)
- [websocket.py](file://src/local_deepl/api/routers/websocket.py)
- [tasks.py](file://src/local_deepl/api/tasks.py)
- [celery_app.py](file://src/local_deepl/api/celery_app.py)

## Conclusion
LocalDeepL’s pipeline is orchestrated by a base workflow with concrete hybrid and grounded implementations, enabling flexible OCR and translation strategies. Robustness is achieved through resilience wrappers, clear exception handling, and background job execution via Celery. Progress tracking and WebSocket events provide real-time visibility into job states. The modular design supports extensibility and performance tuning across preprocessing, OCR, post-processing, translation, and export stages.